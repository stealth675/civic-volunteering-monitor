from __future__ import annotations

import heapq
import logging
import re
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse, urlunparse

from monitor.crawl.fetch import DomainRateLimiter, fetch_with_retries
from monitor.crawl.heuristics import (
    HEURISTIC_PATHS,
    has_url_hint,
    is_crawl_relevant,
    is_document_url,
    is_hard_denied,
    is_political_section_url,
    relevance_details,
    should_keep_document,
)
from monitor.crawl.html_extract import extract_links, html_looks_js_driven
from monitor.crawl.playwright_fetch import fetch_rendered_html
from monitor.crawl.sitemap import discover_sitemaps, parse_sitemap_entries
from monitor.parse.content_clean import extract_main_text_from_html

logger = logging.getLogger(__name__)
MIN_FETCH_ATTEMPTS_PER_JURISDICTION = 5
MAX_DOCS_FROM_POLITICAL_SECTIONS = 120
MAX_DOCS_FROM_PLANS = 60
MAX_DOCS_FROM_MISC = 60
DATE_PATTERNS = [
    re.compile(r"(20\d{2})[-/](\d{2})[-/](\d{2})"),
    re.compile(r"(20\d{2})/(\d{2})/(\d{2})"),
]
META_DATE_PATTERNS = [
    re.compile(r'property=["\']article:published_time["\']\s+content=["\']([^"\']+)["\']', re.IGNORECASE),
    re.compile(r'name=["\']datePublished["\']\s+content=["\']([^"\']+)["\']', re.IGNORECASE),
    re.compile(r'<time[^>]*datetime=["\']([^"\']+)["\']', re.IGNORECASE),
]


@dataclass
class SeedDiagnostics:
    base_fetch_status: int | None = None
    base_fetch_error: str = ""
    base_final_url: str = ""
    robots_status: int | None = None
    sitemap_status: int | None = None
    sitemap_urls_found: int = 0
    sitemap_sitemaps_found: int = 0
    enqueued_urls_total: int = 0
    enqueued_from_sitemap: int = 0
    enqueued_heuristic_paths: int = 0
    dropped_before_fetch_count: int = 0
    hard_deny_dropped_count: int = 0
    drop_reasons_top3: str = ""
    first_http_error_code: int | None = None
    http_403_count: int = 0
    http_429_count: int = 0
    http_5xx_count: int = 0
    fetch_attempts: int = 0
    empty_reason: str = ""
    time_budget_seconds: int = 0
    time_spent_seconds: float = 0.0


@dataclass
class CrawlResult:
    pages_fetched: int
    docs_found: list[dict]
    http_errors: int
    timeouts: int
    notes: list[str]
    diagnostics: SeedDiagnostics = field(default_factory=SeedDiagnostics)


def _normalize_domain(netloc: str) -> str:
    value = (netloc or "").lower()
    return value[4:] if value.startswith("www.") else value


def _same_domain(url: str, domain_netloc: str) -> bool:
    return _normalize_domain(urlparse(url).netloc) == _normalize_domain(domain_netloc)


def _alternate_base_urls(base_url: str) -> list[str]:
    parsed = urlparse(base_url)
    host = parsed.netloc
    hosts = [host, host[4:] if host.startswith("www.") else f"www.{host}"]
    out = []
    for h in hosts:
        u = urlunparse(("https", h, "", "", "", "")).rstrip("/")
        if u and u not in out:
            out.append(u)
    return out


def _timed_fetch(url: str, user_agent: str, timeout: int, limiter: DomainRateLimiter):
    start = time.perf_counter()
    try:
        res = fetch_with_retries(url, user_agent, timeout, limiter=limiter)
        return res, int((time.perf_counter() - start) * 1000), ""
    except Exception as exc:
        return None, int((time.perf_counter() - start) * 1000), type(exc).__name__


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        pass
    try:
        return parsedate_to_datetime(value).astimezone(timezone.utc)
    except Exception:
        return None


def _extract_url_date(url: str) -> datetime | None:
    for p in DATE_PATTERNS:
        m = p.search(url)
        if not m:
            continue
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), tzinfo=timezone.utc)
        except Exception:
            continue
    return None


def _extract_html_meta_date(html: str) -> datetime | None:
    snippet = (html or "")[:10000]
    for pattern in META_DATE_PATTERNS:
        m = pattern.search(snippet)
        if not m:
            continue
        dt = _parse_datetime(m.group(1))
        if dt:
            return dt
    return None


def _recency_bucket(dt: datetime | None, now: datetime) -> int:
    if not dt:
        return 3
    days = (now - dt).days
    if days <= 7:
        return 0
    if days <= 30:
        return 1
    if days <= 365:
        return 2
    return 3


def _seed_fetch_with_fallback(url: str, user_agent: str, timeout: int, limiter: DomainRateLimiter, playwright_enabled: bool):
    res, elapsed_ms, err = _timed_fetch(url, user_agent, timeout, limiter)
    if res is not None and res.status_code in {403, 429} and playwright_enabled:
        try:
            html = fetch_rendered_html(url)
            logger.info("SEED_PLAYWRIGHT_FALLBACK url=%s original_status=%s", url, res.status_code)
            mock = type("Resp", (), {"status_code": 200, "text": html, "content": html.encode("utf-8"), "headers": {"Content-Type": "text/html"}})()
            return mock, elapsed_ms, ""
        except Exception as exc:
            err = type(exc).__name__
    return res, elapsed_ms, err


def _update_http_counters(diag: SeedDiagnostics, status_code: int) -> None:
    if status_code != 200 and diag.first_http_error_code is None:
        diag.first_http_error_code = status_code
    if status_code == 403:
        diag.http_403_count += 1
    if status_code == 429:
        diag.http_429_count += 1
    if 500 <= status_code <= 599:
        diag.http_5xx_count += 1


def crawl_jurisdiction(
    base_url: str,
    timeout: int,
    user_agent: str,
    playwright_enabled: bool = False,
    run_id: int | None = None,
    domain_time_budget_seconds: int = 45,
) -> CrawlResult:
    limiter = DomainRateLimiter(max_per_second=2.0)
    queue: list[tuple[int, int, str, str, str, datetime | None, str]] = []
    queued_urls: set[str] = set()
    seen: set[str] = set()
    docs_found: list[dict] = []
    candidate_urls: set[str] = set()
    http_errors = 0
    timeouts = 0
    pages_fetched = 0
    notes: list[str] = []
    drop_reasons: Counter[str] = Counter()
    diag = SeedDiagnostics(time_budget_seconds=domain_time_budget_seconds)
    now = datetime.now(timezone.utc)

    def push_candidate(url: str, title: str, section: str, parent_date: datetime | None, date_source: str):
        if url in queued_urls or url in seen:
            return
        details = relevance_details(text=title, url=url, section=section, doc_type_hint="DOCUMENT" if is_document_url(url) else "HTML_PAGE")
        rec_bucket = _recency_bucket(parent_date, now)
        heapq.heappush(queue, (rec_bucket, -details["score"], url, title, section, parent_date, date_source))
        queued_urls.add(url)

    base_candidates = _alternate_base_urls(base_url)
    active_base = base_candidates[0]
    domain = _normalize_domain(urlparse(active_base).netloc)
    logger.info("JURISDICTION_START run_id=%s base_url=%s domain=%s", run_id, base_url, domain)

    for candidate in base_candidates:
        res, elapsed_ms, err = _seed_fetch_with_fallback(candidate, user_agent, timeout, limiter, playwright_enabled)
        status = getattr(res, "status_code", None)
        logger.info("FETCH base_url=%s status=%s final_url=%s elapsed_ms=%s error_type=%s", candidate, status, candidate, elapsed_ms, err)
        if res is not None and status and status < 500:
            active_base = candidate
            diag.base_fetch_status = status
            diag.base_final_url = candidate
            break
        diag.base_fetch_status = status
        diag.base_fetch_error = err or (f"HTTP_{status}" if status else "fetch_failed")

    start_time = time.monotonic()
    domain = _normalize_domain(urlparse(active_base).netloc)

    robots_res, robots_elapsed_ms, robots_err = _timed_fetch(f"{active_base}/robots.txt", user_agent, timeout, limiter)
    diag.robots_status = getattr(robots_res, "status_code", None)
    logger.info("FETCH robots url=%s/robots.txt status=%s elapsed_ms=%s error_type=%s", active_base, diag.robots_status, robots_elapsed_ms, robots_err)

    sitemap_urls = discover_sitemaps(active_base, user_agent, timeout, limiter=limiter)
    diag.sitemap_sitemaps_found = len(sitemap_urls)
    for sitemap_url in sorted(set(sitemap_urls)):
        sres, elapsed_ms, err = _timed_fetch(sitemap_url, user_agent, timeout, limiter)
        status = getattr(sres, "status_code", None)
        entries = []
        if sres is not None and status == 200:
            entries = parse_sitemap_entries(sres.content)
        logger.info("FETCH sitemap url=%s status=%s urls_found=%s sitemaps=%s elapsed_ms=%s error_type=%s", sitemap_url, status, len(entries), len(sitemap_urls), elapsed_ms, err)
        if diag.sitemap_status is None:
            diag.sitemap_status = status
        for e in sorted(entries, key=lambda x: x["url"]):
            u = e["url"]
            if not _same_domain(u, domain):
                diag.dropped_before_fetch_count += 1
                drop_reasons["cross_domain"] += 1
                continue
            if is_hard_denied(u):
                diag.dropped_before_fetch_count += 1
                diag.hard_deny_dropped_count += 1
                drop_reasons["hard_deny"] += 1
                continue
            dt = _parse_datetime(e.get("lastmod"))
            push_candidate(u, "", "", dt, "sitemap_lastmod" if dt else "none")
            diag.enqueued_from_sitemap += 1
            diag.sitemap_urls_found += 1

    for p in sorted(HEURISTIC_PATHS):
        push_candidate(f"{active_base}{p}", "", "", None, "none")
        diag.enqueued_heuristic_paths += 1
    diag.enqueued_urls_total = len(queue)
    logger.info("ENQUEUE from_sitemap count=%s", diag.enqueued_from_sitemap)
    logger.info("ENQUEUE initial_heuristic_paths count=%s", diag.enqueued_heuristic_paths)
    logger.info("ENQUEUE total_before_crawl count=%s", len(queue))

    while queue:
        if time.monotonic() - start_time >= domain_time_budget_seconds:
            notes.append("time_budget_reached")
            logger.warning(
                "TIME_BUDGET_REACHED domain=%s time_budget_seconds=%s time_spent_seconds=%.2f fetched=%s html=%s docs=%s",
                domain,
                domain_time_budget_seconds,
                time.monotonic() - start_time,
                diag.fetch_attempts,
                pages_fetched,
                len(docs_found),
            )
            break

        _, _, url, title, section, inherited_date, inherited_source = heapq.heappop(queue)
        if url in seen:
            continue
        seen.add(url)
        diag.fetch_attempts += 1

        res, _, _ = _seed_fetch_with_fallback(url, user_agent, timeout, limiter, playwright_enabled)
        if res is None:
            timeouts += 1
            http_errors += 1
            continue
        _update_http_counters(diag, res.status_code)
        if res.status_code != 200:
            http_errors += 1
            continue

        ctype = res.headers.get("Content-Type", "").lower()
        header_date = _parse_datetime(res.headers.get("Last-Modified"))
        effective_date = header_date or inherited_date or _extract_url_date(url)
        date_source = "header_last_modified" if header_date else ("inherited" if inherited_date else ("url_pattern" if _extract_url_date(url) else inherited_source or "none"))

        if any(x in ctype for x in ["application/pdf", "application/msword", "application/vnd.openxmlformats"]):
            details = relevance_details(url=url, title=title, section=section, mime_type=ctype, doc_type_hint="DOCUMENT")
            if url not in candidate_urls and should_keep_document(url=url, title=title, parent_url=section, score=details["score"]):
                docs_found.append(
                    {
                        "url": url,
                        "title": title,
                        "high_relevance": details["score"] >= 6,
                        "doc_type_hint": "DOCUMENT",
                        "relevance_score": details["score"],
                        "effective_date": effective_date.isoformat() if effective_date else "",
                        "recency_bucket": _recency_bucket(effective_date, now),
                        "date_source": date_source,
                        "theme_match": details["theme_match"],
                        "theme_hits": details["theme_hits"],
                        "political_match": details["political_match"],
                        "political_hits": details["political_hits"],
                    }
                )
                candidate_urls.add(url)
            continue

        pages_fetched += 1
        html = res.text
        links = extract_links(url, html)
        if not links and playwright_enabled and html_looks_js_driven(html):
            try:
                html = fetch_rendered_html(url)
                links = extract_links(url, html)
                notes.append("requires_js_rendering")
            except Exception:
                notes.append("js_rendering_failed")

        html_meta_date = _extract_html_meta_date(html)
        if html_meta_date:
            effective_date = html_meta_date
            date_source = "html_meta"

        page_text = extract_main_text_from_html(html)
        details = relevance_details(text=page_text[:4000], url=url, title=title, section=section, mime_type=ctype, doc_type_hint="HTML_PAGE")
        if details["score"] >= 0 and is_crawl_relevant(text=page_text[:4000], url=url, title=title, section=section, mime_type=ctype, doc_type_hint="HTML_PAGE") and url not in candidate_urls:
            docs_found.append(
                {
                    "url": url,
                    "title": title,
                    "high_relevance": True,
                    "doc_type_hint": "HTML_PAGE",
                    "relevance_score": details["score"],
                    "effective_date": effective_date.isoformat() if effective_date else "",
                    "recency_bucket": _recency_bucket(effective_date, now),
                    "date_source": date_source,
                    "theme_match": details["theme_match"],
                    "theme_hits": details["theme_hits"],
                    "political_match": details["political_match"],
                    "political_hits": details["political_hits"],
                }
            )
            candidate_urls.add(url)

        for link, link_title in sorted(links, key=lambda x: x[0]):
            if not _same_domain(link, domain):
                diag.dropped_before_fetch_count += 1
                drop_reasons["cross_domain"] += 1
                continue
            if is_hard_denied(link):
                diag.dropped_before_fetch_count += 1
                diag.hard_deny_dropped_count += 1
                drop_reasons["hard_deny"] += 1
                continue
            link_details = relevance_details(text=link_title, url=link, section=url, doc_type_hint="DOCUMENT" if is_document_url(link) else "HTML_PAGE")
            if is_document_url(link):
                if should_keep_document(url=link, title=link_title, parent_url=url, score=link_details["score"]):
                    push_candidate(link, link_title, url, effective_date, "inherited")
            elif is_crawl_relevant(text=link_title, url=link, section=url, doc_type_hint="HTML_PAGE") or has_url_hint(link):
                push_candidate(link, link_title, url, effective_date, "inherited")
            else:
                diag.dropped_before_fetch_count += 1
                drop_reasons["low_relevance"] += 1

        if diag.fetch_attempts < MIN_FETCH_ATTEMPTS_PER_JURISDICTION and not queue:
            for p in sorted(HEURISTIC_PATHS)[:MIN_FETCH_ATTEMPTS_PER_JURISDICTION]:
                push_candidate(f"{active_base}{p}", "", "", None, "none")

    # bounded by section quotas only (no absolute total cap)
    docs_found.sort(key=lambda item: (item.get("recency_bucket", 3), -item.get("relevance_score", 0), item.get("url", "")))
    selected: list[dict] = []
    counts = {"political": 0, "plans": 0, "misc": 0}
    for item in docs_found:
        url = item.get("url", "").lower()
        if is_political_section_url(url):
            bucket = "political"
        elif any(p in url for p in ["/plan", "/strategi", "/horing", "/hoyring"]):
            bucket = "plans"
        else:
            bucket = "misc"
        if bucket == "political" and counts[bucket] >= MAX_DOCS_FROM_POLITICAL_SECTIONS:
            continue
        if bucket == "plans" and counts[bucket] >= MAX_DOCS_FROM_PLANS:
            continue
        if bucket == "misc" and counts[bucket] >= MAX_DOCS_FROM_MISC:
            continue
        selected.append(item)
        counts[bucket] += 1

    docs_found = selected
    diag.drop_reasons_top3 = ",".join(f"{k}:{v}" for k, v in drop_reasons.most_common(3))
    diag.time_spent_seconds = round(time.monotonic() - start_time, 3)

    if pages_fetched == 0:
        if diag.base_fetch_error:
            diag.empty_reason = f"base_fetch_failed:{diag.base_fetch_error}"
        elif diag.enqueued_urls_total == 0:
            diag.empty_reason = "no_seed_urls_enqueued"
        elif diag.fetch_attempts == 0:
            diag.empty_reason = "all_urls_dropped_before_fetch"
        else:
            diag.empty_reason = "all_fetches_non_200_or_failed"
        logger.warning("JURISDICTION_EMPTY reason=%s base=%s", diag.empty_reason, active_base)

    return CrawlResult(pages_fetched, docs_found, http_errors, timeouts, notes, diagnostics=diag)

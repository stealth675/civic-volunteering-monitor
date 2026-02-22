from __future__ import annotations

import logging
import time
from collections import Counter, deque
from dataclasses import dataclass, field
from urllib.parse import urlparse, urlunparse

from monitor.crawl.fetch import DomainRateLimiter, fetch_with_retries
from monitor.crawl.heuristics import (
    HEURISTIC_PATHS,
    MAX_CANDIDATES_PER_DOMAIN,
    has_url_hint,
    is_crawl_relevant,
    is_document_url,
    is_hard_denied,
    is_political_section_url,
    relevance_score,
    should_keep_document,
)
from monitor.crawl.html_extract import extract_links, html_looks_js_driven
from monitor.crawl.playwright_fetch import fetch_rendered_html
from monitor.crawl.sitemap import discover_sitemaps, parse_sitemap_urls
from monitor.parse.content_clean import extract_main_text_from_html

logger = logging.getLogger(__name__)
MIN_FETCH_ATTEMPTS_PER_JURISDICTION = 5
MAX_DOCS_FROM_POLITICAL_SECTIONS = 80
MAX_DOCS_FROM_PLANS = 30
MAX_DOCS_FROM_MISC = 20


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
    hosts = [host]
    if host.startswith("www."):
        hosts.append(host[4:])
    else:
        hosts.append(f"www.{host}")
    schemes = ["https", parsed.scheme or "https"]
    out: list[str] = []
    for scheme in schemes:
        for h in hosts:
            u = urlunparse((scheme, h, "", "", "", "")).rstrip("/")
            if u and u not in out:
                out.append(u)
    return out


def _timed_fetch(url: str, user_agent: str, timeout: int, limiter: DomainRateLimiter):
    start = time.perf_counter()
    try:
        res = fetch_with_retries(url, user_agent, timeout, limiter=limiter)
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        return res, elapsed_ms, ""
    except Exception as exc:
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        return None, elapsed_ms, type(exc).__name__


def _seed_fetch_with_fallback(url: str, user_agent: str, timeout: int, limiter: DomainRateLimiter, playwright_enabled: bool):
    res, elapsed_ms, err = _timed_fetch(url, user_agent, timeout, limiter)
    if res is not None and res.status_code in {403, 429} and playwright_enabled:
        try:
            html = fetch_rendered_html(url)
            logger.info("SEED_PLAYWRIGHT_FALLBACK url=%s original_status=%s", url, res.status_code)
            return type("Resp", (), {"status_code": 200, "text": html, "content": html.encode("utf-8"), "headers": {"Content-Type": "text/html"}})(), elapsed_ms, ""
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


def crawl_jurisdiction(base_url: str, timeout: int, user_agent: str, playwright_enabled: bool = False, run_id: int | None = None) -> CrawlResult:
    limiter = DomainRateLimiter(max_per_second=2.0)
    seen: set[str] = set()
    q = deque()
    docs_found: list[dict] = []
    candidate_urls: set[str] = set()
    http_errors = 0
    timeouts = 0
    pages_fetched = 0
    notes: list[str] = []
    drop_reasons: Counter[str] = Counter()
    diag = SeedDiagnostics()

    base_candidates = _alternate_base_urls(base_url)
    active_base = base_candidates[0]
    domain = _normalize_domain(urlparse(active_base).netloc)
    logger.info("JURISDICTION_START run_id=%s base_url=%s domain=%s", run_id, base_url, domain)

    # Base fetch with URL fallback
    for candidate in base_candidates:
        res, elapsed_ms, err = _seed_fetch_with_fallback(candidate, user_agent, timeout, limiter, playwright_enabled)
        status = getattr(res, "status_code", None)
        logger.info("FETCH base_url=%s status=%s final_url=%s elapsed_ms=%s error_type=%s", candidate, status, candidate, elapsed_ms, err)
        if res is not None and status and status < 500:
            active_base = candidate
            diag.base_fetch_status = status
            diag.base_final_url = candidate
            diag.base_fetch_error = ""
            break
        diag.base_fetch_status = status
        diag.base_fetch_error = err or (f"HTTP_{status}" if status else "fetch_failed")

    domain = _normalize_domain(urlparse(active_base).netloc)

    # Robots discovery instrumentation
    robots_url = f"{active_base}/robots.txt"
    robots_res, robots_elapsed_ms, robots_err = _timed_fetch(robots_url, user_agent, timeout, limiter)
    diag.robots_status = getattr(robots_res, "status_code", None)
    logger.info("FETCH robots url=%s status=%s elapsed_ms=%s error_type=%s", robots_url, diag.robots_status, robots_elapsed_ms, robots_err)

    # Sitemap discovery + parsing with fallback to heuristic paths regardless of outcome
    sitemap_urls = discover_sitemaps(active_base, user_agent, timeout, limiter=limiter)
    diag.sitemap_sitemaps_found = len(sitemap_urls)
    sitemap_enqueued = 0
    sitemap_status_seen: int | None = None
    sitemap_urls_found = 0
    for sitemap_url in sitemap_urls:
        sres, elapsed_ms, err = _timed_fetch(sitemap_url, user_agent, timeout, limiter)
        status = getattr(sres, "status_code", None)
        sitemap_status_seen = status if sitemap_status_seen is None else sitemap_status_seen
        parsed_urls: list[str] = []
        if sres is not None and status == 200:
            try:
                parsed_urls = parse_sitemap_urls(sres.content)
            except Exception:
                parsed_urls = []
        logger.info(
            "FETCH sitemap url=%s status=%s urls_found=%s sitemaps=%s elapsed_ms=%s error_type=%s",
            sitemap_url,
            status,
            len(parsed_urls),
            len(sitemap_urls),
            elapsed_ms,
            err,
        )
        if sres is None or status != 200:
            continue
        sitemap_urls_found += len(parsed_urls)
        for u in parsed_urls:
            if not _same_domain(u, domain):
                drop_reasons["cross_domain"] += 1
                diag.dropped_before_fetch_count += 1
                continue
            if is_hard_denied(u):
                drop_reasons["hard_deny"] += 1
                diag.hard_deny_dropped_count += 1
                diag.dropped_before_fetch_count += 1
                continue
            if is_crawl_relevant(url=u) or has_url_hint(u):
                q.append((u, 0))
                sitemap_enqueued += 1

    diag.sitemap_status = sitemap_status_seen
    diag.sitemap_urls_found = sitemap_urls_found
    diag.enqueued_from_sitemap = sitemap_enqueued
    logger.info("ENQUEUE from_sitemap count=%s", sitemap_enqueued)

    heuristic_count = 0
    for p in HEURISTIC_PATHS:
        q.append((f"{active_base}{p}", 0))
        heuristic_count += 1
    diag.enqueued_heuristic_paths = heuristic_count
    diag.enqueued_urls_total = len(q)
    logger.info("ENQUEUE initial_heuristic_paths count=%s", heuristic_count)
    logger.info("ENQUEUE total_before_crawl count=%s", len(q))

    while q:
        url, depth = q.popleft()
        if url in seen:
            drop_reasons["seen"] += 1
            diag.dropped_before_fetch_count += 1
            continue
        if depth > 3:
            drop_reasons["depth_limit"] += 1
            diag.dropped_before_fetch_count += 1
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
        if any(x in ctype for x in ["application/pdf", "application/msword", "application/vnd.openxmlformats"]):
            doc_score = relevance_score(url=url, mime_type=ctype, doc_type_hint="DOCUMENT")
            if url not in candidate_urls and should_keep_document(url=url, title="", parent_url="", score=doc_score):
                docs_found.append({"url": url, "title": "", "high_relevance": is_crawl_relevant(url=url, mime_type=ctype, doc_type_hint="DOCUMENT"), "doc_type_hint": "DOCUMENT", "relevance_score": doc_score})
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

        page_text = extract_main_text_from_html(html)
        page_signal = page_text[:4000]
        page_score = relevance_score(text=page_signal, url=url, mime_type=ctype, doc_type_hint="HTML_PAGE")
        if page_score >= 0 and is_crawl_relevant(text=page_signal, url=url, mime_type=ctype, doc_type_hint="HTML_PAGE") and url not in candidate_urls:
            docs_found.append({"url": url, "title": "", "high_relevance": True, "doc_type_hint": "HTML_PAGE", "relevance_score": page_score})
            candidate_urls.add(url)

        for link, title in links:
            if not _same_domain(link, domain):
                drop_reasons["cross_domain"] += 1
                diag.dropped_before_fetch_count += 1
                continue
            if is_hard_denied(link):
                drop_reasons["hard_deny"] += 1
                diag.hard_deny_dropped_count += 1
                diag.dropped_before_fetch_count += 1
                continue
            link_score = relevance_score(text=title, url=link, section=url, doc_type_hint="DOCUMENT" if is_document_url(link) else "HTML_PAGE")
            if is_document_url(link):
                if link not in candidate_urls and should_keep_document(url=link, title=title, parent_url=url, score=link_score):
                    docs_found.append({"url": link, "title": title, "high_relevance": link_score >= 6, "doc_type_hint": "DOCUMENT", "relevance_score": link_score})
                    candidate_urls.add(link)
            elif depth < 3 and (is_crawl_relevant(text=title, url=link, section=url, doc_type_hint="HTML_PAGE") or has_url_hint(link)):
                q.append((link, depth + 1))
            else:
                drop_reasons["low_relevance"] += 1
                diag.dropped_before_fetch_count += 1

        if not q and diag.fetch_attempts < MIN_FETCH_ATTEMPTS_PER_JURISDICTION:
            for p in HEURISTIC_PATHS[:MIN_FETCH_ATTEMPTS_PER_JURISDICTION]:
                candidate = f"{active_base}{p}"
                if candidate not in seen:
                    q.append((candidate, 0))
            if not q:
                notes.append("min_fetch_attempts_unreachable")

    # Section quotas
    docs_found.sort(key=lambda item: (
        1 if is_political_section_url(item.get("url", "")) else 0,
        item.get("relevance_score", 0),
        1 if item.get("doc_type_hint") == "HTML_PAGE" else 0,
    ), reverse=True)

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
        if len(selected) >= MAX_CANDIDATES_PER_DOMAIN:
            break

    docs_found = selected
    diag.drop_reasons_top3 = ",".join(f"{k}:{v}" for k, v in drop_reasons.most_common(3))

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

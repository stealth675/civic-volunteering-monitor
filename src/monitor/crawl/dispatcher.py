from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass
from urllib.parse import urlparse

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


def _normalize_domain(netloc: str) -> str:
    value = (netloc or "").lower()
    return value[4:] if value.startswith("www.") else value


def _same_domain(url: str, domain_netloc: str) -> bool:
    return _normalize_domain(urlparse(url).netloc) == _normalize_domain(domain_netloc)



@dataclass
class CrawlResult:
    pages_fetched: int
    docs_found: list[dict]
    http_errors: int
    timeouts: int
    notes: list[str]


def crawl_jurisdiction(base_url: str, timeout: int, user_agent: str, playwright_enabled: bool = False) -> CrawlResult:
    limiter = DomainRateLimiter(max_per_second=2.0)

    seen: set[str] = set()
    q = deque()
    docs_found: list[dict] = []
    candidate_urls: set[str] = set()
    http_errors = 0
    timeouts = 0
    pages_fetched = 0
    notes: list[str] = []
    domain = _normalize_domain(urlparse(base_url).netloc)

    for sitemap_url in discover_sitemaps(base_url, user_agent, timeout, limiter=limiter):
        try:
            sres = fetch_with_retries(sitemap_url, user_agent, timeout, limiter=limiter)
            if sres.status_code == 200:
                for u in parse_sitemap_urls(sres.content):
                    if not _same_domain(u, domain):
                        continue
                    if is_hard_denied(u):
                        continue
                    if is_crawl_relevant(url=u) or has_url_hint(u):
                        q.append((u, 0))
        except Exception:
            continue

    for p in HEURISTIC_PATHS:
        q.append((f"{base_url}{p}", 0))

    while q:
        url, depth = q.popleft()
        if url in seen or depth > 3:
            continue
        seen.add(url)
        try:
            res = fetch_with_retries(url, user_agent, timeout, limiter=limiter)
        except TimeoutError:
            timeouts += 1
            continue
        except Exception:
            http_errors += 1
            continue

        if res.status_code != 200:
            http_errors += 1
            continue

        ctype = res.headers.get("Content-Type", "").lower()
        if any(x in ctype for x in ["application/pdf", "application/msword", "application/vnd.openxmlformats"]):
            if url not in candidate_urls and should_keep_document(url=url, title="", parent_url="", score=relevance_score(url=url, mime_type=ctype, doc_type_hint="DOCUMENT")):
                docs_found.append({"url": url, "title": "", "high_relevance": is_crawl_relevant(url=url, mime_type=ctype, doc_type_hint="DOCUMENT"), "doc_type_hint": "DOCUMENT"})
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
                continue
            if is_hard_denied(link, title):
                continue
            link_score = relevance_score(text=title, url=link, section=url, doc_type_hint="DOCUMENT" if is_document_url(link) else "HTML_PAGE")
            if is_document_url(link):
                if link not in candidate_urls and should_keep_document(url=link, title=title, parent_url=url, score=link_score):
                    docs_found.append(
                        {
                            "url": link,
                            "title": title,
                            "high_relevance": link_score >= 6,
                            "doc_type_hint": "DOCUMENT",
                            "relevance_score": link_score,
                        }
                    )
                    candidate_urls.add(link)
            elif depth < 3 and (is_crawl_relevant(text=title, url=link, section=url, doc_type_hint="HTML_PAGE") or has_url_hint(link)):
                q.append((link, depth + 1))

    docs_found.sort(key=lambda item: (
        1 if is_political_section_url(item.get("url", "")) else 0,
        item.get("relevance_score", 0),
        1 if item.get("doc_type_hint") == "HTML_PAGE" else 0,
    ), reverse=True)
    if len(docs_found) > MAX_CANDIDATES_PER_DOMAIN:
        notes.append(f"candidate_cap_applied:{MAX_CANDIDATES_PER_DOMAIN}")
    docs_found = docs_found[:MAX_CANDIDATES_PER_DOMAIN]

    return CrawlResult(pages_fetched, docs_found, http_errors, timeouts, notes)

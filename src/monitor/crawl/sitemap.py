from __future__ import annotations

import re
from xml.etree import ElementTree as ET

from monitor.crawl.fetch import fetch_with_retries, DomainRateLimiter

SITEMAP_TAG_RE = re.compile(r"^Sitemap:\s*(\S+)", re.IGNORECASE)


def discover_sitemaps(base_url: str, user_agent: str, timeout: int, limiter: DomainRateLimiter | None = None) -> list[str]:
    robots_url = f"{base_url}/robots.txt"
    sitemaps: list[str] = []
    try:
        resp = fetch_with_retries(robots_url, user_agent, timeout, limiter=limiter)
        if resp.status_code == 200:
            for line in resp.text.splitlines():
                m = SITEMAP_TAG_RE.match(line.strip())
                if m:
                    sitemaps.append(m.group(1).strip())
    except Exception:
        pass
    if not sitemaps:
        sitemaps.append(f"{base_url}/sitemap.xml")
    return sitemaps


def parse_sitemap_urls(xml_content: bytes) -> list[str]:
    root = ET.fromstring(xml_content)
    ns = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
    urls: list[str] = []
    for node in root.findall(f".//{ns}loc"):
        if node.text:
            urls.append(node.text.strip())
    if not urls:
        for node in root.findall(".//loc"):
            if node.text:
                urls.append(node.text.strip())
    return urls

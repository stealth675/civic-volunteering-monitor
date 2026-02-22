from __future__ import annotations

import re
from xml.etree import ElementTree as ET

from monitor.crawl.fetch import DomainRateLimiter, fetch_with_retries

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


def parse_sitemap_entries(xml_content: bytes) -> list[dict]:
    root = ET.fromstring(xml_content)
    ns = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
    entries: list[dict] = []
    for url_node in root.findall(f".//{ns}url") + root.findall(".//url"):
        loc_node = url_node.find(f"{ns}loc")
        if loc_node is None:
            loc_node = url_node.find("loc")
        if loc_node is None or not loc_node.text:
            continue
        lastmod_node = url_node.find(f"{ns}lastmod")
        if lastmod_node is None:
            lastmod_node = url_node.find("lastmod")
        entries.append({"url": loc_node.text.strip(), "lastmod": lastmod_node.text.strip() if lastmod_node is not None and lastmod_node.text else ""})
    if entries:
        return entries
    for loc in root.findall(f".//{ns}loc") + root.findall(".//loc"):
        if loc.text:
            entries.append({"url": loc.text.strip(), "lastmod": ""})
    return entries


def parse_sitemap_urls(xml_content: bytes) -> list[str]:
    return [e["url"] for e in parse_sitemap_entries(xml_content)]

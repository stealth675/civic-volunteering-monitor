from monitor.crawl.sitemap import parse_sitemap_urls


def test_parse_sitemap_urls():
    xml = b"""<?xml version='1.0' encoding='UTF-8'?>
    <urlset xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'>
      <url><loc>https://example.no/a</loc></url>
      <url><loc>https://example.no/b</loc></url>
    </urlset>
    """
    urls = parse_sitemap_urls(xml)
    assert urls == ["https://example.no/a", "https://example.no/b"]

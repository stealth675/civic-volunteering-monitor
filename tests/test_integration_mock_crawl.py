from monitor.crawl.dispatcher import crawl_jurisdiction


class DummyResp:
    def __init__(self, status_code=200, text="", content=b"", headers=None):
        self.status_code = status_code
        self.text = text
        self.content = content or text.encode("utf-8")
        self.headers = headers or {"Content-Type": "text/html"}


def test_crawl_with_mocked_requests(monkeypatch):
    def fake_fetch(url, user_agent, timeout, limiter=None, retries=3):
        if url.endswith("robots.txt"):
            return DummyResp(text="Sitemap: https://example.no/sitemap.xml")
        if url.endswith("sitemap.xml"):
            return DummyResp(content=b"<urlset><url><loc>https://example.no/frivillighet</loc></url></urlset>")
        if "frivillighet" in url:
            return DummyResp(text='<a href="/docs/plan.pdf">Plan</a>')
        if url.endswith("plan.pdf"):
            return DummyResp(headers={"Content-Type": "application/pdf"}, content=b"%PDF-1.4")
        return DummyResp(status_code=404)

    monkeypatch.setattr("monitor.crawl.dispatcher.fetch_with_retries", fake_fetch)
    monkeypatch.setattr("monitor.crawl.sitemap.fetch_with_retries", fake_fetch)
    result = crawl_jurisdiction("https://example.no", timeout=3, user_agent="x")
    assert result.docs_found


def test_recency_prefers_recent_sitemap_entries(monkeypatch):
    xml = b"""
    <urlset xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'>
      <url><loc>https://example.no/old</loc><lastmod>2020-01-01</lastmod></url>
      <url><loc>https://example.no/recent</loc><lastmod>2099-01-01</lastmod></url>
    </urlset>
    """

    def fake_fetch(url, user_agent, timeout, limiter=None, retries=3):
        if url.endswith("robots.txt"):
            return DummyResp(text="Sitemap: https://example.no/sitemap.xml")
        if url.endswith("sitemap.xml"):
            return DummyResp(content=xml)
        if url.endswith("/recent"):
            return DummyResp(text="Frivillighetspolitikk")
        if url.endswith("/old"):
            return DummyResp(text="Frivillighetspolitikk")
        return DummyResp(status_code=404)

    monkeypatch.setattr("monitor.crawl.dispatcher.fetch_with_retries", fake_fetch)
    monkeypatch.setattr("monitor.crawl.sitemap.fetch_with_retries", fake_fetch)
    result = crawl_jurisdiction("https://example.no", timeout=3, user_agent="x")
    urls = [d["url"] for d in result.docs_found]
    assert urls.index("https://example.no/recent") < urls.index("https://example.no/old")


def test_document_inherits_parent_date(monkeypatch):
    def fake_fetch(url, user_agent, timeout, limiter=None, retries=3):
        if url.endswith("robots.txt"):
            return DummyResp(text="Sitemap: https://example.no/sitemap.xml")
        if url.endswith("sitemap.xml"):
            return DummyResp(content=b"<urlset><url><loc>https://example.no/frivillighet</loc></url></urlset>")
        if url.endswith("/frivillighet"):
            return DummyResp(text='<time datetime="2026-02-05"></time><a href="/docs/a.pdf">A</a>')
        if url.endswith("a.pdf"):
            return DummyResp(headers={"Content-Type": "application/pdf"}, content=b"%PDF")
        return DummyResp(status_code=404)

    monkeypatch.setattr("monitor.crawl.dispatcher.fetch_with_retries", fake_fetch)
    monkeypatch.setattr("monitor.crawl.sitemap.fetch_with_retries", fake_fetch)
    result = crawl_jurisdiction("https://example.no", timeout=3, user_agent="x")
    doc = [d for d in result.docs_found if d["url"].endswith("a.pdf")][0]
    assert doc["date_source"] in {"inherited", "header_last_modified", "url_pattern"}


def test_time_budget_stops_domain(monkeypatch):
    calls = {"n": 0}

    def fake_monotonic():
        calls["n"] += 1
        return float(calls["n"]) * 0.2

    def fake_fetch(url, user_agent, timeout, limiter=None, retries=3):
        if url.endswith("robots.txt"):
            return DummyResp(text="Sitemap: https://example.no/sitemap.xml")
        if url.endswith("sitemap.xml"):
            return DummyResp(content=b"<urlset><url><loc>https://example.no/frivillighet</loc></url><url><loc>https://example.no/frivillighet-2</loc></url></urlset>")
        if "frivillighet" in url:
            return DummyResp(text="Frivillighetspolitikk")
        return DummyResp(status_code=404)

    monkeypatch.setattr("monitor.crawl.dispatcher.time.monotonic", fake_monotonic)
    monkeypatch.setattr("monitor.crawl.dispatcher.fetch_with_retries", fake_fetch)
    monkeypatch.setattr("monitor.crawl.sitemap.fetch_with_retries", fake_fetch)
    result = crawl_jurisdiction("https://example.no", timeout=3, user_agent="x", domain_time_budget_seconds=1)
    assert "time_budget_reached" in result.notes

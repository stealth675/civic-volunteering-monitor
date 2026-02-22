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


def test_sitemap_failure_falls_back_to_heuristic_paths(monkeypatch):
    def fake_fetch(url, user_agent, timeout, limiter=None, retries=3):
        if url.endswith("robots.txt"):
            return DummyResp(status_code=500)
        if url.endswith("sitemap.xml"):
            return DummyResp(status_code=500)
        if url.endswith("/frivillighet"):
            return DummyResp(text='<a href="/docs/strategi.pdf">Strategi</a>')
        if url.endswith("strategi.pdf"):
            return DummyResp(headers={"Content-Type": "application/pdf"}, content=b"%PDF")
        return DummyResp(status_code=404)

    monkeypatch.setattr("monitor.crawl.dispatcher.fetch_with_retries", fake_fetch)
    monkeypatch.setattr("monitor.crawl.sitemap.fetch_with_retries", fake_fetch)
    result = crawl_jurisdiction("https://example.no", timeout=3, user_agent="x")

    assert result.pages_fetched >= 1
    assert any(d["url"].endswith("strategi.pdf") for d in result.docs_found)


def test_www_fallback_when_base_fails(monkeypatch):
    calls = []

    def fake_fetch(url, user_agent, timeout, limiter=None, retries=3):
        calls.append(url)
        if url == "https://example.no":
            return DummyResp(status_code=503)
        if url == "https://www.example.no":
            return DummyResp(status_code=200, text='<a href="/frivillighet">Frivillighet</a>')
        if url.endswith("robots.txt"):
            return DummyResp(text="Sitemap: https://www.example.no/sitemap.xml")
        if url.endswith("sitemap.xml"):
            return DummyResp(content=b"<urlset><url><loc>https://www.example.no/frivillighet</loc></url></urlset>")
        if url.endswith("/frivillighet"):
            return DummyResp(text='<a href="/docs/plan.pdf">Plan</a>')
        if url.endswith("plan.pdf"):
            return DummyResp(headers={"Content-Type": "application/pdf"}, content=b"%PDF")
        return DummyResp(status_code=404)

    monkeypatch.setattr("monitor.crawl.dispatcher.fetch_with_retries", fake_fetch)
    monkeypatch.setattr("monitor.crawl.sitemap.fetch_with_retries", fake_fetch)
    result = crawl_jurisdiction("https://example.no", timeout=3, user_agent="x")

    assert "https://www.example.no" in calls
    assert result.diagnostics.base_final_url == "https://www.example.no"


def test_base_403_triggers_playwright_fallback(monkeypatch):
    def fake_fetch(url, user_agent, timeout, limiter=None, retries=3):
        if url in {"https://example.no", "https://www.example.no"}:
            return DummyResp(status_code=403)
        if url.endswith("robots.txt"):
            return DummyResp(text="Sitemap: https://example.no/sitemap.xml")
        if url.endswith("sitemap.xml"):
            return DummyResp(content=b"<urlset></urlset>")
        return DummyResp(status_code=404)

    monkeypatch.setattr("monitor.crawl.dispatcher.fetch_with_retries", fake_fetch)
    monkeypatch.setattr("monitor.crawl.sitemap.fetch_with_retries", fake_fetch)
    monkeypatch.setattr("monitor.crawl.dispatcher.fetch_rendered_html", lambda _url: "<html><body>ok</body></html>")

    result = crawl_jurisdiction("https://example.no", timeout=3, user_agent="x", playwright_enabled=True)
    assert result.diagnostics.base_fetch_status == 200


def test_counters_are_per_jurisdiction_and_reset(monkeypatch):
    def fake_fetch(url, user_agent, timeout, limiter=None, retries=3):
        if "kommune1" in url:
            if url.endswith("robots.txt"):
                return DummyResp(text="Sitemap: https://kommune1.no/sitemap.xml")
            if url.endswith("sitemap.xml"):
                return DummyResp(content=b"<urlset><url><loc>https://kommune1.no/frivillighet</loc></url></urlset>")
            if url.endswith("/frivillighet"):
                return DummyResp(text="ok")
            return DummyResp(status_code=404)
        if "kommune2" in url:
            return DummyResp(status_code=429)
        return DummyResp(status_code=404)

    monkeypatch.setattr("monitor.crawl.dispatcher.fetch_with_retries", fake_fetch)
    monkeypatch.setattr("monitor.crawl.sitemap.fetch_with_retries", fake_fetch)

    r1 = crawl_jurisdiction("https://kommune1.no", timeout=3, user_agent="x")
    r2 = crawl_jurisdiction("https://kommune2.no", timeout=3, user_agent="x")

    assert r1.diagnostics.http_429_count == 0
    assert r2.diagnostics.http_429_count > 0

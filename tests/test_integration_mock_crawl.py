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


def test_crawl_keeps_document_candidates_even_when_low_relevance(monkeypatch):
    def fake_fetch(url, user_agent, timeout, limiter=None, retries=3):
        if url.endswith("robots.txt"):
            return DummyResp(text="Sitemap: https://example.no/sitemap.xml")
        if url.endswith("sitemap.xml"):
            return DummyResp(content=b"<urlset><url><loc>https://example.no/frivillighet</loc></url></urlset>")
        if "frivillighet" in url:
            return DummyResp(text='<a href="/docs/budsjett-2026.pdf">Budsjett 2026</a>')
        if url.endswith("budsjett-2026.pdf"):
            return DummyResp(headers={"Content-Type": "application/pdf"}, content=b"%PDF-1.4")
        return DummyResp(status_code=404)

    monkeypatch.setattr("monitor.crawl.dispatcher.fetch_with_retries", fake_fetch)
    monkeypatch.setattr("monitor.crawl.sitemap.fetch_with_retries", fake_fetch)
    result = crawl_jurisdiction("https://example.no", timeout=3, user_agent="x")

    docs = [d for d in result.docs_found if d["url"].endswith("budsjett-2026.pdf")]
    assert docs
    assert docs[0]["high_relevance"] is False

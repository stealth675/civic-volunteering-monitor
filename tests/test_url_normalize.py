from monitor.ingest.url_normalize import normalize_website_url


def test_normalize_add_https_and_strip():
    assert normalize_website_url("example.no/") == "https://example.no"


def test_normalize_keeps_domain_only():
    assert normalize_website_url("http://www.kommune.no/politikk") == "https://www.kommune.no"

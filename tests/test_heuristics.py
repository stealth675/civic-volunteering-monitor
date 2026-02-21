from monitor.crawl.heuristics import has_url_hint, is_crawl_relevant, is_llm_candidate, relevance_score


def test_relevance_score_bokmaal():
    text = "Kommunen vedtar frivillighetsstrategi med mål og tiltak for samarbeid med frivillig sektor"
    assert relevance_score(text) >= 4
    assert is_llm_candidate(text)


def test_relevance_score_nynorsk():
    text = "Heilskapleg plan for deltaking i fritidsaktivitetar i lag og foreiningar"
    assert is_crawl_relevant(text)


def test_negative_terms_penalized():
    text = "Møtereferat og protokoll for utvalssak"
    assert relevance_score(text) < 1
    assert not is_crawl_relevant(text)


def test_url_hint_catches_service_paths():
    assert has_url_hint("https://lindesnes.kommune.no/tjenester/kultur-idrett-og-fritid/frivillighet/frivillighetspolitikk/")

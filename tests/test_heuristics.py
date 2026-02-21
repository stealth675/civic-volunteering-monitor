from monitor.crawl.heuristics import is_crawl_relevant, is_llm_candidate, relevance_score


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

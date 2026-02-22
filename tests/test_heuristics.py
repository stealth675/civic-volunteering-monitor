from monitor.crawl.heuristics import (
    has_url_hint,
    is_crawl_relevant,
    is_hard_denied,
    is_llm_candidate,
    is_political_section_url,
    relevance_score,
    should_keep_document,
)


def test_protokoll_is_positive_signal():
    score = relevance_score(
        text="Protokoll fra møtebok med vedtak i utvalg",
        url="https://kommune.no/moter-og-saker/utvalg/protokoll-12-2026.pdf",
        title="Protokoll og saksliste",
        doc_type_hint="DOCUMENT",
    )
    assert score >= 6
    assert is_llm_candidate(
        text="Protokoll fra møtebok med vedtak i utvalg",
        url="https://kommune.no/moter-og-saker/utvalg/protokoll-12-2026.pdf",
        title="Protokoll og saksliste",
        doc_type_hint="DOCUMENT",
    )


def test_frivillighetsplattform_scores_high():
    score = relevance_score(
        text="Frivillighetsplattform og frivillighetspolitikk med tiltak for fritidserklæringen",
        url="https://kommune.no/politikk/frivillighet/frivillighetsplattform",
    )
    assert score >= 8


def test_fritidserklaering_llm_candidate():
    assert is_llm_candidate(
        text="Handlingsplan for Fritidserklæringen og organiserte fritidsaktiviteter",
        url="https://kommune.no/planer/frivillighetspolitikk",
        title="Temaplan frivillighet",
    )


def test_hard_denylist_kart_dropped_early():
    assert is_hard_denied("https://kommune.no/kart/plankart-reguleringsplan.pdf")
    assert not should_keep_document("https://kommune.no/kart/plankart-reguleringsplan.pdf", "Plankart")


def test_hard_denylist_bygg_eiendom_dropped_early():
    assert is_hard_denied("https://kommune.no/byggesak/nabovarsel-gnr-12-bnr-34.pdf")


def test_reguleringsplan_text_scores_negative():
    score = relevance_score(
        text="Detaljreguleringsplan med plankart og matrikkel",
        url="https://kommune.no/plan/byggesak/reguleringsplan-123",
    )
    assert score < 0
    assert not is_crawl_relevant(
        text="Detaljreguleringsplan med plankart og matrikkel",
        url="https://kommune.no/plan/byggesak/reguleringsplan-123",
    )


def test_documents_under_moter_og_saker_prioritized():
    assert should_keep_document(
        url="https://kommune.no/storage/protokoll-2026.pdf",
        title="Protokoll utvalg",
        parent_url="https://kommune.no/moter-og-saker",
    )


def test_documents_under_innsyn_prioritized():
    assert should_keep_document(
        url="https://kommune.no/files/saksframlegg-42.pdf",
        title="Saksframlegg",
        parent_url="https://kommune.no/innsyn/politiske-saker",
    )


def test_arrangementstilskudd_scores_low():
    score = relevance_score(
        text="Arrangementstilskudd for enkeltarrangement i sommerferien",
        url="https://kommune.no/tilskudd/arrangementstilskudd",
    )
    assert score < 3
    assert not is_llm_candidate(
        text="Arrangementstilskudd for enkeltarrangement i sommerferien",
        url="https://kommune.no/tilskudd/arrangementstilskudd",
    )


def test_url_hints_and_political_section_matchers():
    assert has_url_hint("https://kommune.no/politikk/moter-og-saker/sakspapirer")
    assert is_political_section_url("https://kommune.no/innsyn/utvalg")


def test_nynorsk_url_hints_supported():
    assert has_url_hint("https://kommune.no/hoyring/planar-og-strategiar/frivillegheit")


def test_nynorsk_political_section_matchers():
    assert is_political_section_url("https://kommune.no/mote-og-saker/utval")

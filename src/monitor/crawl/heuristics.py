from __future__ import annotations

import re

DISCOVERY_PATHS = {
    "political_meetings": [
        "/politikk",
        "/politikk-og-organisasjon",
        "/moter",
        "/mote",
        "/moter-og-saker",
        "/mote-og-saker",
        "/saker",
        "/sak",
        "/innsyn",
        "/postliste",
        "/rad-og-utvalg",
        "/rad-og-utval",
        "/utvalg",
        "/kommunestyret",
        "/formannskap",
        "/saksdokument",
    ],
    "planning_strategy": [
        "/planer",
        "/planar",
        "/planer-og-strategier",
        "/planar-og-strategiar",
        "/strategi",
        "/strategiar",
        "/planstrategi",
        "/horing",
        "/hoyring",
        "/dokumenter",
        "/dokument",
        "/dokumentarkiv",
    ],
    "volunteering": [
        "/frivillighet",
        "/frivillegheit",
        "/frivillig",
        "/friviljug",
        "/frivilligsentral",
        "/frivilligsentralen",
        "/fritid",
        "/kultur-idrett-og-fritid",
        "/kultur-idrett-og-fritidstilbod",
        "/tjenester/frivillighet",
        "/tjenester/kultur-idrett-og-fritid/frivillighet",
    ],
}

HEURISTIC_PATHS = sorted(set(["/"] + [p for paths in DISCOVERY_PATHS.values() for p in paths]))

URL_HINT_KEYWORDS = [
    "frivillighet", "frivillig", "frivillighets", "fritidserklaering", "fritidserkl",
    "kultur", "idrett", "fritid", "moter", "mote", "saker", "sak", "innsyn",
    "tilskudd", "tilskot", "strategi", "strategiar", "plan", "planar", "politikk",
    "sakspapir", "saksframlegg", "protokoll", "motebok", "møtebok",
    "frivilleg", "friviljug", "hoyring", "høyring",
]

THEME_KEYWORDS = [
    "frivillighet", "frivillig", "frivillige", "friviljug", "friviljuge",
    "frivillighetspolitikk", "frivillighetsmelding", "frivillighetsplattform",
    "plattform for samspill og samarbeid mellom frivillig og kommunal sektor",
    "frivillig sektor", "sivilsamfunn", "organisasjonsliv",
    "frivilligsentral", "frivilligsentralen",
    "frivillige organisasjoner", "frivillige organisasjonar",
    "lag og foreninger", "lag og foreiningar", "foreningsliv", "foreiningsliv",
    "organiserte fritidsaktiviteter", "organiserte fritidsaktivitetar",
    "fritidserklæringen", "fritidserklaeringa", "fritidserklæringa",
    "fritidsaktivitet", "fritidsaktivitetar", "fritidstilbud", "fritidstilbod",
    "inkludering i fritid",
    "deltakelse", "deltaking", "inkludering", "utenforskap", "utanforskap",
]

GOVERNANCE_KEYWORDS = [
    "strategi", "plan", "handlingsplan", "politikk", "policy",
    "temaplan", "planstrategi", "melding", "plattform",
    "overordnet", "heilskapleg", "helhetlig", "mål", "tiltak", "prioritering",
]

POLITICAL_DOC_TYPE_KEYWORDS = [
    "sakspapirer", "sakspapir", "saksframlegg", "saksfremlegg", "saksutredning", "saksutgreiing",
    "innstilling", "vedtak", "protokoll", "møteinnkalling", "møtereferat", "motebok", "møtebok",
    "sakslisten", "saksliste", "referat", "møteprotokoll",
]

COLLABORATION_KEYWORDS = [
    "samarbeid", "samspel", "samspill", "partnerskap", "samhandling",
    "kommune frivillig sektor", "fylkeskommune frivillig sektor",
]

NEGATIVE_KEYWORDS = [
    "anbud", "konkurransegrunnlag", "byggesak", "byggesøknad", "dispensasjon",
    "nabovarsel", "situasjonsplan", "matrikkel", "eiendom", "eigedom", "gnr", "bnr",
    "reguleringsplan", "plankart", "adresse", "oppmåling", "delingstillatelse",
    "arrangementstilskudd", "arrangementstilskot", "enkeltarrangement", "eventstøtte",
]

HARD_DENYLIST_CONTAINS = [
    "/kart", "/map", "kartinnsyn", "plankart", "reguleringsplan", "reguleringsplankart",
    "byggesak", "byggesoknad", "byggesøknad", "matrikkel", "eiendom", "eigedom",
    "nabovarsel", "situasjonsplan", "dispensasjon", "oppmaling", "oppmåling", "gnr", "bnr",
]

HARD_DENYLIST_REGEX = [
    re.compile(r"(?:/|_|-|\b)(?:gnr|bnr)\s*\d+", re.IGNORECASE),
    re.compile(r"\b(?:kart|plankart|reguleringsplan)\b", re.IGNORECASE),
    re.compile(r"\b(?:byggesak|byggesøknad|byggesoknad|nabovarsel|situasjonsplan|dispensasjon)\b", re.IGNORECASE),
]

POLITICAL_SECTION_REGEX = re.compile(
    r"/(?:moter(?:-og-saker)?|mote(?:-og-saker)?|saker|sak|innsyn|postliste|rad-og-utvalg|rad-og-utval|utvalg|utval|kommunestyret|formannskap|politikk|saksdokument)",
    re.IGNORECASE,
)

LLM_RELEVANCE_THRESHOLD = 6
CRAWL_RELEVANCE_THRESHOLD = 2


def is_document_url(url: str) -> bool:
    lowered = url.lower().split("?")[0]
    return lowered.endswith(".pdf") or lowered.endswith(".docx") or lowered.endswith(".doc")


def is_hard_denied(url: str, title: str = "") -> bool:
    parsed = (url or "").lower().split("?", 1)[0]
    if any(term in parsed for term in HARD_DENYLIST_CONTAINS):
        return True
    if any(pattern.search(parsed) for pattern in HARD_DENYLIST_REGEX):
        return True
    filename = parsed.rsplit("/", 1)[-1]
    return any(term in filename for term in ["plankart", "reguleringsplan", "byggesak", "matrikkel", "nabovarsel"])


def is_political_section_url(url: str) -> bool:
    return bool(POLITICAL_SECTION_REGEX.search((url or "").lower()))


def _hits(value: str, keywords: list[str]) -> list[str]:
    return [k for k in keywords if k in value]


def relevance_details(
    text: str = "",
    *,
    url: str = "",
    title: str = "",
    section: str = "",
    mime_type: str = "",
    doc_type_hint: str = "",
) -> dict:
    value = " ".join([text or "", url or "", title or "", section or "", mime_type or "", doc_type_hint or ""]).lower()
    theme_hits = _hits(value, THEME_KEYWORDS)
    governance_hits = _hits(value, GOVERNANCE_KEYWORDS)
    political_hits = _hits(value, POLITICAL_DOC_TYPE_KEYWORDS)
    collab_hits = _hits(value, COLLABORATION_KEYWORDS)
    negative_hits = _hits(value, NEGATIVE_KEYWORDS)

    theme_match = bool(theme_hits)
    political_match = bool(political_hits)
    in_political_section = is_political_section_url(url) or is_political_section_url(section)

    score = 0
    if theme_match:
        score += 5
    if governance_hits:
        score += 2
    if collab_hits:
        score += 2

    # political boosts are conditional on theme
    if in_political_section:
        score += 1
        if theme_match:
            score += 1
    if political_match and theme_match:
        score += 2
    elif political_match:
        score += 0

    if is_document_url(url) and mime_type.lower().startswith("application/"):
        score += 1
    if negative_hits:
        score -= 4
    if "arrangement" in value and "tilskudd" in value:
        score -= 3
    if is_hard_denied(url, title):
        score -= 8

    return {
        "score": score,
        "theme_match": theme_match,
        "theme_hits": theme_hits,
        "political_match": political_match,
        "political_hits": political_hits,
        "in_political_section": in_political_section,
    }


def relevance_score(text: str = "", **kwargs) -> int:
    return relevance_details(text, **kwargs)["score"]


def is_crawl_relevant(text: str = "", **kwargs) -> bool:
    return relevance_score(text, **kwargs) >= CRAWL_RELEVANCE_THRESHOLD


def is_llm_candidate(text: str = "", **kwargs) -> bool:
    details = relevance_details(text, **kwargs)
    return details["theme_match"] and details["score"] >= LLM_RELEVANCE_THRESHOLD


def is_review_candidate(text: str = "", **kwargs) -> bool:
    score = relevance_score(text, **kwargs)
    return 3 <= score <= 5


def should_keep_document(url: str, title: str = "", parent_url: str = "", score: int | None = None) -> bool:
    if is_hard_denied(url, title):
        return False
    if is_political_section_url(parent_url) or is_political_section_url(url):
        return True
    return (score if score is not None else relevance_score(url=url, title=title, section=parent_url, doc_type_hint="DOCUMENT")) >= CRAWL_RELEVANCE_THRESHOLD


def has_url_hint(url: str) -> bool:
    value = (url or "").lower()
    return any(k in value for k in URL_HINT_KEYWORDS)

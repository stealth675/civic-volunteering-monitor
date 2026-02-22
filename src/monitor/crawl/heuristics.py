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

HEURISTIC_PATHS = ["/"] + [p for paths in DISCOVERY_PATHS.values() for p in paths]

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
    "sakslisten", "saksliste", "handlingsplan", "temaplan", "strategi", "planstrategi",
    "rapport", "analyse", "evaluering", "utredning", "utgreiing",
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
    r"/(?:moter(?:-og-saker)?|mote(?:-og-saker)?|saker|sak|innsyn|postliste|rad-og-utvalg|rad-og-utval|utvalg|utval|kommunestyret|formannskap|politikk)",
    re.IGNORECASE,
)

LLM_RELEVANCE_THRESHOLD = 6
CRAWL_RELEVANCE_THRESHOLD = 2
MAX_CANDIDATES_PER_DOMAIN = 120


def is_document_url(url: str) -> bool:
    lowered = url.lower().split("?")[0]
    return lowered.endswith(".pdf") or lowered.endswith(".docx") or lowered.endswith(".doc")


def is_hard_denied(url: str, title: str = "") -> bool:
    parsed = (url or "").lower().split("?", 1)[0]
    pathish = parsed
    if any(term in pathish for term in HARD_DENYLIST_CONTAINS):
        return True
    if any(pattern.search(pathish) for pattern in HARD_DENYLIST_REGEX):
        return True
    # filename-level fallback
    filename = pathish.rsplit("/", 1)[-1]
    return any(term in filename for term in ["plankart", "reguleringsplan", "byggesak", "matrikkel", "nabovarsel"])


def is_political_section_url(url: str) -> bool:
    return bool(POLITICAL_SECTION_REGEX.search((url or "").lower()))


def relevance_score(
    text: str = "",
    *,
    url: str = "",
    title: str = "",
    section: str = "",
    mime_type: str = "",
    doc_type_hint: str = "",
) -> int:
    value = " ".join([text or "", url or "", title or "", section or "", mime_type or "", doc_type_hint or ""]).lower()
    score = 0
    if any(k in value for k in THEME_KEYWORDS):
        score += 3
    if any(k in value for k in GOVERNANCE_KEYWORDS):
        score += 2
    if any(k in value for k in POLITICAL_DOC_TYPE_KEYWORDS):
        score += 3
    if any(k in value for k in COLLABORATION_KEYWORDS):
        score += 2
    in_political_section = is_political_section_url(url) or is_political_section_url(section)
    if in_political_section:
        score += 3
    doc_type_match = any(k in value for k in ["protokoll", "saksliste", "møtebok", "motebok", "møtereferat", "saksframlegg", "saksfremlegg"])
    if in_political_section and doc_type_match:
        score += 3
    if is_document_url(url) and mime_type.lower().startswith("application/"):
        score += 1
    if any(k in value for k in NEGATIVE_KEYWORDS):
        score -= 4
    if "arrangement" in value and "tilskudd" in value:
        score -= 3
    if is_hard_denied(url, title):
        score -= 8
    return score


def is_crawl_relevant(text: str = "", **kwargs) -> bool:
    return relevance_score(text, **kwargs) >= CRAWL_RELEVANCE_THRESHOLD


def is_llm_candidate(text: str = "", **kwargs) -> bool:
    return relevance_score(text, **kwargs) >= LLM_RELEVANCE_THRESHOLD


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

from __future__ import annotations

HEURISTIC_PATHS = [
    "/politikk",
    "/politikk-og-organisasjon",
    "/moter",
    "/moter-og-saker",
    "/saker",
    "/innsyn",
    "/postliste",
    "/aktuelt",
    "/nyheter",
    "/kunngjoringer",
    "/planer",
    "/planer-og-strategier",
    "/strategi",
    "/horing",
    "/dokumenter",
    "/rad-og-utvalg",
    "/frivillighet",
    "/frivilligsentral",
    "/tilskudd",
]

THEME_KEYWORDS = [
    "frivillighet", "frivillig", "frivillige", "friviljug", "friviljuge",
    "frivillig sektor", "sivilsamfunn", "organisasjonsliv",
    "frivillige organisasjoner", "frivillige organisasjonar",
    "lag og foreninger", "lag og foreiningar", "foreningsliv", "foreiningsliv",
    "fritidsaktivitet", "fritidsaktivitetar", "fritidstilbud", "fritidstilbod",
    "deltakelse", "deltaking", "inkludering", "utenforskap", "utanforskap",
]

GOVERNANCE_KEYWORDS = [
    "strategi", "plan", "handlingsplan", "politikk", "policy",
    "overordnet", "heilskapleg", "helhetlig", "mål", "tiltak", "prioritering",
]

COLLABORATION_KEYWORDS = [
    "samarbeid", "samspel", "samspill", "partnerskap", "samhandling",
    "kommune frivillig sektor", "fylkeskommune frivillig sektor",
]

NEGATIVE_KEYWORDS = [
    "protokoll", "saksliste", "møtebok", "møtereferat", "utvalssak",
    "anbud", "konkurransegrunnlag", "reguleringsplan", "byggesak",
    "enkeltarrangement", "arrangementsstøtte", "arrangementstilskot",
]


def is_document_url(url: str) -> bool:
    lowered = url.lower().split("?")[0]
    return lowered.endswith(".pdf") or lowered.endswith(".docx") or lowered.endswith(".doc")


def relevance_score(text: str) -> int:
    value = (text or "").lower()
    score = 0
    if any(k in value for k in THEME_KEYWORDS):
        score += 2
    if any(k in value for k in GOVERNANCE_KEYWORDS):
        score += 2
    if any(k in value for k in COLLABORATION_KEYWORDS):
        score += 2
    if any(k in value for k in NEGATIVE_KEYWORDS):
        score -= 3
    return score


def is_crawl_relevant(text: str) -> bool:
    return relevance_score(text) >= 1


def is_llm_candidate(text: str) -> bool:
    return relevance_score(text) >= 3

from __future__ import annotations

from monitor.classify.llm_client import classify_json
from monitor.classify.prompts import SYSTEM_PROMPT
from monitor.store.dedupe import truncate_for_llm


def classify_document(settings, text: str, metadata: dict) -> dict:
    truncated = truncate_for_llm(text, settings.llm_max_chars)
    prompt = f"""{SYSTEM_PROMPT}
Metadata: {metadata}
Tekst:
{truncated}

JSON-skjema:
- category
- confidence (0-1)
- summary (maks 1200 tegn)
- key_points (3-7)
- mentions_platform_ks_fn (bool)
- mentions_rasisme_diskriminering_inkludering (bool)
- target_groups (liste)
- measures (liste)
- named_entities (liste)
- suggested_followups (liste)
"""
    return classify_json(settings, prompt)

from __future__ import annotations

import re


def clean_text(text: str) -> str:
    return " ".join((text or "").split())


def extract_main_text_from_html(html: str) -> str:
    no_script = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.IGNORECASE)
    no_style = re.sub(r"<style[\s\S]*?</style>", " ", no_script, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", no_style)
    return clean_text(text)

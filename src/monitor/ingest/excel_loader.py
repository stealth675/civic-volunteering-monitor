from __future__ import annotations

import hashlib
from dataclasses import dataclass

import pandas as pd

from monitor.ingest.url_normalize import normalize_website_url


@dataclass
class JurisdictionRow:
    jurisdiction_id: str
    name: str
    type: str
    website: str


REQUIRED_COLUMNS = {"name", "type", "website"}


def load_jurisdictions(excel_path: str) -> tuple[list[JurisdictionRow], list[dict]]:
    df = pd.read_excel(excel_path)
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(f"Mangler kolonner i Excel: {sorted(missing)}")

    valid: list[JurisdictionRow] = []
    invalid: list[dict] = []

    for _, row in df.iterrows():
        name = str(row.get("name", "")).strip()
        jtype = str(row.get("type", "")).strip()
        website_raw = str(row.get("website", "")).strip()
        jurisdiction_id = str(row.get("jurisdiction_id", "")).strip()
        if not jurisdiction_id:
            key = f"{name}|{jtype}|{website_raw}".lower()
            jurisdiction_id = hashlib.md5(key.encode("utf-8")).hexdigest()[:12]

        try:
            website = normalize_website_url(website_raw)
            valid.append(JurisdictionRow(jurisdiction_id, name, jtype, website))
        except Exception as exc:
            invalid.append(
                {
                    "jurisdiction_id": jurisdiction_id,
                    "name": name,
                    "type": jtype,
                    "website": website_raw,
                    "error": str(exc),
                }
            )
    return valid, invalid

from __future__ import annotations

import logging
import pandas as pd

logger = logging.getLogger(__name__)


def export_csv_xlsx(rows: list[dict], csv_path: str, xlsx_path: str) -> None:
    df = pd.DataFrame(rows)
    df.to_csv(csv_path, index=False)
    try:
        df.to_excel(xlsx_path, index=False)
    except Exception as exc:
        logger.warning("Kunne ikke skrive XLSX-rapport %s: %s", xlsx_path, exc)

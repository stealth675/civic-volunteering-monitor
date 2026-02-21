from __future__ import annotations

import pandas as pd


def export_csv_xlsx(rows: list[dict], csv_path: str, xlsx_path: str) -> None:
    df = pd.DataFrame(rows)
    df.to_csv(csv_path, index=False)
    df.to_excel(xlsx_path, index=False)

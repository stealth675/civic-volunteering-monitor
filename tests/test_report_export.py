from pathlib import Path

import pandas as pd

from monitor.report.export_excel import export_csv_xlsx


def test_export_csv_even_if_xlsx_fails(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(pd.DataFrame, "to_excel", lambda self, *args, **kwargs: (_ for _ in ()).throw(RuntimeError("xlsx fail")))

    csv_path = tmp_path / "a.csv"
    xlsx_path = tmp_path / "a.xlsx"

    export_csv_xlsx([{"a": 1}], str(csv_path), str(xlsx_path))

    assert csv_path.exists()
    assert not xlsx_path.exists()

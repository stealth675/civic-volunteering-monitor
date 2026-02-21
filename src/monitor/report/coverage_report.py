from __future__ import annotations

from monitor.report.export_excel import export_csv_xlsx


def write_coverage_report(rows: list[dict], output_dir: str, run_id: int) -> tuple[str, str]:
    csv_path = f"{output_dir}/coverage_run_{run_id}.csv"
    xlsx_path = f"{output_dir}/coverage_run_{run_id}.xlsx"
    export_csv_xlsx(rows, csv_path, xlsx_path)
    return csv_path, xlsx_path

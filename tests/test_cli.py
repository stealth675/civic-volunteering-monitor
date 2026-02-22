import argparse
import csv
from types import SimpleNamespace

from monitor import cli
from monitor.store.db import connect, init_db


def test_main_accepts_prefixed_monitor(monkeypatch):
    captured = {}

    def fake_cmd(args):
        captured["excel"] = args.excel

    parser = argparse.ArgumentParser(prog="monitor")
    sub = parser.add_subparsers(dest="command", required=True)
    p_ing = sub.add_parser("ingest")
    p_ing.add_argument("--excel", required=True)
    p_ing.set_defaults(func=fake_cmd)

    monkeypatch.setattr(cli, "build_parser", lambda: parser)
    cli.main(["monitor", "ingest", "--excel", "input.xlsx"])

    assert captured["excel"] == "input.xlsx"


def test_extract_text_for_document_pdf_parse_error(monkeypatch):
    def fail_pdf(_content):
        raise RuntimeError("cryptography>=3.1 is required for AES algorithm")

    monkeypatch.setattr(cli, "extract_pdf_text", fail_pdf)
    text, needs_ocr = cli._extract_text_for_document("pdf", b"%PDF", "", "https://example.no/file.pdf")

    assert text == ""
    assert needs_ocr is True


def test_extract_text_for_document_docx(monkeypatch):
    monkeypatch.setattr(cli, "extract_docx_text", lambda _content: "dok")

    text, needs_ocr = cli._extract_text_for_document("docx", b"bytes", "", "https://example.no/file.docx")

    assert text == "dok"
    assert needs_ocr is False


def test_cmd_report_uses_latest_document_version_only(tmp_path, monkeypatch):
    db_path = tmp_path / "db.sqlite"
    conn = connect(f"sqlite:///{db_path}")
    init_db(conn)

    conn.execute("INSERT INTO jurisdictions(jurisdiction_id,name,type,website) VALUES (?,?,?,?)", ("k1", "Kommune", "kommune", "https://k.no"))
    conn.execute("INSERT INTO sources(id,jurisdiction_id,url,title) VALUES (?,?,?,?)", (1, "k1", "https://k.no/doc.pdf", "Doc"))
    conn.execute("INSERT INTO documents(id,source_id,doc_type) VALUES (?,?,?)", (1, 1, "PDF"))
    conn.execute(
        "INSERT INTO document_versions(id,document_id,content_hash,first_seen,last_seen,last_modified,llm_json) VALUES (?,?,?,?,?,?,?)",
        (1, 1, "h1", "2026-01-01", "2026-01-01", "Mon, 01 Jan 2026 00:00:00 GMT", '{"category":"old"}'),
    )
    conn.execute(
        "INSERT INTO document_versions(id,document_id,content_hash,first_seen,last_seen,last_modified,llm_json) VALUES (?,?,?,?,?,?,?)",
        (2, 1, "h2", "2026-01-01", "2026-02-01", "Mon, 01 Feb 2026 00:00:00 GMT", '{"category":"new"}'),
    )
    conn.execute("INSERT INTO crawl_runs(id, started_at, finished_at) VALUES (1, 'x', 'y')")
    conn.commit()

    monkey_settings = SimpleNamespace(db_url=f"sqlite:///{db_path}")
    monkeypatch.setattr(cli, "load_settings", lambda: monkey_settings)

    args = SimpleNamespace(run_id=1, output=str(tmp_path))
    cli.cmd_report(args)

    csv_path = tmp_path / "findings_run_1.csv"
    with csv_path.open() as fh:
        rows = list(csv.DictReader(fh))

    assert len(rows) == 1
    assert rows[0]["category"] == "new"
    assert rows[0]["first_seen"] == "2026-01-01"
    assert rows[0]["last_seen"] == "2026-02-01"

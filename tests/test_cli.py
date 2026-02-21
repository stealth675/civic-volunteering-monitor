import argparse

from monitor import cli


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

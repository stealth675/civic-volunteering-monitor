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

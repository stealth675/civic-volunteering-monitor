from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path


from monitor.classify.classify_doc import classify_document
from monitor.config import load_settings
from monitor.crawl.dispatcher import crawl_jurisdiction
from monitor.crawl.fetch import DomainRateLimiter, fetch_with_retries
from monitor.crawl.heuristics import is_llm_candidate, relevance_score
from monitor.ingest.excel_loader import load_jurisdictions
from monitor.logging_setup import setup_logging
from monitor.parse.content_clean import extract_main_text_from_html
from monitor.parse.doc_text import extract_docx_text
from monitor.parse.pdf_text import extract_pdf_text
from monitor.report.coverage_report import write_coverage_report
from monitor.report.findings_report import write_findings_report
from monitor.store.blob_store import store_blob
from monitor.store.db import (
    connect,
    create_run,
    finish_run,
    get_or_create_document,
    get_or_create_source,
    init_db,
    insert_status,
    upsert_document_version,
    upsert_jurisdiction,
)
from monitor.store.dedupe import sha256_bytes
from monitor.store.models import COVERAGE_STATUS_FAIL, COVERAGE_STATUS_OK, COVERAGE_STATUS_WARN

logger = logging.getLogger(__name__)


def _doc_ext_and_type(url: str, content_type: str) -> tuple[str, str]:
    u = url.lower()
    if u.endswith(".pdf") or "pdf" in content_type:
        return "pdf", "PDF"
    if u.endswith(".docx") or "wordprocessingml" in content_type:
        return "docx", "DOCX"
    return "html", "HTML"


def cmd_ingest(args):
    settings = load_settings()
    conn = connect(settings.db_url)
    init_db(conn)
    valid, invalid = load_jurisdictions(args.excel)
    for row in valid:
        upsert_jurisdiction(conn, row)
    print(f"Ingest OK: {len(valid)} gyldige, {len(invalid)} ugyldige")


def cmd_run(args):
    settings = load_settings()
    output_dir = args.output
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    conn = connect(settings.db_url)
    init_db(conn)
    run_id = create_run(conn)
    setup_logging(run_id, output_dir)

    valid, invalid = load_jurisdictions(args.excel)
    coverage_rows = []
    findings_rows = []

    for inv in invalid:
        row = {
            "run_id": run_id,
            "jurisdiction_id": inv["jurisdiction_id"],
            "name": inv["name"],
            "website": inv["website"],
            "status": COVERAGE_STATUS_FAIL,
            "http_errors_count": 0,
            "timeouts_count": 0,
            "pages_fetched": 0,
            "docs_found": 0,
            "docs_downloaded": 0,
            "error_message": inv["error"],
            "notes": "invalid_input",
        }
        coverage_rows.append(row)
        insert_status(conn, row)

    for j in valid:
        upsert_jurisdiction(conn, j)
        docs_downloaded = 0
        try:
            result = crawl_jurisdiction(j.website, settings.request_timeout, settings.user_agent, settings.playwright_enabled)
            limiter = DomainRateLimiter(max_per_second=2.0)

            for item in result.docs_found:
                url = item["url"]
                title = item.get("title", "")
                try:
                    r = fetch_with_retries(url, settings.user_agent, settings.request_timeout, limiter=limiter)
                    if r.status_code != 200:
                        continue
                    ext, dtype = _doc_ext_and_type(url, r.headers.get("Content-Type", ""))
                    content = r.content if ext != "html" else r.text.encode("utf-8")
                    content_hash = sha256_bytes(content)
                    source_id = get_or_create_source(conn, j.jurisdiction_id, url, title)
                    document_id = get_or_create_document(conn, source_id, dtype)

                    text = ""
                    needs_ocr = False
                    if ext == "pdf":
                        text, needs_ocr = extract_pdf_text(content)
                    elif ext == "docx":
                        text = extract_docx_text(content)
                    else:
                        text = extract_main_text_from_html(r.text)

                    blob_path = store_blob(settings.blob_dir, j.jurisdiction_id, content_hash, ext, content)
                    version_id, changed = upsert_document_version(
                        conn,
                        document_id,
                        content_hash,
                        http_status=r.status_code,
                        content_type=r.headers.get("Content-Type"),
                        etag=r.headers.get("ETag"),
                        last_modified=r.headers.get("Last-Modified"),
                        blob_path=blob_path,
                        extracted_text=text,
                        needs_ocr=needs_ocr,
                    )
                    docs_downloaded += 1

                    llm_json = {}
                    llm_status = "not_changed"
                    llm_reason = "Dokumentet er ikke endret siden forrige versjon"
                    rel_signal = f"{title} {url} {text[:4000]}"
                    rel_score = relevance_score(rel_signal)

                    if changed:
                        if not text.strip():
                            llm_status = "skipped_empty_text"
                            llm_reason = "Ingen ekstraherbar tekst"
                        elif not (settings.openai_api_key or settings.azure_openai_api_key):
                            llm_status = "skipped_no_api_key"
                            llm_reason = "Mangler API-nøkkel"
                        elif not is_llm_candidate(rel_signal):
                            llm_status = "skipped_low_relevance"
                            llm_reason = "Lav relevansscore"
                        else:
                            meta = {"url": url, "title": title, "jurisdiction": j.name, "doc_type": dtype}
                            try:
                                llm_json = classify_document(settings, text, meta)
                                conn.execute("UPDATE document_versions SET llm_json=? WHERE id=?", (json.dumps(llm_json, ensure_ascii=False), version_id))
                                conn.commit()
                                llm_status = "classified"
                                llm_reason = "Klassifisert med LLM"
                            except Exception as llm_exc:
                                logger.warning("LLM feilet for %s: %s", url, llm_exc)
                                llm_status = "llm_error"
                                llm_reason = str(llm_exc)

                        findings_rows.append(
                            {
                                "jurisdiction": j.name,
                                "type": j.type,
                                "title": title,
                                "url": url,
                                "doc_type": dtype,
                                "source_kind": item.get("doc_type_hint", "DOCUMENT"),
                                "published_date": "",
                                "first_seen": "",
                                "last_seen": "",
                                "category": llm_json.get("category", ""),
                                "confidence": llm_json.get("confidence", ""),
                                "summary": llm_json.get("summary", ""),
                                "mentions_platform_ks_fn": llm_json.get("mentions_platform_ks_fn", False),
                                "relevance_score": rel_score,
                                "llm_status": llm_status,
                                "llm_reason": llm_reason,
                            }
                        )
                except Exception as exc:
                    logger.warning("dokumentfeil %s: %s", url, exc)

            status = COVERAGE_STATUS_OK if result.http_errors == 0 and result.timeouts == 0 else COVERAGE_STATUS_WARN
            row = {
                "run_id": run_id,
                "jurisdiction_id": j.jurisdiction_id,
                "name": j.name,
                "website": j.website,
                "status": status,
                "http_errors_count": result.http_errors,
                "timeouts_count": result.timeouts,
                "pages_fetched": result.pages_fetched,
                "docs_found": len(result.docs_found),
                "docs_downloaded": docs_downloaded,
                "error_message": "",
                "notes": ";".join(sorted(set(result.notes))),
            }
            coverage_rows.append(row)
            insert_status(conn, row)
        except Exception as exc:
            row = {
                "run_id": run_id,
                "jurisdiction_id": j.jurisdiction_id,
                "name": j.name,
                "website": j.website,
                "status": COVERAGE_STATUS_FAIL,
                "http_errors_count": 0,
                "timeouts_count": 0,
                "pages_fetched": 0,
                "docs_found": 0,
                "docs_downloaded": 0,
                "error_message": str(exc),
                "notes": "crawl_failed",
            }
            coverage_rows.append(row)
            insert_status(conn, row)

    finish_run(conn, run_id)
    cov = write_coverage_report(coverage_rows, output_dir, run_id)
    fin = write_findings_report(findings_rows, output_dir, run_id)
    print(f"run_id={run_id}\ncoverage={cov}\nfindings={fin}")


def cmd_report(args):
    settings = load_settings()
    conn = connect(settings.db_url)
    rows = [dict(r) for r in conn.execute("SELECT * FROM crawl_run_jurisdiction_status WHERE run_id=?", (args.run_id,)).fetchall()]
    c = write_coverage_report(rows, args.output, args.run_id)
    f_rows = []
    query = """
    SELECT s.jurisdiction_id, j.name as jurisdiction, j.type, s.url, s.title, d.doc_type, dv.llm_json
    FROM document_versions dv
    JOIN documents d ON dv.document_id=d.id
    JOIN sources s ON d.source_id=s.id
    LEFT JOIN jurisdictions j ON j.jurisdiction_id=s.jurisdiction_id
    """
    for r in conn.execute(query).fetchall():
        llm = json.loads(r["llm_json"]) if r["llm_json"] else {}
        f_rows.append(
            {
                "jurisdiction": r["jurisdiction"],
                "type": r["type"],
                "title": r["title"],
                "url": r["url"],
                "doc_type": r["doc_type"],
                "source_kind": r["doc_type"],
                "published_date": "",
                "first_seen": "",
                "last_seen": "",
                "category": llm.get("category", ""),
                "confidence": llm.get("confidence", ""),
                "summary": llm.get("summary", ""),
                "mentions_platform_ks_fn": llm.get("mentions_platform_ks_fn", False),
                "relevance_score": "",
                "llm_status": "classified" if llm else "not_classified",
                "llm_reason": "",
            }
        )
    f = write_findings_report(f_rows, args.output, args.run_id)
    print(f"coverage={c}\nfindings={f}")


def cmd_classify(args):
    settings = load_settings()
    conn = connect(settings.db_url)
    rows = conn.execute(
        "SELECT id, extracted_text FROM document_versions WHERE llm_json IS NULL AND COALESCE(extracted_text, '') != ''"
    ).fetchall()
    done = 0
    for r in rows:
        if not (settings.openai_api_key or settings.azure_openai_api_key):
            break
        llm = classify_document(settings, r["extracted_text"], {"run_id": args.run_id})
        conn.execute("UPDATE document_versions SET llm_json=? WHERE id=?", (json.dumps(llm, ensure_ascii=False), r["id"]))
        conn.commit()
        done += 1
    print(f"klassifisert={done}")


def build_parser():
    p = argparse.ArgumentParser(prog="monitor")
    sub = p.add_subparsers(dest="command", required=True)

    p_ing = sub.add_parser("ingest")
    p_ing.add_argument("--excel", required=True)
    p_ing.set_defaults(func=cmd_ingest)

    p_run = sub.add_parser("run")
    p_run.add_argument("--excel", required=True)
    p_run.add_argument("--output", default="data/output")
    p_run.add_argument("--max-concurrency", type=int, default=4)
    p_run.set_defaults(func=cmd_run)

    p_rep = sub.add_parser("report")
    p_rep.add_argument("--run-id", type=int, required=True)
    p_rep.add_argument("--output", default="data/output")
    p_rep.set_defaults(func=cmd_report)

    p_cls = sub.add_parser("classify")
    p_cls.add_argument("--run-id", type=int, required=True)
    p_cls.set_defaults(func=cmd_classify)
    return p


def main():
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

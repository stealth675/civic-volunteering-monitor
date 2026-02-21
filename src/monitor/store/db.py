from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def _sqlite_path(db_url: str) -> str:
    if not db_url.startswith("sqlite:///"):
        raise ValueError("Kun sqlite:/// støttes foreløpig")
    return db_url.replace("sqlite:///", "", 1)


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def connect(db_url: str) -> sqlite3.Connection:
    path = _sqlite_path(db_url)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS jurisdictions (
            id INTEGER PRIMARY KEY,
            jurisdiction_id TEXT UNIQUE,
            name TEXT,
            type TEXT,
            website TEXT
        );
        CREATE TABLE IF NOT EXISTS crawl_runs (
            id INTEGER PRIMARY KEY,
            started_at TEXT,
            finished_at TEXT
        );
        CREATE TABLE IF NOT EXISTS crawl_run_jurisdiction_status (
            id INTEGER PRIMARY KEY,
            run_id INTEGER,
            jurisdiction_id TEXT,
            name TEXT,
            website TEXT,
            status TEXT,
            http_errors_count INTEGER,
            timeouts_count INTEGER,
            pages_fetched INTEGER,
            docs_found INTEGER,
            docs_downloaded INTEGER,
            error_message TEXT,
            notes TEXT
        );
        CREATE TABLE IF NOT EXISTS sources (
            id INTEGER PRIMARY KEY,
            jurisdiction_id TEXT,
            url TEXT,
            title TEXT,
            UNIQUE(jurisdiction_id, url)
        );
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY,
            source_id INTEGER,
            doc_type TEXT
        );
        CREATE TABLE IF NOT EXISTS document_versions (
            id INTEGER PRIMARY KEY,
            document_id INTEGER,
            content_hash TEXT,
            first_seen TEXT,
            last_seen TEXT,
            http_status INTEGER,
            content_type TEXT,
            etag TEXT,
            last_modified TEXT,
            blob_path TEXT,
            extracted_text TEXT,
            needs_ocr INTEGER DEFAULT 0,
            llm_json TEXT
        );
        """
    )
    conn.commit()


def upsert_jurisdiction(conn, row):
    conn.execute(
        """INSERT INTO jurisdictions (jurisdiction_id,name,type,website)
        VALUES (?,?,?,?)
        ON CONFLICT(jurisdiction_id) DO UPDATE SET
          name=excluded.name,type=excluded.type,website=excluded.website""",
        (row.jurisdiction_id, row.name, row.type, row.website),
    )
    conn.commit()


def create_run(conn) -> int:
    cur = conn.execute("INSERT INTO crawl_runs(started_at, finished_at) VALUES (?,?)", (utcnow_iso(), None))
    conn.commit()
    return cur.lastrowid


def finish_run(conn, run_id: int):
    conn.execute("UPDATE crawl_runs SET finished_at=? WHERE id=?", (utcnow_iso(), run_id))
    conn.commit()


def get_or_create_source(conn, jurisdiction_id: str, url: str, title: str) -> int:
    conn.execute("INSERT OR IGNORE INTO sources(jurisdiction_id,url,title) VALUES (?,?,?)", (jurisdiction_id, url, title))
    row = conn.execute("SELECT id FROM sources WHERE jurisdiction_id=? AND url=?", (jurisdiction_id, url)).fetchone()
    conn.commit()
    return row["id"]


def get_or_create_document(conn, source_id: int, doc_type: str) -> int:
    row = conn.execute("SELECT id FROM documents WHERE source_id=?", (source_id,)).fetchone()
    if row:
        return row["id"]
    cur = conn.execute("INSERT INTO documents(source_id, doc_type) VALUES (?,?)", (source_id, doc_type))
    conn.commit()
    return cur.lastrowid


def latest_hash(conn, document_id: int) -> str | None:
    row = conn.execute(
        "SELECT content_hash FROM document_versions WHERE document_id=? ORDER BY id DESC LIMIT 1", (document_id,)
    ).fetchone()
    return row["content_hash"] if row else None


def upsert_document_version(conn, document_id: int, content_hash: str, **kwargs) -> tuple[int, bool]:
    now = utcnow_iso()
    last = conn.execute(
        "SELECT id, content_hash FROM document_versions WHERE document_id=? ORDER BY id DESC LIMIT 1", (document_id,)
    ).fetchone()
    if last and last["content_hash"] == content_hash:
        conn.execute("UPDATE document_versions SET last_seen=? WHERE id=?", (now, last["id"]))
        conn.commit()
        return last["id"], False

    cur = conn.execute(
        """INSERT INTO document_versions(
            document_id,content_hash,first_seen,last_seen,http_status,content_type,etag,last_modified,blob_path,extracted_text,needs_ocr,llm_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            document_id,
            content_hash,
            now,
            now,
            kwargs.get("http_status"),
            kwargs.get("content_type"),
            kwargs.get("etag"),
            kwargs.get("last_modified"),
            kwargs.get("blob_path"),
            kwargs.get("extracted_text"),
            int(bool(kwargs.get("needs_ocr"))),
            kwargs.get("llm_json"),
        ),
    )
    conn.commit()
    return cur.lastrowid, True


def insert_status(conn, payload: dict):
    conn.execute(
        """INSERT INTO crawl_run_jurisdiction_status(
            run_id,jurisdiction_id,name,website,status,http_errors_count,timeouts_count,pages_fetched,docs_found,docs_downloaded,error_message,notes
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            payload["run_id"], payload["jurisdiction_id"], payload["name"], payload["website"], payload["status"],
            payload["http_errors_count"], payload["timeouts_count"], payload["pages_fetched"], payload["docs_found"],
            payload["docs_downloaded"], payload.get("error_message"), payload.get("notes"),
        ),
    )
    conn.commit()

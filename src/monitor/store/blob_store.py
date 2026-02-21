from __future__ import annotations

from pathlib import Path


def store_blob(blob_dir: str, jurisdiction_id: str, content_hash: str, ext: str, data: bytes) -> str:
    path = Path(blob_dir) / jurisdiction_id
    path.mkdir(parents=True, exist_ok=True)
    file_path = path / f"{content_hash}.{ext}"
    file_path.write_bytes(data)
    return str(file_path)

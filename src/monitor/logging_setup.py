from __future__ import annotations

import logging
from pathlib import Path


def setup_logging(run_id: int | None, output_dir: str) -> None:
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    log_name = f"run_{run_id}.log" if run_id else "monitor.log"
    log_path = Path(output_dir) / log_name

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_path, encoding="utf-8"),
        ],
        force=True,
    )

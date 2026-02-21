from __future__ import annotations

import os
from dataclasses import dataclass
from dotenv import load_dotenv


@dataclass
class Settings:
    input_excel_path: str = "data/input/Oversikt-kommuner-fylker.xlsx"
    db_url: str = "sqlite:///data/output/monitor.db"
    blob_dir: str = "data/blob"
    max_concurrency: int = 4
    user_agent: str = "KommunalFrivillighetMonitor/0.1"
    request_timeout: int = 20
    playwright_enabled: bool = False
    openai_provider: str = "openai"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    azure_openai_api_key: str = ""
    azure_openai_endpoint: str = ""
    azure_openai_api_version: str = "2024-05-01-preview"
    azure_openai_deployment: str = ""
    llm_max_chars: int = 24000


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def load_settings() -> Settings:
    load_dotenv()
    return Settings(
        input_excel_path=os.getenv("INPUT_EXCEL_PATH", Settings.input_excel_path),
        db_url=os.getenv("DB_URL", Settings.db_url),
        blob_dir=os.getenv("BLOB_DIR", Settings.blob_dir),
        max_concurrency=int(os.getenv("MAX_CONCURRENCY", str(Settings.max_concurrency))),
        user_agent=os.getenv("USER_AGENT", Settings.user_agent),
        request_timeout=int(os.getenv("REQUEST_TIMEOUT", str(Settings.request_timeout))),
        playwright_enabled=_as_bool(os.getenv("PLAYWRIGHT_ENABLED"), False),
        openai_provider=os.getenv("OPENAI_PROVIDER", Settings.openai_provider),
        openai_api_key=os.getenv("OPENAI_API_KEY", ""),
        openai_model=os.getenv("OPENAI_MODEL", Settings.openai_model),
        azure_openai_api_key=os.getenv("AZURE_OPENAI_API_KEY", ""),
        azure_openai_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT", ""),
        azure_openai_api_version=os.getenv("AZURE_OPENAI_API_VERSION", Settings.azure_openai_api_version),
        azure_openai_deployment=os.getenv("AZURE_OPENAI_DEPLOYMENT", ""),
        llm_max_chars=int(os.getenv("LLM_MAX_CHARS", str(Settings.llm_max_chars))),
    )

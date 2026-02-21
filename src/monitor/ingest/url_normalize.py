from urllib.parse import urlparse


def normalize_website_url(raw: str) -> str:
    value = (raw or "").strip()
    if not value:
        raise ValueError("Tom URL")
    if not value.startswith(("http://", "https://")):
        value = f"https://{value}"
    parsed = urlparse(value)
    if not parsed.netloc:
        raise ValueError(f"Ugyldig URL: {raw}")
    return f"https://{parsed.netloc}".rstrip("/")

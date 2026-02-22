from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

logger = logging.getLogger(__name__)


@dataclass
class SimpleResponse:
    status_code: int
    text: str
    content: bytes
    headers: dict


class DomainRateLimiter:
    def __init__(self, max_per_second: float = 2.0):
        self.max_per_second = max_per_second
        self._last_call: dict[str, float] = {}

    def wait(self, domain: str) -> None:
        now = time.time()
        min_interval = 1.0 / self.max_per_second
        last = self._last_call.get(domain, 0.0)
        sleep_for = min_interval - (now - last)
        if sleep_for > 0:
            time.sleep(sleep_for)
        self._last_call[domain] = time.time()


def _request_headers(user_agent: str) -> dict[str, str]:
    return {
        "User-Agent": user_agent or "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "nb-NO,nb;q=0.9,en;q=0.8",
        "Connection": "keep-alive",
        "Cache-Control": "no-cache",
    }


def _do_get(url: str, user_agent: str, timeout: int) -> SimpleResponse:
    req = Request(url, headers=_request_headers(user_agent))
    with urlopen(req, timeout=timeout) as res:
        content = res.read()
        headers = {k: v for k, v in res.headers.items()}
        ctype = headers.get("Content-Type", "")
        charset = "utf-8"
        if "charset=" in ctype:
            charset = ctype.split("charset=")[-1].split(";")[0].strip()
        text = content.decode(charset, errors="replace")
        return SimpleResponse(status_code=getattr(res, "status", 200), text=text, content=content, headers=headers)


def _sleep_backoff(attempt: int) -> None:
    base = min(8.0, 0.8 * (2 ** (attempt - 1)))
    time.sleep(base + random.uniform(0.0, 0.25))


def fetch_with_retries(url: str, user_agent: str, timeout: int, limiter: DomainRateLimiter | None = None, retries: int = 4):
    domain = urlparse(url).netloc
    limiter = limiter or DomainRateLimiter(max_per_second=2.0)

    for attempt in range(1, retries + 1):
        try:
            limiter.wait(domain)
            return _do_get(url, user_agent, timeout)
        except HTTPError as exc:
            if exc.code in {429, 500, 502, 503, 504} and attempt < retries:
                _sleep_backoff(attempt)
                continue
            return SimpleResponse(status_code=exc.code, text="", content=b"", headers={})
        except URLError as exc:
            if attempt == retries:
                raise TimeoutError(str(exc))
            logger.warning("retrying %s due to %s", url, exc)
            _sleep_backoff(attempt)
    raise RuntimeError("Unexpected retry flow")

from __future__ import annotations

import logging
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


def _do_get(url: str, user_agent: str, timeout: int) -> SimpleResponse:
    req = Request(url, headers={"User-Agent": user_agent})
    with urlopen(req, timeout=timeout) as res:
        content = res.read()
        headers = {k: v for k, v in res.headers.items()}
        ctype = headers.get("Content-Type", "")
        charset = "utf-8"
        if "charset=" in ctype:
            charset = ctype.split("charset=")[-1].split(";")[0].strip()
        text = content.decode(charset, errors="replace")
        return SimpleResponse(status_code=getattr(res, "status", 200), text=text, content=content, headers=headers)


def fetch_with_retries(url: str, user_agent: str, timeout: int, limiter: DomainRateLimiter | None = None, retries: int = 3):
    domain = urlparse(url).netloc
    limiter = limiter or DomainRateLimiter(max_per_second=2.0)

    for attempt in range(1, retries + 1):
        try:
            limiter.wait(domain)
            return _do_get(url, user_agent, timeout)
        except HTTPError as exc:
            if exc.code in {429, 500, 502, 503, 504} and attempt < retries:
                time.sleep(1.5 * attempt)
                continue
            return SimpleResponse(status_code=exc.code, text="", content=b"", headers={})
        except URLError as exc:
            if attempt == retries:
                raise TimeoutError(str(exc))
            logger.warning("retrying %s due to %s", url, exc)
            time.sleep(1.5 * attempt)
    raise RuntimeError("Unexpected retry flow")

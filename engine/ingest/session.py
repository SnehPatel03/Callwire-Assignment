"""Browser-like HTTP sessions for NSE/BSE, which reject bare clients.

A PoliteSession warms up cookies on the exchange homepage, spaces requests out,
retries transient failures with backoff, and rebuilds the session when the
exchange invalidates it (401/429/5xx).
"""
import time

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


class PoliteSession:
    def __init__(self, extra_headers: dict, warm_url: str | None = None, min_gap: float = 1.0):
        self.headers = {
            "User-Agent": USER_AGENT,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            **extra_headers,
        }
        self.warm_url = warm_url
        self.min_gap = min_gap          # minimum seconds between two requests
        self._last_call = 0.0
        self._client: httpx.Client | None = None

    def _rebuild(self) -> None:
        self._client = httpx.Client(headers=self.headers, timeout=30, follow_redirects=True)
        if self.warm_url:
            self._client.get(self.warm_url)  # collect cookies the API expects

    @retry(
        stop=stop_after_attempt(4),
        wait=wait_exponential(min=2, max=30),
        retry=retry_if_exception_type(httpx.HTTPError),
        reraise=True,
    )
    def get(self, url: str, **kwargs) -> httpx.Response:
        if self._client is None:
            self._rebuild()
        pause = self.min_gap - (time.time() - self._last_call)
        if pause > 0:
            time.sleep(pause)
        self._last_call = time.time()

        resp = self._client.get(url, **kwargs)
        if resp.status_code in (401, 429) or resp.status_code >= 500:
            self._rebuild()  # fresh cookies, then tenacity retries
            raise httpx.HTTPStatusError(f"HTTP {resp.status_code}", request=resp.request, response=resp)
        # 403 is returned as-is: retrying a WAF block only burns time.
        return resp

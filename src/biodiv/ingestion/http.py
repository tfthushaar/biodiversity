"""A polite async HTTP client shared by every connector.

The ingestion layer is the only part of the system that talks to third-party APIs, so this is
where the design report's "rate limiting so the platform never overwhelms a third-party API"
lives: a global request-rate cap, a concurrency cap, and retry with backoff that honours
Retry-After.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx

RETRY_STATUS = frozenset({429, 500, 502, 503, 504})
MAX_RETRY_AFTER = 60.0


class RateLimiter:
    """Spaces requests at least 1/per_second apart, across all concurrent callers."""

    def __init__(self, per_second: float) -> None:
        if per_second <= 0:
            raise ValueError("per_second must be positive")
        self._interval = 1.0 / per_second
        self._next = 0.0
        self._lock = asyncio.Lock()

    async def wait(self) -> None:
        async with self._lock:
            now = time.monotonic()
            start = max(now, self._next)
            self._next = start + self._interval
        if start > now:
            await asyncio.sleep(start - now)


class PoliteClient:
    def __init__(
        self,
        *,
        user_agent: str,
        per_second: float = 5.0,
        max_concurrency: int = 5,
        retries: int = 4,
        backoff: float = 1.0,
        timeout: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._client = httpx.AsyncClient(
            headers={"User-Agent": user_agent},
            timeout=timeout,
            transport=transport,
            follow_redirects=True,
        )
        self._limiter = RateLimiter(per_second)
        self._sem = asyncio.Semaphore(max_concurrency)
        self._retries = retries
        self._backoff = backoff

    async def __aenter__(self) -> PoliteClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self._client.aclose()

    def _delay(self, attempt: int, retry_after: str | None) -> float:
        if retry_after and retry_after.isdigit():
            return min(float(retry_after), MAX_RETRY_AFTER)
        return self._backoff * (2**attempt)

    async def get(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        """GET with rate limiting and retries. Raises httpx.HTTPStatusError on a final failure."""
        for attempt in range(self._retries + 1):
            await self._limiter.wait()
            last = attempt == self._retries
            try:
                async with self._sem:
                    resp = await self._client.get(url, params=params, headers=headers)
            except (httpx.TimeoutException, httpx.TransportError):
                if last:
                    raise
                await asyncio.sleep(self._delay(attempt, None))
                continue
            if resp.status_code in RETRY_STATUS and not last:
                await asyncio.sleep(self._delay(attempt, resp.headers.get("Retry-After")))
                continue
            resp.raise_for_status()
            return resp
        raise AssertionError("unreachable")  # pragma: no cover

    async def get_json(self, url: str, params: dict[str, Any] | None = None, **kw: Any) -> Any:
        return (await self.get(url, params, **kw)).json()

    async def get_bytes(self, url: str, params: dict[str, Any] | None = None) -> bytes:
        return (await self.get(url, params)).content

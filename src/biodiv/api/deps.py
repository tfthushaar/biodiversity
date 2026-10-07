"""Shared request dependencies: models, database, and a rate limit. All overridable in tests."""

from __future__ import annotations

import time
from collections import defaultdict, deque
from collections.abc import Iterator
from functools import lru_cache
from pathlib import Path
from threading import Lock

import psycopg
from fastapi import Depends, HTTPException, Request

from biodiv.core.settings import Settings, get_settings
from biodiv.inference.classifier import Embedder, LinearHead, SpeciesClassifier
from biodiv.inference.megadetector import MegaDetector


class ModelRegistry:
    """Loads each model on first use and keeps it. A model that is not configured is reported as
    unavailable instead of crashing the service, so the rest of the API still works."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._cache: dict[str, object] = {}
        self._lock = Lock()

    def _load(self, key: str, factory):
        with self._lock:
            if key not in self._cache:
                self._cache[key] = factory()
            return self._cache[key]

    def _path(self, value: str) -> Path | None:
        return Path(value) if value and Path(value).is_file() else None

    @property
    def detector(self) -> MegaDetector | None:
        path = self._path(self.settings.megadetector_onnx)
        return self._load("detector", lambda: MegaDetector(path)) if path else None

    def _embedder(self) -> Embedder | None:
        path = self._path(self.settings.backbone_onnx)
        return self._load("embedder", lambda: Embedder(path)) if path else None

    def classifier(self, task: str) -> SpeciesClassifier | None:
        head_path = Path(self.settings.heads_dir) / f"{task}.json"
        embedder = self._embedder()
        if embedder is None or not head_path.is_file():
            return None
        return self._load(
            f"head:{task}", lambda: SpeciesClassifier(embedder, LinearHead.load(head_path)))

    def availability(self) -> dict[str, bool]:
        heads = Path(self.settings.heads_dir)
        backbone = self._path(self.settings.backbone_onnx) is not None
        return {
            "detector": self._path(self.settings.megadetector_onnx) is not None,
            "plants": backbone and (heads / "plants.json").is_file(),
            "animals": backbone and (heads / "animals.json").is_file(),
        }


@lru_cache
def _registry() -> ModelRegistry:
    return ModelRegistry(get_settings())


def get_registry() -> ModelRegistry:
    return _registry()


def get_conn() -> Iterator[psycopg.Connection]:
    url = get_settings().database_url
    if not url:
        raise HTTPException(503, "No database is configured for this service.")
    with psycopg.connect(url) as conn:
        yield conn


class RateLimiter:
    """A sliding window per client, in memory. Enough to keep one free instance from being
    hammered; a multi-instance deployment would need a shared store."""

    def __init__(self, per_minute: int) -> None:
        self.per_minute = per_minute
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def check(self, client: str, now: float | None = None) -> float | None:
        """None if allowed, else seconds until the client may try again."""
        now = time.monotonic() if now is None else now
        with self._lock:
            hits = self._hits[client]
            while hits and now - hits[0] >= 60:
                hits.popleft()
            if len(hits) >= self.per_minute:
                return 60 - (now - hits[0])
            hits.append(now)
            return None


@lru_cache
def _limiter() -> RateLimiter:
    return RateLimiter(get_settings().infer_requests_per_minute)


def get_limiter() -> RateLimiter:
    return _limiter()


def client_id(request: Request) -> str:
    # Behind a host's proxy the real client is the first X-Forwarded-For hop.
    forwarded = request.headers.get("x-forwarded-for", "")
    return forwarded.split(",")[0].strip() or (request.client.host if request.client else "?")


def rate_limited(request: Request, limiter: RateLimiter = Depends(get_limiter)) -> None:
    wait = limiter.check(client_id(request))
    if wait is not None:
        raise HTTPException(429, "Too many requests; slow down.",
                            headers={"Retry-After": str(int(wait) + 1)})

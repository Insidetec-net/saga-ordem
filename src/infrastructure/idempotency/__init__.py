"""Idempotency Store — Prevents duplicate request processing."""
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any

from src.infrastructure.serialization import DomainEncoder


class IdempotencyStore(ABC):
    """Abstract idempotency store using set-if-not-exists semantics."""

    @abstractmethod
    async def check_and_store(
        self, key: str, ttl_seconds: int = 86400
    ) -> bool:
        """Returns True if new (stored), False if duplicate."""
        ...

    @abstractmethod
    async def get_result(self, key: str) -> dict[str, Any] | None: ...

    @abstractmethod
    async def store_result(
        self,
        key: str,
        result: dict[str, Any],
        ttl_seconds: int = 86400,
    ) -> None: ...


class InMemoryIdempotency(IdempotencyStore):
    """In-memory idempotency for tests."""

    def __init__(self):
        self._store: dict[str, Any] = {}

    async def check_and_store(
        self, key: str, ttl_seconds: int = 86400
    ) -> bool:
        if key in self._store:
            return False
        self._store[key] = {"status": "processing"}
        return True

    async def get_result(self, key: str) -> dict[str, Any] | None:
        return self._store.get(key)

    async def store_result(
        self,
        key: str,
        result: dict[str, Any],
        ttl_seconds: int = 86400,
    ) -> None:
        self._store[key] = result


class RedisIdempotency(IdempotencyStore):
    """Production idempotency using Redis SET NX (set-if-not-exists)."""

    def __init__(self, redis_client):
        self._redis = redis_client
        self.prefix = "idempotency:"

    async def check_and_store(
        self, key: str, ttl_seconds: int = 86400
    ) -> bool:
        full_key = f"{self.prefix}{key}"
        result = await self._redis.set(
            full_key, "processing", nx=True, ex=ttl_seconds
        )
        return result is True

    async def get_result(self, key: str) -> dict[str, Any] | None:
        full_key = f"{self.prefix}{key}"
        data = await self._redis.get(full_key)
        if data is None:
            return None
        return json.loads(data)

    async def store_result(
        self,
        key: str,
        result: dict[str, Any],
        ttl_seconds: int = 86400,
    ) -> None:
        full_key = f"{self.prefix}{key}"
        await self._redis.set(
            full_key,
            json.dumps(result, cls=DomainEncoder),
            ex=ttl_seconds,
        )

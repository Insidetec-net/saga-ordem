"""Redis Idempotency Store — Prevents duplicate requests across distributed nodes."""
from __future__ import annotations

import json
from typing import Any

from redis.asyncio import Redis

from src.infrastructure.idempotency import IdempotencyStore


class RedisIdempotency(IdempotencyStore):
    """Redis-backed idempotency.

    Uses atomic SET NX (set if not exists) to guarantee that
    only one worker can process a given key.
    """

    def __init__(
        self,
        redis_client: Redis,
        ttl_seconds: int = 86400,  # 24 hours
    ):
        self._redis = redis_client
        self._ttl = ttl_seconds

    async def check_and_store(self, key: str) -> bool:
        """Attempt to lock the idempotency key.

        Returns True if the key was set (meaning it's a new request).
        Returns False if the key already exists.
        """
        idempotency_key = f"idempotency:{key}"
        # SET NX returns True if key was set, False if it already existed
        is_new = await self._redis.set(
            idempotency_key,
            json.dumps({"status": "processing"}),
            nx=True,
            ex=self._ttl,
        )
        return bool(is_new)

    async def store_result(
        self, key: str, result: dict[str, Any]
    ) -> None:
        """Store the final processing result."""
        idempotency_key = f"idempotency:{key}"
        # Overwrite the 'processing' status with actual result
        await self._redis.set(
            idempotency_key,
            json.dumps(result),
            ex=self._ttl,
        )

    async def get_result(self, key: str) -> dict[str, Any] | None:
        """Retrieve the cached result if available."""
        idempotency_key = f"idempotency:{key}"
        data = await self._redis.get(idempotency_key)
        if data:
            return json.loads(data)
        return None

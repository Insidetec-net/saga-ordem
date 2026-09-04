"""Serialization — JSON encoder/decoder for domain objects."""
from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from src.domain import DomainEvent, Money


class DomainEncoder(json.JSONEncoder):
    """Custom JSON encoder that handles domain types."""

    def default(self, obj):
        if isinstance(obj, UUID):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, Decimal):
            return str(obj)
        if isinstance(obj, Money):
            return {"amount": str(obj.amount), "currency": obj.currency}
        if isinstance(obj, DomainEvent):
            return obj.__dict__
        return super().default(obj)


def domain_hook(dct: dict) -> Any:
    """JSON object_hook to reconstruct domain events."""
    if "event_type" not in dct:
        return dct
    # Simplified — full reconstruction handled in event handlers
    return dct

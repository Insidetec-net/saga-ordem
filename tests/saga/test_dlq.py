"""Dead Letter Queue tests."""
import pytest


class TestDeadLetterQueue:
    @pytest.mark.asyncio
    async def test_dlq_captures_failed_events(self, dlq):
        await dlq.enqueue(
            event_type="test_event",
            payload={"data": "test"},
            error="Connection timeout",
        )
        assert dlq.size == 1

        messages = await dlq.get_all()
        assert messages[0]["event_type"] == "test_event"
        assert messages[0]["error"] == "Connection timeout"

    @pytest.mark.asyncio
    async def test_dlq_tracks_retry_count(self, dlq):
        await dlq.enqueue(
            event_type="test_event",
            payload={},
            error="Timeout",
            retry_count=3,
        )
        messages = await dlq.get_all()
        assert messages[0]["retry_count"] == 3

    @pytest.mark.asyncio
    async def test_dlq_multiple_messages(self, dlq):
        await dlq.enqueue("event_a", {}, "error_a")
        await dlq.enqueue("event_b", {}, "error_b")
        assert dlq.size == 2

        messages = await dlq.get_all()
        types = [m["event_type"] for m in messages]
        assert "event_a" in types
        assert "event_b" in types

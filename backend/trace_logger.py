"""
Veridex NBA Platform — Live Execution Trace Logger

Lightweight, additive instrumentation layer that captures structured
trace events as the decision pipeline runs.

Each event records: timestamp, agent name, event type, detail string,
pipeline stage, and a sequence number.

Events are stored in-memory per decision_id and can be:
  1. Streamed in real-time via async generator (for SSE)
  2. Retrieved in bulk (for late-joining clients or replay)

This module has ZERO impact on pipeline control flow — it is purely
observational.  Removing every trace.log() call would change nothing
about the system's behaviour.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import AsyncGenerator


class TraceEvent:
    """Single structured trace event."""

    __slots__ = ("timestamp", "agent", "event", "detail", "stage", "seq")

    def __init__(
        self,
        agent: str,
        event: str,
        detail: str,
        stage: str,
        seq: int,
    ):
        self.timestamp = datetime.now(timezone.utc).strftime("%H:%M:%S.%f")[:-3]
        self.agent = agent
        self.event = event
        self.detail = detail
        self.stage = stage
        self.seq = seq

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "agent": self.agent,
            "event": self.event,
            "detail": self.detail,
            "stage": self.stage,
            "seq": self.seq,
        }


class TraceLogger:
    """
    In-memory trace logger with per-decision event streams.

    Thread-safe for the single-threaded asyncio event loop used by
    FastAPI/uvicorn.  Each decision gets its own event list and set
    of subscriber queues.
    """

    def __init__(self):
        # decision_id → list[TraceEvent]
        self._traces: dict[str, list[TraceEvent]] = {}
        # decision_id → list[asyncio.Queue]  (one per SSE subscriber)
        self._subscribers: dict[str, list[asyncio.Queue]] = {}
        # decision_id → monotonically increasing sequence counter
        self._seq: dict[str, int] = {}

    # ── Public API ─────────────────────────────────────────────────

    def log(
        self,
        decision_id: str,
        agent: str,
        event: str,
        detail: str = "",
        stage: str = "",
    ) -> None:
        """
        Record a single trace event.  One-liner call site.

        This is intentionally synchronous so callers don't need to
        await it — keeps the instrumentation truly zero-friction.
        """
        if decision_id not in self._traces:
            self._traces[decision_id] = []
            self._subscribers[decision_id] = []
            self._seq[decision_id] = 0

        self._seq[decision_id] += 1
        evt = TraceEvent(
            agent=agent,
            event=event,
            detail=detail,
            stage=stage,
            seq=self._seq[decision_id],
        )
        self._traces[decision_id].append(evt)

        # Fan-out to all active SSE subscribers (non-blocking put)
        evt_dict = evt.to_dict()
        for q in self._subscribers[decision_id]:
            try:
                q.put_nowait(evt_dict)
            except asyncio.QueueFull:
                pass  # Drop if subscriber is too slow — acceptable for trace

    def get_trace(self, decision_id: str) -> list[dict]:
        """Return full trace for a decision (for REST endpoint / replay)."""
        events = self._traces.get(decision_id, [])
        return [e.to_dict() for e in events]

    async def subscribe(
        self, decision_id: str
    ) -> AsyncGenerator[dict, None]:
        """
        Async generator that yields trace events as they arrive.

        Used by the SSE endpoint.  Automatically unsubscribes on
        generator close / client disconnect.
        """
        q: asyncio.Queue = asyncio.Queue(maxsize=256)

        # Ensure structures exist
        if decision_id not in self._subscribers:
            self._subscribers[decision_id] = []
            self._traces[decision_id] = []
            self._seq[decision_id] = 0

        self._subscribers[decision_id].append(q)

        try:
            # First, replay any events that already happened
            for evt in self._traces.get(decision_id, []):
                yield evt.to_dict()

            # Then stream new events as they arrive
            while True:
                evt_dict = await asyncio.wait_for(q.get(), timeout=30.0)
                yield evt_dict
        except asyncio.TimeoutError:
            # No events for 30s — assume pipeline finished, close stream
            return
        except (asyncio.CancelledError, GeneratorExit):
            return
        finally:
            # Clean up subscriber
            try:
                self._subscribers[decision_id].remove(q)
            except (ValueError, KeyError):
                pass

    def mark_complete(self, decision_id: str) -> None:
        """
        Signal that the pipeline is done for this decision.

        Sends a sentinel to all subscribers so they can close cleanly.
        """
        sentinel = {
            "timestamp": datetime.now(timezone.utc).strftime("%H:%M:%S.%f")[:-3],
            "agent": "Pipeline",
            "event": "complete",
            "detail": "Pipeline execution finished",
            "stage": "done",
            "seq": self._seq.get(decision_id, 0) + 1,
            "_done": True,
        }
        for q in self._subscribers.get(decision_id, []):
            try:
                q.put_nowait(sentinel)
            except asyncio.QueueFull:
                pass


# ── Global singleton ────────────────────────────────────────────────
trace = TraceLogger()

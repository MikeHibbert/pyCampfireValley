"""Valley event bus — the dev-event stream that feeds the TUI.

Typed events describing what is happening inside the valley:
tool_started/tool_finished/command_output/file_changed/agent_say plus valley
lifecycle and torch events. The bus keeps a bounded in-memory ring so a
newly connected TUI can replay recent history, and every subscriber gets a
live asyncio.Queue. An optional FastAPI app (build_events_app) exposes the
stream as SSE on /events and recent history on /events/recent.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

from fastapi import FastAPI
from fastapi.responses import StreamingResponse

EVENT_TYPES = (
    "valley_started",
    "valley_stopped",
    "torch_received",
    "torch_completed",
    "campfire_assigned",
    "tool_started",
    "tool_finished",
    "command_output",
    "file_changed",
    "agent_say",
    "steward_patrol",
    "leader_say",
)

_RING_DEFAULT = 500


@dataclass
class ValleyEvent:
    type: str
    text: str = ""
    ts: float = field(default_factory=time.time)
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    valley: str = ""
    campfire: str = ""
    torch_id: str = ""
    detail: Dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(asdict(self), default=str)


class EventBus:
    """In-memory pub/sub with a bounded replay ring. Never raises."""

    def __init__(self, ring_size: int = _RING_DEFAULT):
        self._ring: List[ValleyEvent] = []
        self._ring_size = max(10, int(ring_size))
        self._subs: List[asyncio.Queue] = []
        self._counter = 0

    def emit(
        self,
        type: str,
        text: str = "",
        *,
        valley: str = "",
        campfire: str = "",
        torch_id: str = "",
        detail: Optional[Dict[str, Any]] = None,
    ) -> ValleyEvent:
        if type not in EVENT_TYPES:
            type = "agent_say"
        ev = ValleyEvent(
            type=type,
            text=str(text or "")[:2000],
            valley=valley,
            campfire=campfire,
            torch_id=torch_id,
            detail=detail or {},
        )
        self._counter += 1
        self._ring.append(ev)
        if len(self._ring) > self._ring_size:
            del self._ring[: len(self._ring) - self._ring_size]
        for q in list(self._subs):
            try:
                q.put_nowait(ev)
            except Exception:
                pass
        return ev

    def recent(self, limit: int = 100) -> List[ValleyEvent]:
        return list(self._ring[-max(1, int(limit)):])

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=1000)
        self._subs.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        try:
            self._subs.remove(q)
        except Exception:
            pass

    @property
    def subscriber_count(self) -> int:
        return len(self._subs)


def build_events_app(bus: EventBus) -> FastAPI:
    """Tiny FastAPI app: GET /events (SSE live stream), GET /events/recent."""
    app = FastAPI(title="campfirevalley-events")

    @app.get("/events/recent")
    async def recent(limit: int = 100):
        return {"events": [e.to_json() for e in bus.recent(limit)]}

    @app.get("/events")
    async def stream():
        q = bus.subscribe()

        async def gen():
            try:
                yield "retry: 3000\n\n"
                for ev in bus.recent(50):
                    yield f"data: {ev.to_json()}\n\n"
                while True:
                    try:
                        ev = await asyncio.wait_for(q.get(), timeout=15)
                        yield f"data: {ev.to_json()}\n\n"
                    except asyncio.TimeoutError:
                        yield ": keepalive\n\n"
            except asyncio.CancelledError:
                pass
            finally:
                bus.unsubscribe(q)

        return StreamingResponse(gen(), media_type="text/event-stream")

    return app


def run_events_server(bus: EventBus, host: str = "0.0.0.0", port: int = 8020) -> None:
    """Blocking: serve the event stream (call from a thread or a process)."""
    import uvicorn

    uvicorn.run(build_events_app(bus), host=host, port=port, log_level="warning")

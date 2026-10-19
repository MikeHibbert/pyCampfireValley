"""Valley event bus — the dev-event stream that feeds the TUI.

Typed events describing what is happening inside the valley:
tool_started/tool_finished/command_output/file_changed/agent_say plus valley
lifecycle and torch events. The bus keeps a bounded in-memory ring so a
newly connected TUI can replay recent history, and every subscriber gets a
live asyncio.Queue. An optional FastAPI app (build_events_app) exposes the
stream as SSE on /events and recent history on /events/recent.

Tiers (work_206b9187b0): every event carries a `tier` — "ledger" (default:
the full torrent, the durable record) or "live" (only what a person needs at
that moment: state transitions, errors and escalations, final verses not
token deltas, aggregated heartbeats, leader changes, torch receipts). A
small policy function (live_worthy) decides promotion at emit time; workers
keep emitting unchanged.
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

# Two plainly named tiers (work_206b9187b0): "ledger" is the default — the
# full torrent, the durable record. "live" is only what a person needs at
# that moment. Promotion from ledger to live is decided by live_worthy() at
# emit time; explicit tier= on emit() always wins.
TIER_LEDGER = "ledger"
TIER_LIVE = "live"
TIERS = (TIER_LEDGER, TIER_LIVE)


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
    tier: str = TIER_LEDGER

    def to_json(self) -> str:
        return json.dumps(asdict(self), default=str)


def live_worthy(ev: "ValleyEvent") -> bool:
    """Small promotion policy (work_206b9187b0): decide at emit time whether
    an event belongs on the "live" tier — only what a person needs at that
    moment. Everything else stays on the "ledger" tier (the full torrent,
    the durable record). Workers keep emitting unchanged; this runs inside
    EventBus.emit when no explicit tier was passed.

    Live-worthy: state transitions, errors and escalations, final verses
    (not token deltas), aggregated heartbeats, leader changes, torch
    receipts.
    """
    try:
        etype = str(getattr(ev, "type", "") or "")
        detail = getattr(ev, "detail", None) or {}
        text = str(getattr(ev, "text", "") or "")

        # Valley lifecycle = state transitions.
        if etype in ("valley_started", "valley_stopped", "campfire_assigned"):
            return True
        # Torch receipts: a torch arriving or completing is a receipt a
        # person needs; per-campfire torch progress churn is not.
        if etype in ("torch_received", "torch_completed"):
            return True
        # Leader changes / leader words.
        if etype == "leader_say":
            return True
        # Errors and escalations, wherever they surface.
        if etype in ("tool_finished", "command_output") and detail.get("error"):
            return True
        if "error" in etype or "escalat" in etype or "fail" in etype:
            return True
        if detail.get("escalate") or detail.get("level") in ("error", "critical"):
            return True
        # Final verses, not token deltas: a verse/turn completing is live;
        # streaming token deltas are ledger-only.
        if etype == "agent_say" and (detail.get("final") or detail.get("done") or "final" in text.lower()):
            return True
        if "token" in etype or detail.get("delta") is not None or detail.get("token_delta"):
            return False
        # Aggregated heartbeats only: a heartbeat carrying an aggregate
        # summary is live; per-tick heartbeats are ledger-only.
        if "heartbeat" in etype or "heartbeat" in text.lower():
            return bool(detail.get("aggregate") or detail.get("summary") or detail.get("aggregated"))
        # Steward patrol noise stays on the ledger unless it escalates.
        return False
    except Exception:
        # The bus never raises; on any surprise, keep the durable default.
        return False


class EventBus:
    """In-memory pub/sub with a bounded replay ring. Never raises."""

    def __init__(self, ring_size: int = _RING_DEFAULT, leader: str = ""):
        self._ring: List[ValleyEvent] = []
        self._ring_size = max(10, int(ring_size))
        self._subs: List[asyncio.Queue] = []
        self._counter = 0
        self.leader = str(leader or "")

    def emit(
        self,
        type: str,
        text: str = "",
        *,
        valley: str = "",
        campfire: str = "",
        torch_id: str = "",
        detail: Optional[Dict[str, Any]] = None,
        tier: Optional[str] = None,
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
        # Tier (work_206b9187b0): explicit tier= wins; otherwise the small
        # policy function decides promotion at emit time. Workers keep
        # emitting unchanged — they pass no tier and get the policy verdict.
        if tier in TIERS:
            ev.tier = tier
        else:
            ev.tier = TIER_LIVE if live_worthy(ev) else TIER_LEDGER
        self._counter += 1
        self._ring.append(ev)
        if len(self._ring) > self._ring_size:
            del self._ring[: len(self._ring) - self._ring_size]
        for sub in list(self._subs):
            # Tiered subscriptions are stored as (queue, tier) tuples and
            # plain subscriptions as the bare queue (work_206b9187b0).
            # Deliver to a tiered subscriber only when the event's tier
            # matches; an untiered subscriber keeps receiving the full
            # torrent (ledger + live), unchanged behavior.
            q = sub[0] if isinstance(sub, tuple) else sub
            want = sub[1] if isinstance(sub, tuple) else None
            if want is not None and ev.tier != want:
                continue
            try:
                q.put_nowait(ev)
            except Exception:
                pass
        return ev

    def recent(self, limit: int = 100, tier: Optional[str] = None) -> List[ValleyEvent]:
        """Recent events, optionally filtered to one tier (work_206b9187b0):
        a live consumer asks for tier="live"; the durable record reads all."""
        evs = list(self._ring[-max(1, int(limit)):])
        if tier in TIERS:
            evs = [e for e in evs if e.tier == tier]
        return evs

    def subscribe(self, tier: Optional[str] = None) -> asyncio.Queue:
        """Subscribe to the bus. With tier="live" the queue receives only
        live-tier events (what a person needs at that moment); with no tier
        it receives the full torrent (ledger + live), unchanged behavior."""
        q: asyncio.Queue = asyncio.Queue(maxsize=1000)
        if tier in TIERS:
            self._subs.append((q, tier))  # type: ignore[arg-type]
        else:
            self._subs.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        try:
            for i, sub in enumerate(list(self._subs)):
                qt = sub[0] if isinstance(sub, tuple) else sub
                if qt is q:
                    del self._subs[i]
                    return
        except Exception:
            pass

    @property
    def subscriber_count(self) -> int:
        return len(self._subs)


def build_events_app(bus: EventBus, send_torch=None) -> FastAPI:
    """Tiny FastAPI app: GET /events (SSE live stream), GET /events/recent."""
    app = FastAPI(title="campfirevalley-events")

    @app.get("/events/leader")
    async def leader():
        return {"leader": bus.leader or "the valley"}

    @app.post("/torchs")
    async def send_torch_route(body: dict):
        """Folder work pipe: TUI sends a folder torch (objective + context + folder)."""
        if send_torch is None:
            return {"error": "no torch sender wired on this valley"}
        if not str((body or {}).get("objective") or "").strip():
            return {"error": "objective is required"}
        try:
            import inspect as _inspect
            result = send_torch(body or {})
            if _inspect.isawaitable(result):
                result = await result
            return {"ok": True, "torch_id": result}
        except Exception as e:
            return {"error": str(e)[:300]}

    @app.get("/events/recent")
    async def recent(limit: int = 100, tier: Optional[str] = None):
        # tier="live" serves only what a person needs at that moment
        # (work_206b9187b0); default serves the full torrent.
        return {"events": [e.to_json() for e in bus.recent(limit, tier=tier)]}

    @app.get("/events")
    async def stream(tier: Optional[str] = None):
        q = bus.subscribe(tier=tier)

        async def gen():
            try:
                yield "retry: 3000\n\n"
                for ev in bus.recent(50, tier=tier):
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


def run_events_server(bus: EventBus, host: str = "0.0.0.0", port: int = 8020, send_torch=None) -> None:
    """Blocking: serve the event stream (call from a thread or a process)."""
    import uvicorn

    uvicorn.run(build_events_app(bus, send_torch=send_torch), host=host, port=port, log_level="warning")
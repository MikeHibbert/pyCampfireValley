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

Topics (work_8648d80e16): subscribers declare their topics — "valley",
"campfire", "torch" — and the bus routes by the topic derived from each
event's own keys (topic_of), instead of broadcasting everything to
everyone. Ledger sinks subscribe to everything; live subscribers receive
only their own topics.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, Iterable, List, Optional

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


def topic_of(ev: "ValleyEvent") -> str:
    """Routing topic for an event, derived from the routing keys the event
    already carries (work_8648d80e16): torch_id set → "torch", else campfire
    set → "campfire", else "valley". Most specific key wins."""
    if getattr(ev, "torch_id", ""):
        return "torch"
    if getattr(ev, "campfire", ""):
        return "campfire"
    return "valley"


class EventBus:
    """In-memory pub/sub with a bounded replay ring. Never raises."""

    def __init__(self, ring_size: int = _RING_DEFAULT, leader: str = ""):
        self._ring: List[ValleyEvent] = []
        self._ring_size = max(10, int(ring_size))
        # Topic-keyed subscriptions (work_8648d80e16): buckets keyed by the
        # routing topic ("valley"/"campfire"/"torch") plus "*" for
        # everything-subscribers (ledger sinks subscribe to everything).
        # Each bucket keeps the work_206b9187b0 representation: tiered
        # subscriptions as (queue, tier) tuples, plain ones as the bare
        # queue.
        self._subs: Dict[str, List[Any]] = {}
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
        # Topic-keyed routing (work_8648d80e16): the event's own keys decide
        # its topic (topic_of) and it is delivered to that topic's bucket
        # plus the "*" bucket — subscribers that declared no topics (ledger
        # sinks) get everything; a live subscriber that declared topics gets
        # only its own. Tier filtering (work_206b9187b0) still applies on
        # top: tiered subscriptions are stored as (queue, tier) tuples and
        # plain subscriptions as the bare queue; a tiered subscriber gets
        # only its tier, an untiered one the full torrent, unchanged.
        topic = topic_of(ev)
        for bucket in (topic, "*"):
            for sub in list(self._subs.get(bucket, ())):
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

    def subscribe(
        self,
        tier: Optional[str] = None,
        topics: Optional[Iterable[str]] = None,
    ) -> asyncio.Queue:
        """Subscribe to the bus.

        Tier (work_206b9187b0): with tier="live" the queue receives only
        live-tier events (what a person needs at that moment); with no tier
        it receives the full torrent (ledger + live), unchanged behavior.

        Topics (work_8648d80e16): subscribers declare their topics —
        "valley", "campfire" or "torch" — and the bus routes by the topic
        derived from each event's own keys, so a live subscriber receives
        only its own topics. topics=None (or containing "*") subscribes to
        everything: ledger sinks subscribe to everything, and legacy
        callers that declare no topics keep the full torrent.
        """
        q: asyncio.Queue = asyncio.Queue(maxsize=1000)
        if isinstance(topics, str):
            # Tolerate a comma-separated string declaration ("torch,valley").
            topics = [t.strip() for t in topics.split(",") if t.strip()]
        entry = (q, tier) if tier in TIERS else q
        if not topics or "*" in topics:
            self._subs.setdefault("*", []).append(entry)
        else:
            for topic in topics:
                self._subs.setdefault(str(topic), []).append(entry)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        # WHY (work_8648d80e16, declared-work discipline work_fb464e49b9):
        # a multi-topic subscriber is registered once per topic bucket, so
        # unsubscribe must strip the queue from EVERY bucket — the old
        # first-match-and-return left a ghost in the remaining buckets and
        # the queue kept receiving its remaining topics.
        try:
            for subs in list(self._subs.values()):
                kept = [
                    sub for sub in subs
                    if (sub[0] if isinstance(sub, tuple) else sub) is not q
                ]
                if len(kept) != len(subs):
                    subs[:] = kept
        except Exception:
            pass

    @property
    def subscriber_count(self) -> int:
        # WHY (work_8648d80e16, declared-work discipline work_fb464e49b9):
        # a subscriber that declares several topics is registered once per
        # topic bucket, so summing bucket lengths double-counted it (a
        # {"valley","campfire"} subscriber counted as 2). One subscriber is
        # one queue: count unique queues across all buckets instead.
        seen = set()
        for subs in self._subs.values():
            for sub in subs:
                q = sub[0] if isinstance(sub, tuple) else sub
                seen.add(id(q))
        return len(seen)


def value_filter(campfire: Optional[str] = None, torch: Optional[str] = None):
    """work_c067bee3d2: campfire/torch query params narrow a stream to one
    campfire or one torch's events; blank/absent = no filter. Campfire
    matching is case-insensitive; torch_id matching is exact. Module-level
    so tests exercise it without opening an SSE socket (the TestClient
    hang lesson recorded in test_events_smoke.py)."""
    campfire_f = (campfire or "").strip().lower()
    torch_f = (torch or "").strip()

    def matches(ev: "ValleyEvent") -> bool:
        if campfire_f and str(getattr(ev, "campfire", "") or "").strip().lower() != campfire_f:
            return False
        if torch_f and str(getattr(ev, "torch_id", "") or "") != torch_f:
            return False
        return True

    return matches


def build_events_app(bus: EventBus, send_torch=None) -> FastAPI:
    """Tiny FastAPI app: GET /events (SSE live-tier stream), GET /events/recent (live replay)."""
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
    async def recent(limit: int = 100, tier: Optional[str] = None,
                     campfire: Optional[str] = None, torch: Optional[str] = None):
        # Live replay is the person-facing default (work_c067bee3d2):
        # /events/recent serves the live tier's replay unless a caller
        # explicitly asks for another tier; campfire/torch narrow it
        # (value_filter). Previously the default was the full torrent
        # (work_206b9187b0) - the rewire makes live the default.
        eff_tier = tier if tier else TIER_LIVE
        matches = value_filter(campfire, torch)
        return {"events": [e.to_json() for e in bus.recent(limit, tier=eff_tier) if matches(e)]}

    @app.get("/events")
    async def stream(tier: Optional[str] = None, topics: Optional[str] = None,
                     campfire: Optional[str] = None, torch: Optional[str] = None):
        # Live tier is the person-facing default (work_c067bee3d2): /events
        # streams only the live tier unless a caller explicitly asks for
        # another tier. campfire/torch narrow the stream to one campfire or
        # one torch's events (value_filter).
        # Topic declaration (work_8648d80e16): a live subscriber declares its
        # topics as a comma-separated list (valley/campfire/torch) and the
        # bus routes by key, so it receives only its own topics; omitted =
        # everything (ledger sinks subscribe to everything).
        eff_tier = tier if tier else TIER_LIVE
        topic_set = (
            [t.strip() for t in topics.split(",") if t.strip()] if topics else None
        )
        matches = value_filter(campfire, torch)
        q = bus.subscribe(tier=eff_tier, topics=topic_set)

        async def gen():
            try:
                yield "retry: 3000\n\n"
                for ev in bus.recent(50, tier=eff_tier):
                    # The replay honors the topic declaration too
                    # (work_8648d80e16) — no valley history into a torch queue.
                    if topic_set and topic_of(ev) not in topic_set:
                        continue
                    if not matches(ev):
                        continue
                    yield f"data: {ev.to_json()}\n\n"
                while True:
                    try:
                        ev = await asyncio.wait_for(q.get(), timeout=15)
                        if not matches(ev):
                            continue
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
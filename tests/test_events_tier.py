"""Tier tests for the event bus — work_206b9187b0-s1 (slice 1/2 of work_206b9187b0).

WHY (declared-work discipline, work_fb464e49b9, docs/declared-work-discipline.md):
the ledger/live tier split lives in campfirevalley/events.py with comments
citing work_206b9187b0, but no test pinned the contract. This file pins it so
the tier behavior cannot drift silently:

  'ledger' (default) — the full torrent, the durable record;
  'live'             — only what a person needs at that moment: state
                       transitions, errors and escalations, final verses (not
                       token deltas), aggregated heartbeats, leader changes,
                       torch receipts.
"""

import json

from campfirevalley.events import (
    TIER_LEDGER,
    TIER_LIVE,
    TIERS,
    EventBus,
    ValleyEvent,
    live_worthy,
)


def _ev(type, detail=None, text="", tier=None):
    """Build a ValleyEvent directly; tier=None lets the dataclass default apply."""
    kwargs = {"type": type, "text": text, "detail": {} if detail is None else detail}
    if tier is not None:
        kwargs["tier"] = tier
    return ValleyEvent(**kwargs)


# --- constants and defaults -------------------------------------------------


def test_tier_constants():
    assert TIER_LEDGER == "ledger"
    assert TIER_LIVE == "live"
    assert TIERS == (TIER_LEDGER, TIER_LIVE)


def test_default_tier_is_ledger():
    assert _ev("agent_say").tier == TIER_LEDGER


def test_explicit_tier_honored_on_event():
    assert _ev("agent_say", tier=TIER_LIVE).tier == TIER_LIVE
    assert _ev("agent_say", tier=TIER_LEDGER).tier == TIER_LEDGER


def test_to_json_carries_tier():
    payload = json.loads(_ev("agent_say", tier=TIER_LIVE).to_json())
    assert payload["tier"] == TIER_LIVE


# --- live_worthy policy (unit: direct ValleyEvent construction) --------------


def test_live_worthy_state_transitions():
    assert live_worthy(_ev("valley_started"))
    assert live_worthy(_ev("valley_stopped"))
    assert live_worthy(_ev("campfire_assigned"))


def test_live_worthy_torch_receipts():
    assert live_worthy(_ev("torch_received"))
    assert live_worthy(_ev("torch_completed"))


def test_live_worthy_leader_changes():
    assert live_worthy(_ev("leader_say", text="new leader elected"))


def test_live_worthy_errors_and_escalations():
    assert live_worthy(_ev("tool_finished", detail={"error": "boom"}))
    assert live_worthy(_ev("command_output", detail={"level": "critical"}))
    assert live_worthy(_ev("agent_say", detail={"escalate": True}))


def test_live_worthy_final_verse_but_not_token_delta():
    assert live_worthy(_ev("agent_say", detail={"final": True}))
    assert live_worthy(_ev("agent_say", text="Final answer: 42"))
    # Token deltas are ledger-only, even on agent_say.
    assert not live_worthy(_ev("agent_say", detail={"delta": "to"}))
    assert not live_worthy(_ev("agent_say", detail={"token_delta": True}))


def test_live_worthy_heartbeat_only_when_aggregated():
    assert not live_worthy(_ev("heartbeat", detail={"count": 1}))
    assert live_worthy(_ev("heartbeat", detail={"aggregate": {"n": 30}}))
    assert live_worthy(_ev("agent_say", text="heartbeat", detail={"summary": "30 ticks"}))


def test_live_worthy_ordinary_chatter_stays_ledger():
    assert not live_worthy(_ev("agent_say", text="hello"))
    assert not live_worthy(_ev("steward_patrol", text="patrol ok"))


# --- emit: policy default, explicit win --------------------------------------


def test_emit_tier_defaults_through_live_worthy():
    bus = EventBus()
    assert bus.emit("valley_started").tier == TIER_LIVE
    assert bus.emit("agent_say", text="hello").tier == TIER_LEDGER
    assert bus.emit("agent_say", detail={"delta": "to"}).tier == TIER_LEDGER
    assert bus.emit("tool_finished", detail={"error": "boom"}).tier == TIER_LIVE


def test_emit_explicit_tier_wins():
    bus = EventBus()
    assert bus.emit("agent_say", text="hello", tier=TIER_LIVE).tier == TIER_LIVE
    assert bus.emit("valley_started", tier=TIER_LEDGER).tier == TIER_LEDGER


# --- recent: tier filter, ring keeps everything ------------------------------


def test_recent_filters_by_tier_and_ring_keeps_all():
    bus = EventBus()
    bus.emit("agent_say", text="hello")             # ledger
    bus.emit("valley_started")                      # live via policy
    bus.emit("agent_say", detail={"delta": "to"})   # ledger (token delta)
    bus.emit("agent_say", detail={"final": True})   # live via policy

    everything = bus.recent(limit=50)
    assert len(everything) == 4  # ledger is the full record — nothing dropped

    live = {e.type for e in bus.recent(limit=50, tier=TIER_LIVE)}
    assert live == {"valley_started", "agent_say"}

    ledger = {e.type for e in bus.recent(limit=50, tier=TIER_LEDGER)}
    assert ledger == {"agent_say"}

    # An unknown tier filters nothing (durable default, never raises).
    assert len(bus.recent(limit=50, tier="bogus")) == 4


# --- subscribe: tiered queues get only their tier ----------------------------


def test_subscribe_tier_gets_only_that_tier():
    bus = EventBus()
    q = bus.subscribe(tier=TIER_LIVE)
    bus.emit("agent_say", text="hello")   # ledger — must NOT reach a live queue
    bus.emit("valley_started")            # live — must reach it
    assert q.qsize() == 1
    assert q.get_nowait().type == "valley_started"


def test_subscribe_without_tier_gets_full_torrent():
    bus = EventBus()
    q = bus.subscribe()
    bus.emit("agent_say", text="hello")
    bus.emit("valley_started")
    assert q.qsize() == 2
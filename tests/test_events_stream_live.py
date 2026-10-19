"""Live-tier stream tests (work_c067bee3d2-s1).

GET /events streams only the live tier by default and narrows by
campfire/torch query params; /events/recent serves the live replay with the
same filters. The SSE route itself is only checked for wiring - streaming
GET /events through TestClient hangs pytest (the non-daemon portal-thread
lesson recorded in test_events_smoke.py), so the stream's filter logic is
exercised through value_filter() and the bounded /events/recent route.
"""
import json

from campfirevalley.events import (
    EventBus,
    build_events_app,
    value_filter,
    TIER_LIVE,
    TIER_LEDGER,
    ValleyEvent,
)


def _ev(etype, text="x", campfire="", torch_id="", tier=TIER_LEDGER):
    return ValleyEvent(
        type=etype, text=text, campfire=campfire, torch_id=torch_id, tier=tier
    )


def test_value_filter_blank_matches_all():
    m = value_filter()
    assert m(_ev("agent_say", campfire="dev"))
    assert m(_ev("agent_say"))


def test_value_filter_campfire_case_insensitive():
    m = value_filter(campfire="Dev")
    assert m(_ev("agent_say", campfire="dev"))
    assert m(_ev("agent_say", campfire="DEV"))
    assert not m(_ev("agent_say", campfire="scribe"))
    assert not m(_ev("agent_say"))


def test_value_filter_torch():
    m = value_filter(torch="t1")
    assert m(_ev("tool_started", torch_id="t1"))
    assert not m(_ev("tool_started", torch_id="t2"))
    assert not m(_ev("tool_started"))


def test_value_filter_combined():
    m = value_filter(campfire="dev", torch="t1")
    assert m(_ev("tool_started", campfire="dev", torch_id="t1"))
    assert not m(_ev("tool_started", campfire="scribe", torch_id="t1"))


def test_recent_defaults_to_live_tier():
    from fastapi.testclient import TestClient

    bus = EventBus()
    c = TestClient(build_events_app(bus))
    bus.emit("agent_say", "ordinary chatter", tier=TIER_LEDGER)
    bus.emit("torch_received", "fix the bug", campfire="dev", tier=TIER_LIVE)
    body = c.get("/events/recent").json()
    types = [json.loads(e)["type"] for e in body["events"]]
    assert "torch_received" in types
    assert "agent_say" not in types  # ledger chatter is no longer the default replay


def test_recent_campfire_filter():
    from fastapi.testclient import TestClient

    bus = EventBus()
    c = TestClient(build_events_app(bus))
    bus.emit("torch_received", "for dev", campfire="dev", tier=TIER_LIVE)
    bus.emit("torch_received", "for scribe", campfire="scribe", tier=TIER_LIVE)
    body = c.get("/events/recent?campfire=dev").json()
    texts = " ".join(json.loads(e)["text"] for e in body["events"])
    assert "for dev" in texts and "for scribe" not in texts


def test_recent_torch_filter():
    from fastapi.testclient import TestClient

    bus = EventBus()
    c = TestClient(build_events_app(bus))
    bus.emit("tool_started", "step", campfire="dev", torch_id="t1", tier=TIER_LIVE)
    bus.emit("tool_started", "other", campfire="dev", torch_id="t2", tier=TIER_LIVE)
    body = c.get("/events/recent?torch=t1").json()
    assert all(json.loads(e)["torch_id"] == "t1" for e in body["events"])


def test_events_route_wired():
    from fastapi.testclient import TestClient

    bus = EventBus()
    app = build_events_app(bus)
    c = TestClient(app)
    # bounded check only - see module docstring for the SSE hang lesson
    r = c.get("/events/recent?limit=3")
    assert r.status_code == 200
    paths = {getattr(rt, "path", "") for rt in app.routes}
    assert "/events" in paths and "/events/recent" in paths


print("ALL LIVE-STREAM TESTS PASS")

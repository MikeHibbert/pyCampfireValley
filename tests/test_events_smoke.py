
import asyncio, sys
sys.path.insert(0, r"C:\Users\Mike\Documents\Python\CampfireValley")
from campfirevalley.events import EventBus, build_events_app, EVENT_TYPES

def test_emit_ring_recent():
    bus = EventBus(ring_size=10)
    for i in range(15):
        bus.emit("tool_started", f"tool {i}")
    rec = bus.recent(100)
    assert len(rec) == 10, len(rec)
    assert rec[-1].text == "tool 14"
    assert rec[0].text == "tool 5"

def test_unknown_type_falls_back():
    bus = EventBus()
    ev = bus.emit("weird_type", "x")
    assert ev.type == "agent_say"

def test_subscribe_receives():
    bus = EventBus()
    q = bus.subscribe()
    bus.emit("agent_say", "hello")
    ev = q.get_nowait()
    assert ev.text == "hello"
    bus.unsubscribe(q)
    assert bus.subscriber_count == 0

def test_json_roundtrip():
    import json
    bus = EventBus()
    ev = bus.emit("tool_finished", "done", detail={"rc": 0})
    data = json.loads(ev.to_json())
    assert data["type"] == "tool_finished" and data["detail"]["rc"] == 0

def test_sse_app():
    from fastapi.testclient import TestClient
    bus = EventBus()
    app = build_events_app(bus)
    c = TestClient(app)
    bus.emit("agent_say", "hi there")
    r = c.get("/events/recent?limit=5")
    assert r.status_code == 200
    body = r.json()
    assert body["events"] and "hi there" in body["events"][-1]
    # SSE stream smoke: open and read first chunk
    with c.stream("GET", "/events") as resp:
        assert resp.status_code == 200
        it = resp.iter_text()
        first = next(it)
        assert first.startswith("retry:")
        chunk = next(it)
        assert "hi there" in chunk

print("ALL EVENT TESTS PASS")

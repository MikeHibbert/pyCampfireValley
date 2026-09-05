"""Sable oversight smoke tests (offline, no valley start needed)."""
import asyncio
import sys

sys.path.insert(0, ".")

from campfirevalley.sable import Sable  # noqa: E402
from campfirevalley.events import EventBus  # noqa: E402


class FakeStewardMonitor:
    def __init__(self):
        self._checks = {"mcp": lambda: (True, "connected")}
        self.last_sweep = {
            "swept_at": "2026-09-05T00:00:00Z",
            "checks": {"mcp": {"healthy": True, "detail": "connected"}},
        }


class FakeSteward:
    def __init__(self):
        self.monitor = FakeStewardMonitor()


class FakeValley:
    name = "test_valley"
    campfires = {"timberwolf-steward": FakeSteward(), "dev": type("C", (), {"_running": True})()}
    events = EventBus()


def test_sable_reports_facts_to_leader():
    bus = EventBus()
    v = FakeValley()
    v.events = bus
    s = Sable(v, bus=bus)
    s.record_failure("t1", "dev", "boom")
    facts = asyncio.run(s.sweep())
    # leader_say lands on the replay ring (subscribers are async queues)
    recent = [ev.as_dict() for ev in bus.recent(20)] if hasattr(bus.recent(1)[0] if bus.recent(1) else None, "as_dict") else [
        {"type": getattr(ev, "type", ""), "text": getattr(ev, "text", "")} for ev in bus.recent(20)
    ]
    leader_says = [ev for ev in recent if ev.get("type") == "leader_say"]
    assert facts["failure_count_window"] == 1
    assert leader_says, "sable should report facts via leader_say"
    text = leader_says[-1].get("text", "")
    assert "failure" in text.lower()
    print("ok: failure reported to leader")


def test_sable_stall_detection():
    bus = EventBus()
    v = FakeValley()
    v.events = bus
    s = Sable(v, bus=bus)
    s._in_flight["t-stall"] = 0.0  # seen at epoch -> older than threshold
    facts = asyncio.run(s.sweep())
    assert facts["stalled_torches"], "long-in-flight torch should be reported as stalled"
    assert facts["stalled_torches"][0]["torch_id"] == "t-stall"
    print("ok: stall detected")


def test_sable_health_facts():
    v = FakeValley()
    s = Sable(v)
    facts = asyncio.run(s.sweep())
    h = facts["campfire_health"]
    assert h["campfires_running"] == 1
    assert h.get("mcp") == "connected"  # steward's last sweep surfaced
    print("ok: health facts gathered")


def test_sable_never_raises_in_sweep_loop():
    v = FakeValley()
    s = Sable(v)
    # a sweep loop tick with a broken bus must not raise
    s.bus = None

    async def run():
        await s._sweep_loop_once() if hasattr(s, "_sweep_loop_once") else None
        s._running = True
        task = asyncio.create_task(s._sweep_loop())
        await asyncio.sleep(0.05)
        s._running = False
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    asyncio.run(run())
    print("ok: sweep loop survives errors")


def run():
    pass


if __name__ == "__main__":
    test_sable_reports_facts_to_leader()
    test_sable_stall_detection()
    test_sable_health_facts()
    test_sable_never_raises_in_sweep_loop()
    print("ALL SABLE TESTS PASS (4/4)")
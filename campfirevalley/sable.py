"""Sable, a wise and far sighted eagle.

Sable is the chopped-down Golden Eagle for product valleys: a lean oversight
layer that watches a running valley and reports FACTS to the valley leader
(the Timberwolf, or whoever holds the leader role). The same record-not-judge
discipline as the queen-bee eagle - Sable observes and records, it does not
interpret, and it gets none of the Andrew-side machinery (no work-board
introspection, no lesson stores, no model profiles). Eagle on Andrew's
mountain; Sable over the product valley.

What Sable watches:
- campfire health facts (from the steward's monitor round, when present),
- torch failures (a torch that raised, or repeated failures from one campfire),
- event-stream stalls (long gaps between torch_received and torch_completed).

How it reports: a single `leader_say` event per sweep that summarises the
facts it saw, so the leader's voice in the TUI carries the valley's condition.
"""
from __future__ import annotations

import asyncio
import time
from collections import deque
from datetime import datetime, timezone
from typing import Any, Deque, Dict, List, Optional

from .events import EventBus

STALL_THRESHOLD_SECONDS = 300.0
FAILURE_WINDOW = 20
FAILURE_ALERT_THRESHOLD = 3


class Sable:
    """Sable, a wise and far sighted eagle.

    Watches the valley's event stream and campfire health, records facts,
    and reports them to the leader. Never interprets, never intervenes.
    """

    def __init__(self, valley, bus=None, interval_seconds: float = 60.0):
        self.valley = valley
        self.bus = bus or getattr(valley, "events", None)
        self.interval_seconds = interval_seconds
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._in_flight: Dict[str, float] = {}  # torch_id -> first-seen ts
        self._failures: Deque[Dict[str, Any]] = deque(maxlen=FAILURE_WINDOW)
        self._last_sweep_ts = 0.0

    # -- lifecycle -----------------------------------------------------------

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._sweep_loop())

    async def stop(self) -> None:
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None

    # -- observation ---------------------------------------------------------

    def observe_event(self, ev: Any) -> None:
        """Feed one event into Sable's watch (called from the bus fan-out)."""
        etype = getattr(ev, "type", ev.get("type", "") if isinstance(ev, dict) else "")
        torch_id = getattr(ev, "torch_id", None)
        if torch_id is None and isinstance(ev, dict):
            torch_id = ev.get("torch_id")
        ts = time_now()
        if etype == "torch_received" and torch_id:
            self._in_flight.setdefault(str(torch_id), ts)
        elif etype == "torch_completed" and torch_id:
            self._in_flight.pop(str(torch_id), None)
        elif etype == "torch_failed" and torch_id:
            self._failures.append({
                "torch_id": str(torch_id),
                "campfire": getattr(ev, "campfire", None) if not isinstance(ev, dict) else ev.get("campfire"),
                "ts": ts,
            })
            self._in_flight.pop(str(torch_id), None)

    def record_failure(self, torch_id: str, campfire: str, error: str = "") -> None:
        """Direct failure report (for paths that do not emit torch_failed)."""
        self._failures.append({"torch_id": str(torch_id), "campfire": campfire, "error": str(error)[:120], "ts": time_now()})

    # -- sweeps --------------------------------------------------------------

    async def _sweep_loop(self) -> None:
        while self._running:
            try:
                await self.sweep()
            except Exception:
                pass  # Sable never takes the valley down with it
            await asyncio.sleep(self.interval_seconds)

    async def sweep(self) -> Dict[str, Any]:
        """One oversight sweep: gather facts, report to the leader as facts."""
        now = time_now()
        facts: Dict[str, Any] = {"swept_at": datetime.now(timezone.utc).isoformat(), "valley": getattr(self.valley, "name", "")}

        # stalls: torches in flight longer than the threshold
        stalls = []
        for torch_id, first_seen in list(self._in_flight.items()):
            if now - first_seen >= STALL_THRESHOLD_SECONDS:
                stalls.append({"torch_id": torch_id, "age_s": round(now - first_seen, 1)})
        if not stalls:
            self._in_flight.clear()
        facts["stalled_torches"] = stalls

        # failures: recent failure facts
        recent_failures = list(self._failures)
        facts["recent_failures"] = recent_failures[-5:]
        facts["failure_count_window"] = len(recent_failures)

        # campfire health via the steward monitor camper, when present
        health = self._health_facts()
        facts["campfire_health"] = health

        # report to the leader (leader_say event) when there is something to say
        lines = self._compose_report(facts)
        if lines and self.bus is not None:
            try:
                self.bus.emit("leader_say", text=lines, valley=facts["valley"], detail={"source": "sable"})
            except Exception:
                pass
        self._last_sweep_ts = now
        return facts

    def _health_facts(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        steward = getattr(self.valley, "campfires", {}).get("timberwolf-steward")
        if steward is not None and hasattr(steward, "monitor"):
            try:
                monitor = steward.monitor
                # Prefer the steward's own recorded sweep (facts already gathered)
                last = getattr(monitor, "last_sweep", None)
                if isinstance(last, dict) and last.get("checks"):
                    for name, res in last["checks"].items():
                        out[str(name)[:40]] = str(res.get("detail", ""))[:80]
                        out.setdefault("steward_last_sweep", str(last.get("swept_at", ""))[:40])
                else:
                    # Fall back to registered check names (not yet swept)
                    checks = getattr(monitor, "_checks", None) or {}
                    for name in checks:
                        out[str(name)[:40]] = "registered"
                    out["steward"] = "checks registered; no sweep yet"
            except Exception:
                out["steward"] = "monitor facts unavailable"
        else:
            out["steward"] = "no steward campfire provisioned"
        out["campfires_running"] = sum(
            1 for c in getattr(self.valley, "campfires", {}).values() if getattr(c, "_running", False)
        )
        return out

    def _compose_report(self, facts: Dict[str, Any]) -> str:
        lines: List[str] = []
        stalls = facts.get("stalled_torches") or []
        if stalls:
            ids = ", ".join(s["torch_id"][:12] for s in stalls[:3])
            lines.append(f"{len(stalls)} torch(es) in flight over {int(STALL_THRESHOLD_SECONDS)}s: {ids}")
        fails = facts.get("recent_failures") or []
        if fails:
            last = fails[-1]
            who = last.get("campfire") or "unknown campfire"
            lines.append(f"{len(fails)} recent torch failure(s), latest from {who}")
        health = facts.get("campfire_health") or {}
        running = health.get("campfires_running")
        if running is not None:
            lines.append(f"campfires running: {running}; steward: {health.get('steward', 'present')}")
        return " | ".join(lines)

    # -- last facts ----------------------------------------------------------

    def last_facts(self) -> Dict[str, Any]:
        return {
            "last_sweep_ts": self._last_sweep_ts,
            "in_flight": len(self._in_flight),
            "failures_window": len(self._failures),
        }


def time_now() -> float:
    import time
    return time.time()
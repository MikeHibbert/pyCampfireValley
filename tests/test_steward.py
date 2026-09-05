
"""Tests for the Timberwolf StewardCampfire (deterministic care, division line)."""

import asyncio

import pytest

from campfirevalley.campfires.steward import (
    StewardCampfire,
    MonitorCamper,
    HousekeeperCamper,
    ReportCamper,
    SelfHealCamper,
)


def _mk_steward(target_valley=""):
    return StewardCampfire(mcp_broker=None, config=None)


def test_default_config_carries_four_campers():
    s = _mk_steward()
    assert set(s._campers) == {"monitor", "housekeeper", "report", "self_heal"}
    uses = [st.get("uses", "") for st in s.config.steps]
    assert any("camper/monitor@" in u for u in uses)
    assert any("camper/report@" in u for u in uses)


def test_monitor_collects_health_facts():
    m = MonitorCamper({})
    m.add_health_check("mcp", lambda: (True, "3 connections"))
    m.add_health_check("jobs", lambda: (False, "job X stale"))
    asyncio.run(m.start())
    out = asyncio.run(m.process())
    assert out["total"] == 2 and out["healthy"] == 1 and out["unhealthy"] == 1
    assert out["checks"]["mcp"]["healthy"] is True
    assert "stale" in out["checks"]["jobs"]["detail"]


def test_monitor_survives_raising_check():
    m = MonitorCamper({})

    def boom():
        raise ValueError("socket died")

    m.add_health_check("boom", boom)
    asyncio.run(m.start())
    out = asyncio.run(m.process())
    assert out["unhealthy"] == 1
    assert "ValueError" in out["checks"]["boom"]["detail"]


def test_housekeeper_collects_task_facts():
    h = HousekeeperCamper({})
    h.add_task("prune_runs", lambda: {"pruned": 12})
    h.add_task("rotate_logs", lambda: {"rotated": 3})
    asyncio.run(h.start())
    out = asyncio.run(h.process())
    assert out["tasks"]["prune_runs"] == {"pruned": 12}
    assert out["tasks"]["rotate_logs"] == {"rotated": 3}


def test_report_records_locally_without_channel():
    r = ReportCamper({"valley_name": "timber-valley", "target_valley": ""})
    asyncio.run(r.start())
    out = asyncio.run(r.process({"monitor": {"unhealthy": 0}}))
    assert out["dispatched"] is False
    assert r.last_report["facts"]["monitor"]["unhealthy"] == 0
    assert r.last_report["steward"] == "timberwolf"


def test_report_dispatches_through_send_fn():
    sent = {}

    async def send(target, report):
        sent["target"] = target
        sent["report"] = report

    r = ReportCamper({"valley_name": "timber-valley", "target_valley": "andrew-core", "send_fn": send})
    asyncio.run(r.start())
    out = asyncio.run(r.process({"monitor": {"unhealthy": 1}}))
    assert out["dispatched"] is True
    assert sent["target"] == "andrew-core"
    assert sent["report"]["facts"]["monitor"]["unhealthy"] == 1


def test_self_heal_applies_registered_remedies():
    h = SelfHealCamper({})

    def retry_failed():
        return {"retried": 2, "recovered": 1}

    h.add_remedy("retry_failed_jobs", retry_failed)
    asyncio.run(h.start())
    out = asyncio.run(h.process())
    assert out["remedies"]["retry_failed_jobs"] == {"retried": 2, "recovered": 1}
    assert h.actions[0]["remedy"] == "retry_failed_jobs"


def test_self_heal_respects_remedy_filter():
    h = SelfHealCamper({})
    h.add_remedy("a", lambda: {"ok": 1})
    h.add_remedy("b", lambda: {"ok": 2})
    asyncio.run(h.start())
    out = asyncio.run(h.process({"remedies": ["b"]}))
    assert "a" not in out["remedies"] and out["remedies"]["b"] == {"ok": 2}


def test_patrol_flows_facts_to_report():
    s = _mk_steward()
    s.monitor.add_health_check("mcp", lambda: (True, "ok"))
    s.housekeeper.add_task("prune", lambda: {"pruned": 1})
    s.self_heal.add_remedy("heal", lambda: {"recovered": 1})
    out = asyncio.run(s.patrol())
    assert out["monitor"]["healthy"] == 1
    assert out["housekeeping"]["tasks"]["prune"]["pruned"] == 1
    assert out["self_heal"]["remedies"]["heal"]["recovered"] == 1
    assert out["report"]["dispatched"] is False  # no channel wired in test


def test_division_line_no_llm_surface():
    """The steward imports no LLM machinery: deterministic care only."""
    import campfirevalley.campfires.steward as st
    names = dir(st)
    for banned in ("LLMCampfire", "ollama", "openrouter"):
        assert not any(banned.lower() in n.lower() for n in names), f"steward references {banned}"

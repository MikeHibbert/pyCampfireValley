import types

import pytest

from campfirevalley.models import Torch
from campfirevalley.valley import Valley


class _DummyMonitoring:
    async def log(self, *args, **kwargs):
        return None


class _ResponderCampfire:
    def __init__(self, responses=None, config=None):
        self.responses = responses or {}
        self.config = config or {}
        self.calls = []
        self.verify_calls = 0
        self.improve_calls = 0
        self.workflow_calls = 0

    async def process_torch(self, torch):
        self.calls.append(torch)
        claim = getattr(torch, "claim", "")
        if claim == "watch_plan":
            text = self.responses.get("watch_plan", "{}")
            return types.SimpleNamespace(data={"text": text})
        if claim == "watch_verify":
            scripted = self.responses.get("watch_verify", [])
            idx = min(self.verify_calls, max(0, len(scripted) - 1))
            self.verify_calls += 1
            text = scripted[idx] if scripted else '{"pass": true, "reason": "pass", "feedback": "", "reroute_to": "execute"}'
            return types.SimpleNamespace(data={"text": text})
        if claim == "watch_improve":
            scripted = self.responses.get("watch_improve", [])
            idx = min(self.improve_calls, max(0, len(scripted) - 1))
            self.improve_calls += 1
            if isinstance(scripted, list):
                text = scripted[idx] if scripted else "{}"
            else:
                text = scripted or "{}"
            return types.SimpleNamespace(data={"text": text})
        if claim == "workflow_step":
            scripted = self.responses.get("workflow_step", [])
            idx = min(self.workflow_calls, max(0, len(scripted) - 1))
            self.workflow_calls += 1
            text = scripted[idx] if scripted else "workflow output"
            return types.SimpleNamespace(data={"text": text})
        text = self.responses.get(claim) or self.responses.get("default") or "round output"
        return types.SimpleNamespace(data={"text": text})


@pytest.mark.asyncio
async def test_process_target_campfire_uses_watch_by_default():
    valley = Valley.__new__(Valley)
    valley.name = "Local Valley"
    valley.campfires = {
        "Alpha": _ResponderCampfire(config={}),
    }

    async def fake_watch(name, torch):
        return {"watch": name, "torch": torch.torch_id}

    async def fake_service(*args, **kwargs):
        return None

    valley._run_watch_for_torch = fake_watch
    valley.process_service_call = fake_service

    torch = Torch(
        claim="voice_text",
        source_campfire="voice",
        channel="voice",
        sender_valley="Local Valley",
        target_address="Local Valley:Alpha",
        data={"text": "hello"},
        signature="voice_placeholder",
    )

    result = await Valley._process_target_campfire(valley, "Alpha", torch)

    assert result == {"watch": "Alpha", "torch": torch.torch_id}


@pytest.mark.asyncio
async def test_process_target_campfire_respects_watch_disable():
    valley = Valley.__new__(Valley)
    valley.name = "Local Valley"
    direct = {"text": "direct"}
    valley.campfires = {
        "Alpha": _ResponderCampfire(
            responses={"default": "direct"},
            config={"behavior": {"watch": {"enabled": False}}},
        ),
    }

    async def fake_watch(*args, **kwargs):
        raise AssertionError("watch should not run when disabled")

    async def fake_service(*args, **kwargs):
        return None

    async def direct_process(_torch):
        return direct

    valley._run_watch_for_torch = fake_watch
    valley.process_service_call = fake_service
    valley.campfires["Alpha"].process_torch = direct_process

    torch = Torch(
        claim="voice_text",
        source_campfire="voice",
        channel="voice",
        sender_valley="Local Valley",
        target_address="Local Valley:Alpha",
        data={"text": "hello"},
        signature="voice_placeholder",
    )

    result = await Valley._process_target_campfire(valley, "Alpha", torch)

    assert result == direct


@pytest.mark.asyncio
async def test_watch_run_reroutes_execute_round_until_verify_passes(monkeypatch, tmp_path):
    monkeypatch.setenv("REPORTS_DIR", str(tmp_path))
    valley = Valley.__new__(Valley)
    valley.name = "Local Valley"
    valley.monitoring = _DummyMonitoring()
    valley._watch_runs = {}
    valley._watch_learnings = {}
    valley._workflow_cache = {}

    plan_text = (
        '{"rounds": {'
        '"discover": {"goal": "Gather context", "campers": ["Research Camper"]}, '
        '"plan": {"goal": "Plan the work", "campers": ["Alpha Auditor"]}, '
        '"execute": {"goal": "Do the work", "campers": ["Research Camper"], '
        '"steps": [{"camper": "Research Camper", "task": "Research and answer the request."}]}, '
        '"verify": {"goal": "Verify readiness", "campers": ["Alpha Auditor"], '
        '"pass_criteria": ["Answer the request fully"]}, '
        '"improve": {"goal": "Capture learning", "campers": ["Alpha Auditor"], '
        '"focus_areas": ["camper selection", "workflow ordering"]}'
        '}, "failure_policy": {"default_reroute_to": "execute"}}'
    )
    verify_fail = '{"pass": false, "reason": "weak_result", "feedback": "Strengthen the answer.", "reroute_to": "execute"}'
    verify_pass = '{"pass": true, "reason": "pass", "feedback": "", "reroute_to": "execute"}'
    improve_json = (
        '{"outcome_summary": "The watch improved after a retry.", '
        '"effectiveness": {"task_fit": 4, "quality": 4, "efficiency": 3, "coordination": 4}, '
        '"strengths": ["Verifier feedback was incorporated successfully."], '
        '"weaknesses": ["The first execute draft was too weak."], '
        '"recommendations": ["Use the Research Camper for similar torches.", "Refine execute task wording earlier."], '
        '"camper_feedback": [{"campfire": "Research Camper", "rating": "helpful", "notes": "Recovered well on retry."}], '
        '"learned_policy": {"prefer_campers": ["Research Camper"], "workflow_suggestions": ["Keep a single research-focused execute step."]}}'
    )

    alpha = _ResponderCampfire(responses={"default": "Alpha direct"})
    auditor = _ResponderCampfire(
        responses={
            "watch_plan": plan_text,
            "watch_verify": [verify_fail, verify_pass],
            "watch_improve": [improve_json],
        }
    )
    worker = _ResponderCampfire(
        responses={
            "watch_discover": "Research context",
            "watch_plan": "Use Research Camper for execution.",
            "workflow_step": ["First draft", "Final draft"],
        }
    )

    valley.campfires = {
        "Alpha": alpha,
        "Alpha Auditor": auditor,
        "Research Camper": worker,
    }
    valley.get_workflow = lambda name: {
        "steps": [{"camper": "Research Camper", "task": "Research and answer the request."}]
    }

    torch = Torch(
        claim="voice_text",
        source_campfire="voice",
        channel="voice",
        sender_valley="Caller Valley",
        target_address="Local Valley:Alpha",
        data={"text": "Find the answer"},
        signature="voice_placeholder",
    )

    result = await Valley._run_watch_for_torch(valley, "Alpha", torch)

    assert result is not None
    assert result.data["ok"] is True
    assert result.data["text"] == "Final draft"
    assert worker.workflow_calls == 2
    assert auditor.improve_calls == 1
    rounds = [entry.get("round") for entry in result.data["watch"]["history"]]
    assert rounds[:4] == ["discover", "plan", "execute", "verify"]
    assert rounds[-3:] == ["execute", "verify", "improve"]
    assert result.data["watch"]["history"][0]["campers_used"] == ["Research Camper"]
    assert result.data["watch"]["history"][0]["summary"] == "Research Camper:\nResearch context"
    assert result.data["watch"]["history"][1]["campers_used"] == ["Alpha Auditor"]
    assert result.data["watch"]["history"][1]["planner_source"] == "auditor"
    learning = result.data["watch"]["learning"]
    assert learning["recommendations"][0] == "Use the Research Camper for similar torches."
    assert result.data["watch"]["learning_summary"]["runs"] == 1
    assert valley._watch_learnings["Alpha"]["passes"] == 1
    assert result.data["watch"]["report_url"].endswith("/api/watch/runs/" + result.data["watch"]["watch_id"] + "/report")
    assert result.data["watch"]["report_path"].endswith(".html")
    assert len([call for call in auditor.calls if getattr(call, "claim", "") == "watch_plan"]) == 3


@pytest.mark.asyncio
async def test_watch_run_records_heuristic_learning_without_improver_json(monkeypatch, tmp_path):
    monkeypatch.setenv("REPORTS_DIR", str(tmp_path))
    valley = Valley.__new__(Valley)
    valley.name = "Local Valley"
    valley.monitoring = _DummyMonitoring()
    valley._watch_runs = {}
    valley._watch_learnings = {}
    valley._workflow_cache = {}

    alpha = _ResponderCampfire(responses={"watch_discover": "Alpha context"})
    worker = _ResponderCampfire(responses={"workflow_step": ["Solid answer"]})
    valley.campfires = {
        "Alpha": alpha,
        "Research Camper": worker,
    }
    valley.get_workflow = lambda name: {
        "steps": [{"camper": "Research Camper", "task": "Answer the request clearly."}]
    }

    torch = Torch(
        claim="voice_text",
        source_campfire="voice",
        channel="voice",
        sender_valley="Caller Valley",
        target_address="Local Valley:Alpha",
        data={"text": "Find the answer"},
        signature="voice_placeholder",
    )

    result = await Valley._run_watch_for_torch(valley, "Alpha", torch)

    assert result is not None
    assert result.data["ok"] is True
    assert result.data["watch"]["history"][-1]["round"] == "improve"
    assert "recommendations" in result.data["watch"]["learning"]
    assert valley._watch_learnings["Alpha"]["runs"] == 1
    assert valley._watch_learnings["Alpha"]["average_effectiveness"]["task_fit"] >= 1


@pytest.mark.asyncio
async def test_watch_plan_falls_back_when_auditor_plan_is_invalid(monkeypatch, tmp_path):
    monkeypatch.setenv("REPORTS_DIR", str(tmp_path))
    valley = Valley.__new__(Valley)
    valley.name = "Local Valley"
    valley.monitoring = _DummyMonitoring()
    valley._watch_runs = {}
    valley._watch_learnings = {}
    valley._workflow_cache = {}

    alpha = _ResponderCampfire(responses={"watch_discover": "Alpha context"})
    auditor = _ResponderCampfire(
        responses={
            "watch_plan": '{"rounds": {"discover": {"goal": "Broken", "campers": []}}}',
            "watch_verify": ['{"pass": true, "reason": "pass", "feedback": "", "reroute_to": "execute"}'],
        }
    )
    worker = _ResponderCampfire(responses={"workflow_step": ["Solid answer"]})
    valley.campfires = {
        "Alpha": alpha,
        "Alpha Auditor": auditor,
        "Research Camper": worker,
    }
    valley.get_workflow = lambda name: {
        "steps": [{"camper": "Research Camper", "task": "Answer the request clearly."}]
    }

    torch = Torch(
        claim="voice_text",
        source_campfire="voice",
        channel="voice",
        sender_valley="Caller Valley",
        target_address="Local Valley:Alpha",
        data={"text": "Find the answer"},
        signature="voice_placeholder",
    )

    result = await Valley._run_watch_for_torch(valley, "Alpha", torch)

    assert result is not None
    assert result.data["ok"] is True
    assert result.data["watch"]["history"][0]["campers_used"] == ["Research Camper"]
    assert result.data["watch"]["history"][1]["planner_source"] == "fallback"
    assert result.data["watch"]["history"][1]["planner_fallback_reason"].startswith("planner_missing_")
    assert result.data["watch"]["history"][2]["campers_used"] == ["Research Camper"]


@pytest.mark.asyncio
async def test_watch_plan_prompt_prefers_non_auditor_specialists(monkeypatch, tmp_path):
    monkeypatch.setenv("REPORTS_DIR", str(tmp_path))
    valley = Valley.__new__(Valley)
    valley.name = "Local Valley"
    valley.monitoring = _DummyMonitoring()
    valley._watch_runs = {}
    valley._watch_learnings = {}
    valley._workflow_cache = {}

    alpha = _ResponderCampfire(responses={"watch_discover": "Alpha context"})
    auditor = _ResponderCampfire(
        responses={
            "watch_plan": '{"rounds": {"discover": {"goal": "Broken", "campers": []}}}',
        }
    )
    worker = _ResponderCampfire(responses={"workflow_step": ["Solid answer"]})
    valley.campfires = {
        "Alpha": alpha,
        "Alpha Auditor": auditor,
        "Research Camper": worker,
    }
    valley.get_workflow = lambda name: {
        "steps": [{"camper": "Research Camper", "task": "Answer the request clearly."}]
    }

    torch = Torch(
        claim="voice_text",
        source_campfire="voice",
        channel="voice",
        sender_valley="Caller Valley",
        target_address="Local Valley:Alpha",
        data={"text": "Find the answer"},
        signature="voice_placeholder",
    )

    plan = await Valley._request_watch_plan(valley, "Alpha", torch, "corr_1")

    assert plan["rounds"]["discover"]["campers"] == ["Research Camper"]
    assert plan["rounds"]["execute"]["campers"][0] == "Research Camper"
    prompt = auditor.calls[0].data["text"]
    assert "Preferred non-auditor campers for discover/execute" in prompt
    assert "- Research Camper" in prompt
    assert "Keep the auditor out of discover and execute" in prompt


def test_render_watch_report_html_contains_rounds_and_learning(monkeypatch, tmp_path):
    monkeypatch.setenv("REPORTS_DIR", str(tmp_path))
    valley = Valley.__new__(Valley)
    valley._watch_runs = {
        "watch_demo": {
            "ok": True,
            "text": "Final answer",
            "campfire": "Alpha",
            "correlation_id": "voice_demo",
            "watch": {
                "watch_id": "watch_demo",
                "campfire": "Alpha",
                "torch_id": "voice_torch",
                "retry_count": 1,
                "report_url": "/api/watch/runs/watch_demo/report",
                "history": [
                    {
                        "round": "discover",
                        "status": "completed",
                        "campers_used": ["Alpha", "Research Camper"],
                        "summary": "Collected source material.",
                        "details": [{"camper": "Research Camper", "ok": True, "text": "Found the relevant source."}],
                    },
                    {
                        "round": "verify",
                        "status": "completed",
                        "campers_used": ["Alpha Auditor"],
                        "summary": "Verifier approved the result.",
                        "decision": {"pass": True, "reason": "pass", "feedback": "", "reroute_to": "execute"},
                    },
                ],
                "learning": {
                    "outcome_summary": "Passed after one retry.",
                    "effectiveness": {"task_fit": 4, "quality": 4, "efficiency": 3, "coordination": 4},
                    "strengths": ["Good camper selection."],
                    "weaknesses": ["The first draft was weak."],
                    "recommendations": ["Use the Research Camper earlier."],
                    "camper_feedback": [{"campfire": "Research Camper", "rating": "helpful", "notes": "Found the key source."}],
                    "learned_policy": {"prefer_campers": ["Research Camper"]},
                },
                "learning_summary": {"runs": 1, "passes": 1},
            },
        }
    }

    html_doc = Valley.render_watch_report_html(valley, "watch_demo")
    saved_path = Valley.save_watch_report(valley, "watch_demo")

    assert html_doc is not None
    assert "Watch Report" in html_doc
    assert "Alpha" in html_doc
    assert "Research Camper" in html_doc
    assert "Verifier approved the result." in html_doc
    assert "Use the Research Camper earlier." in html_doc
    assert saved_path is not None
    assert tmp_path.joinpath("watch_demo.html").exists()

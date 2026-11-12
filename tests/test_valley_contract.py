"""Conformance tests for the Valley Contract bare tier (docs/valley-contract.md).

Contract v1 (PR #25): a bare valley exposes the agent-executor surface —
/ready, POST /agent/handoff, GET /kumbayas/runs [+ /{id}],
POST /kumbayas/runs/{id}/cancel, POST /chat — and must NOT expose the /work
surface (that is Andrew-tier only). These tests drive the route handlers
directly with a stub valley: no HTTP layer, no LLM, fully deterministic.
Single-loop scenarios: every background task is created and awaited on the
same asyncio run that observes it (a task created on a closing loop would
orphan silently — lesson from the mDNS loop test).
"""

import asyncio

import pytest
from fastapi import HTTPException

import campfirevalley.web.api as api


class _StubTorch:
    def __init__(self, data=None):
        self.data = data if data is not None else {}


class _Config:
    """Valley-shaped config (env + campfires dict incl. the visible list)."""

    def __init__(self):
        from types import SimpleNamespace

        self.campfires = {"visible": ["Main Campfire"]}
        self.env = {}


class _StubValley:
    """Enough of Valley for the contract handlers: a campfire that answers."""

    name = "Test Valley"
    _running = True

    def __init__(self):
        self.config = _Config()
        self.campfires = {"Main Campfire": object()}
        self.torches = []

    async def process_torch(self, torch):
        self.torches.append(torch)
        return _StubTorch(data={"llm_response": f"echo: {torch.data.get('text', '')}"})


@pytest.fixture()
def stub_valley():
    valley = _StubValley()
    api.set_valley(valley)
    api._contract_runs.clear()
    api._contract_tasks.clear()
    yield valley
    for task in list(api._contract_tasks.values()):
        task.cancel()
    api.set_valley(None)


def test_ready_carries_the_contract_fields(stub_valley):
    ready = asyncio.run(api.contract_ready())
    assert ready == {
        "service": "Test Valley",
        "status": "ready",
        "draining": False,
        "contract": 1,
        "capabilities": ["agent"],
    }


def test_handoff_refuses_a_valley_with_no_campers():
    valley = _StubValley()
    valley.campfires.clear()
    api.set_valley(valley)
    with pytest.raises(HTTPException) as err:
        asyncio.run(api.agent_handoff({"prompt": "do the thing"}))
    assert err.value.status_code == 409


def test_handoff_rejects_a_missing_prompt():
    with pytest.raises(HTTPException) as err:
        asyncio.run(api.agent_handoff({}))
    assert err.value.status_code == 400


def test_handoff_runs_and_lands_in_the_runs_list(stub_valley):
    async def _scenario():
        reply = await api.agent_handoff({
            "title": "Ship the widget",
            "prompt": "build the widget",
            "session_id": "ide:andruide",
        })
        assert set(reply.keys()) == {"id"}
        run_id = reply["id"]
        await asyncio.sleep(0.05)  # the stub answers instantly
        runs = await api.contract_runs_list()
        assert len(runs) == 1
        run = runs[0]
        assert run["id"] == run_id
        assert run["kumbaya"] == "Ship the widget"
        assert run["session_id"] == "ide:andruide"
        assert run["status"] == "completed"
        assert run["result"] == "echo: build the widget"
        verses = run["verses"]
        assert verses and verses[0]["status"] == "completed"
        detail = await api.contract_run_detail(run_id)
        assert detail["id"] == run_id
        with pytest.raises(HTTPException) as err:
            await api.contract_run_detail("no-such-run")
        assert err.value.status_code == 404

    asyncio.run(_scenario())


def test_cancel_stops_a_running_run():
    class SlowValley(_StubValley):
        async def process_torch(self, torch):
            await asyncio.sleep(30)  # long enough to cancel deterministically
            return _StubTorch(data={})

    valley = SlowValley()
    api.set_valley(valley)

    async def _scenario():
        reply = await api.agent_handoff({"prompt": "long job"})
        run_id = reply["id"]
        result = await api.contract_cancel_run(run_id)
        assert result == {"status": "cancelled", "id": run_id}
        run = await api.contract_run_detail(run_id)
        assert run["status"] == "cancelled"
        assert run["verses"][0]["error"] == "cancelled by request"

    asyncio.run(_scenario())


def test_chat_with_interrupt_stops_the_session_run():
    class SlowValley(_StubValley):
        async def process_torch(self, torch):
            if torch.claim == "agent_handoff":
                await asyncio.sleep(30)
            return _StubTorch(data={"llm_response": "yes dad"})

    valley = SlowValley()
    api.set_valley(valley)

    async def _scenario():
        reply = await api.agent_handoff({"prompt": "long job", "session_id": "ide:andruide"})
        run_id = reply["id"]
        out = await api.contract_chat({
            "session_id": "ide:andruide",
            "message": "stop, do it differently",
            "interrupt": True,
        })
        assert out == {"reply": "yes dad"}
        run = await api.contract_run_detail(run_id)
        assert run["status"] == "cancelled"

    asyncio.run(_scenario())


def test_chat_without_a_valley_is_refused():
    api.set_valley(None)
    with pytest.raises(HTTPException) as err:
        asyncio.run(api.contract_chat({"message": "hello"}))
    assert err.value.status_code == 409

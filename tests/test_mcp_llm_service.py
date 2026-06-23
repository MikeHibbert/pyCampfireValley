from datetime import timedelta
from types import SimpleNamespace

import pytest

from campfirevalley.llm_campfire import LLMCampfire
from campfirevalley.llm_service import AIInferenceService
from campfirevalley.models import CampfireConfig, Torch, VALIServiceResponse
from campfirevalley.vali import VALICoordinator, VALIServiceRegistry, VALIServiceType


class _MemoryBroker:
    def __init__(self):
        self._connected = False
        self._subscriptions = {}
        self.published = []

    async def connect(self):
        self._connected = True
        return True

    async def disconnect(self):
        self._connected = False
        self._subscriptions.clear()
        return True

    def is_connected(self):
        return self._connected

    async def subscribe(self, channel, callback):
        self._subscriptions.setdefault(channel, []).append(callback)
        return True

    async def unsubscribe(self, channel):
        self._subscriptions.pop(channel, None)
        return True

    async def publish(self, channel, message, priority="normal", target_valley=None):
        self.published.append((channel, message))
        for callback in list(self._subscriptions.get(channel, [])):
            await callback(channel, message)
        return True


@pytest.mark.asyncio
async def test_vali_ai_inference_round_trips_via_mcp(monkeypatch):
    async def _fake_run(prompt, model, base_url, timeout_seconds, think=False):
        assert prompt == "Say hello"
        assert model == "gemma4:e4b"
        assert timeout_seconds == 95.0
        assert think is False
        return {"text": "hello from mcp", "endpoint": "generate", "raw_status": 200}

    monkeypatch.setattr("campfirevalley.llm_service.run_ollama_inference", _fake_run)

    broker = _MemoryBroker()
    await broker.connect()
    registry = VALIServiceRegistry()
    coordinator = VALICoordinator(broker, registry, valley_name="Local Valley")
    await coordinator.start()
    await coordinator.register_service(AIInferenceService(default_ollama_host="http://ollama", default_timeout_seconds=90))

    response = await coordinator.request_service_via_mcp(
        VALIServiceType.AI_INFERENCE,
        payload={
            "provider": "ollama",
            "prompt": "Say hello",
            "model": "gemma4:e4b",
            "base_url": "http://ollama",
            "campfire_name": "Alpha",
        },
        requirements={"timeout_seconds": 95},
        timeout=timedelta(seconds=2),
    )

    await coordinator.stop()

    assert response.status == "completed"
    assert response.deliverables["text"] == "hello from mcp"
    assert response.deliverables["model"] == "gemma4:e4b"
    assert response.metadata["think"] is False
    assert any(channel == "vali.requests" for channel, _ in broker.published)
    assert any(channel.startswith("vali.responses.") for channel, _ in broker.published)


@pytest.mark.asyncio
async def test_vali_ai_inference_allows_think_override(monkeypatch):
    async def _fake_run(prompt, model, base_url, timeout_seconds, think=False):
        assert think == "low"
        return {"text": "hello with low think", "endpoint": "generate", "raw_status": 200}

    monkeypatch.setattr("campfirevalley.llm_service.run_ollama_inference", _fake_run)

    broker = _MemoryBroker()
    await broker.connect()
    registry = VALIServiceRegistry()
    coordinator = VALICoordinator(broker, registry, valley_name="Local Valley")
    await coordinator.start()
    await coordinator.register_service(AIInferenceService(default_ollama_host="http://ollama", default_timeout_seconds=90))

    response = await coordinator.request_service_via_mcp(
        VALIServiceType.AI_INFERENCE,
        payload={
            "provider": "ollama",
            "prompt": "Say hello",
            "model": "gemma4:e4b",
            "base_url": "http://ollama",
            "campfire_name": "Alpha",
            "think": "low",
        },
        requirements={"timeout_seconds": 95},
        timeout=timedelta(seconds=2),
    )

    await coordinator.stop()

    assert response.status == "completed"
    assert response.metadata["think"] == "low"


@pytest.mark.asyncio
async def test_llm_campfire_prefers_mcp_for_ollama():
    class _FakeCoordinator:
        def __init__(self):
            self.calls = []

        async def request_service_via_mcp(self, service_type, payload, requirements=None, timeout=None):
            self.calls.append(
                {
                    "service_type": service_type,
                    "payload": payload,
                    "requirements": requirements,
                    "timeout": timeout,
                }
            )
            return VALIServiceResponse(
                request_id="vali_test",
                status="completed",
                deliverables={"text": "reply via mcp", "model": "gemma4:e4b"},
                metadata={},
            )

    class _DirectCamper:
        def __init__(self):
            self.calls = 0

        async def process_with_llm(self, prompt, model=None):
            self.calls += 1
            return "reply via direct"

    campfire = LLMCampfire.__new__(LLMCampfire)
    campfire.config = CampfireConfig(
        name="Alpha",
        type="LLMCampfire",
        config={"llm": {"provider": "ollama", "model": "gemma4:e4b", "base_url": "http://ollama"}},
    )
    campfire.llm_config = SimpleNamespace(default_model="gemma4:e4b")
    campfire.vali_coordinator = _FakeCoordinator()
    campfire._llm_camper = _DirectCamper()

    async def _return_response(torch, prompt, response, model=None):
        return response

    campfire._maybe_run_zeitgeist_tools = _return_response
    campfire._prepare_context_prompt = lambda torch, prompt: prompt

    torch = Torch(
        claim="voice_text",
        source_campfire="voice",
        channel="voice",
        sender_valley="Caller Valley",
        target_address="Local Valley:Alpha",
        data={"text": "Hello"},
        signature="voice_placeholder",
    )

    result = await LLMCampfire.process_torch_with_llm(campfire, torch, "Hello", model="gemma4:e4b")

    assert result is not None
    assert result.data["llm_response"] == "reply via mcp"
    assert result.data["llm_model"] == "gemma4:e4b"
    assert campfire._llm_camper.calls == 0
    assert len(campfire.vali_coordinator.calls) == 1
    assert campfire.vali_coordinator.calls[0]["service_type"] == VALIServiceType.AI_INFERENCE
    assert campfire.vali_coordinator.calls[0]["requirements"]["timeout_seconds"] > 30.0

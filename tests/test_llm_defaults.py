import campfirevalley.web.api as api
from campfirevalley.llm_defaults import get_default_ollama_model


def test_get_default_ollama_model_uses_env_override(monkeypatch):
    monkeypatch.setenv("DEFAULT_OLLAMA_MODEL", "custom-gemma:latest")

    assert get_default_ollama_model() == "custom-gemma:latest"


def test_runtime_defaults_endpoint_returns_shared_ollama_model(monkeypatch):
    monkeypatch.setenv("DEFAULT_OLLAMA_MODEL", "custom-gemma:latest")

    payload = api.get_runtime_defaults()

    assert payload["status"] == "ok"
    assert payload["defaults"]["ollama_model"] == "custom-gemma:latest"

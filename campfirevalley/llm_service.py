"""
MCP-backed LLM inference service implementations.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, Optional, Set

import httpx

from .llm_defaults import get_default_ollama_model
from .models import VALIServiceRequest, VALIServiceResponse
from .vali import BaseVALIService, VALIServiceStatus, VALIServiceType


logger = logging.getLogger(__name__)

_OLLAMA_MODELS_CACHE: Dict[str, Any] = {"ts": 0.0, "models": set()}


def get_llm_timeout_seconds() -> float:
    raw = os.getenv("LLM_INFERENCE_TIMEOUT_SECONDS") or os.getenv("OLLAMA_TIMEOUT_SECONDS") or "180"
    try:
        return max(10.0, float(raw))
    except Exception:
        return 180.0


def get_default_ollama_think_value() -> Any:
    raw = os.getenv("OLLAMA_THINK")
    if raw is None or not str(raw).strip():
        return False
    value = str(raw).strip().lower()
    if value in {"true", "1", "yes", "on"}:
        return True
    if value in {"false", "0", "no", "off"}:
        return False
    if value in {"low", "medium", "high"}:
        return value
    return False


async def get_ollama_model_names(base_url: str) -> Set[str]:
    now = time.time()
    ts = float(_OLLAMA_MODELS_CACHE.get("ts") or 0.0)
    cached = _OLLAMA_MODELS_CACHE.get("models")
    if isinstance(cached, set) and cached and (now - ts) < 60.0:
        return cached
    models: Set[str] = set()
    url = (base_url or "").rstrip("/") + "/api/tags"
    try:
        timeout = httpx.Timeout(10.0, connect=5.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url)
        if response.status_code == 200:
            data = response.json() if response.content else {}
            items = data.get("models") if isinstance(data, dict) else None
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, dict):
                        name = str(item.get("name") or "").strip()
                        if name:
                            models.add(name)
    except Exception:
        models = set()
    if models:
        _OLLAMA_MODELS_CACHE["ts"] = now
        _OLLAMA_MODELS_CACHE["models"] = models
    return models


def _extract_ollama_text(data: Dict[str, Any]) -> str:
    if not isinstance(data, dict):
        return ""
    text = str(data.get("response") or "").strip()
    if text:
        return text
    message = data.get("message")
    if isinstance(message, dict):
        return str(message.get("content") or "").strip()
    return ""


async def run_ollama_inference(
    prompt: str,
    model: str,
    base_url: str,
    timeout_seconds: float,
    think: Any = False,
) -> Dict[str, Any]:
    host = (base_url or "").rstrip("/")
    model_name = str(model or "").strip() or get_default_ollama_model()
    timeout = httpx.Timeout(timeout_seconds, connect=min(10.0, timeout_seconds))
    async with httpx.AsyncClient(timeout=timeout) as client:
        generate_payload = {"model": model_name, "prompt": prompt, "stream": False, "think": think}
        generate_response = await client.post(f"{host}/api/generate", json=generate_payload)
        if generate_response.status_code == 200:
            body = generate_response.json() if generate_response.content else {}
            return {
                "text": _extract_ollama_text(body),
                "endpoint": "generate",
                "raw_status": generate_response.status_code,
            }
        logger.warning(
            "Ollama generate failed with status %s, trying chat fallback",
            generate_response.status_code,
        )
        chat_payload = {
            "model": model_name,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "think": think,
        }
        chat_response = await client.post(f"{host}/api/chat", json=chat_payload)
        chat_response.raise_for_status()
        body = chat_response.json() if chat_response.content else {}
        return {
            "text": _extract_ollama_text(body),
            "endpoint": "chat",
            "raw_status": chat_response.status_code,
        }


class AIInferenceService(BaseVALIService):
    """Brokered AI inference service used by campfires via MCP/VALI."""

    def __init__(self, default_ollama_host: Optional[str] = None, default_timeout_seconds: Optional[float] = None):
        super().__init__(
            VALIServiceType.AI_INFERENCE,
            {
                "providers": ["ollama"],
                "default_timeout_seconds": default_timeout_seconds or get_llm_timeout_seconds(),
                "default_think": get_default_ollama_think_value(),
            },
        )
        self.default_ollama_host = (
            str(default_ollama_host or os.getenv("OLLAMA_HOST") or "http://host.docker.internal:11434").strip()
        )
        self.default_timeout_seconds = float(default_timeout_seconds or get_llm_timeout_seconds())
        self.default_think = get_default_ollama_think_value()

    async def process_request(self, request: VALIServiceRequest) -> VALIServiceResponse:
        started = time.perf_counter()
        try:
            payload = request.payload if isinstance(request.payload, dict) else {}
            requirements = request.requirements if isinstance(request.requirements, dict) else {}
            provider = str(payload.get("provider") or "ollama").strip().lower()
            if provider != "ollama":
                return VALIServiceResponse(
                    request_id=request.request_id,
                    status=VALIServiceStatus.FAILED.value,
                    deliverables={},
                    metadata={"error": f"Unsupported MCP inference provider: {provider}"},
                )
            prompt = str(payload.get("prompt") or "").strip()
            if not prompt:
                return VALIServiceResponse(
                    request_id=request.request_id,
                    status=VALIServiceStatus.FAILED.value,
                    deliverables={},
                    metadata={"error": "Missing prompt for MCP inference"},
                )
            base_url = str(payload.get("base_url") or self.default_ollama_host).strip()
            fallback_model = str(payload.get("fallback_model") or get_default_ollama_model()).strip()
            requested_model = str(payload.get("model") or fallback_model).strip() or fallback_model
            think = payload.get("think", self.default_think)
            if think is None or (isinstance(think, str) and not think.strip()):
                think = self.default_think
            timeout_seconds = self.default_timeout_seconds
            try:
                timeout_seconds = max(10.0, float(requirements.get("timeout_seconds") or timeout_seconds))
            except Exception:
                timeout_seconds = self.default_timeout_seconds
            available_models = await get_ollama_model_names(base_url)
            used_model = requested_model
            if available_models and requested_model not in available_models:
                used_model = fallback_model if fallback_model in available_models else requested_model
            inference = await run_ollama_inference(prompt, used_model, base_url, timeout_seconds, think=think)
            text = str(inference.get("text") or "").strip()
            status = VALIServiceStatus.COMPLETED.value if text else VALIServiceStatus.FAILED.value
            return VALIServiceResponse(
                request_id=request.request_id,
                status=status,
                deliverables={
                    "text": text,
                    "model": used_model,
                    "provider": provider,
                    "endpoint": inference.get("endpoint") or "",
                },
                metadata={
                    "requested_model": requested_model,
                    "latency_ms": round((time.perf_counter() - started) * 1000, 2),
                    "timeout_seconds": timeout_seconds,
                    "think": think,
                    "campfire_name": str(payload.get("campfire_name") or "").strip(),
                },
            )
        except Exception as exc:
            logger.error("AI inference service failed: %s", exc)
            return VALIServiceResponse(
                request_id=request.request_id,
                status=VALIServiceStatus.FAILED.value,
                deliverables={},
                metadata={
                    "error": str(exc),
                    "latency_ms": round((time.perf_counter() - started) * 1000, 2),
                },
            )

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


async def get_ollama_model_names(base_url: str, api_key: Optional[str] = None) -> Set[str]:
    now = time.time()
    ts = float(_OLLAMA_MODELS_CACHE.get("ts") or 0.0)
    cached = _OLLAMA_MODELS_CACHE.get("models")
    if isinstance(cached, set) and cached and (now - ts) < 60.0:
        return cached
    models: Set[str] = set()
    url = (base_url or "").rstrip("/") + "/api/tags"
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    try:
        timeout = httpx.Timeout(10.0, connect=5.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url, headers=headers)
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
    api_key: Optional[str] = None,
) -> Dict[str, Any]:
    host = (base_url or "").rstrip("/")
    model_name = str(model or "").strip() or get_default_ollama_model()
    timeout = httpx.Timeout(timeout_seconds, connect=min(10.0, timeout_seconds))
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    async with httpx.AsyncClient(timeout=timeout) as client:
        _markers = [
            "\n\nUser Request:", "\nUser Request:", "User Request:",
            "\n\nUser request: ", "\n\nUser request:", "\nUser request: ", "\nUser request:",
            "User request: ", "User request:",
            "\n\nUSER REQUEST:", "\nUSER REQUEST:", "USER REQUEST:",
        ]
        _split_idx = -1
        _marker = ""
        for _m in _markers:
            _idx = prompt.find(_m)
            if _idx != -1:
                _split_idx = _idx
                _marker = _m
                break
        if _split_idx == -1:
            import re as _re
            _m = _re.search(r"(?i)user\s*request\s*:", prompt)
            if _m:
                _split_idx = _m.start()
                _marker = prompt[_m.start():_m.end()]
        if _split_idx != -1:
            _system_part = prompt[:_split_idx].strip()
            _user_part = prompt[_split_idx + len(_marker):].strip()
        else:
            _system_part = ""
            _user_part = prompt
            _marker = "none"
        import logging as _log
        _log.getLogger("ollama_split").info(
            "OLLAMA SPLIT marker=%s system_len=%d user_len=%d",
            _marker, len(_system_part), len(_user_part)
        )
        generate_payload = {"model": model_name, "prompt": _user_part if _system_part else prompt, "stream": False, "think": think, "options": {"temperature": 0.0, "num_ctx": 4096, "use_cache": False, "cfg_scale": 2.0}}
        if _system_part:
            generate_payload["system"] = _system_part
        generate_response = await client.post(f"{host}/api/generate", json=generate_payload, headers=headers)
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
        _chat_messages = []
        if _system_part:
            _chat_messages.append({"role": "system", "content": _system_part})
        _chat_messages.append({"role": "user", "content": _user_part or prompt})
        chat_payload = {
            "model": model_name,
            "messages": _chat_messages,
            "stream": False,
            "think": think,
            "options": {"temperature": 0.0, "num_ctx": 4096, "use_cache": False, "cfg_scale": 2.0},
        }
        chat_response = await client.post(f"{host}/api/chat", json=chat_payload, headers=headers)
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
                "providers": ["ollama", "ollama_cloud"],
                "default_timeout_seconds": default_timeout_seconds or get_llm_timeout_seconds(),
                "default_think": get_default_ollama_think_value(),
            },
        )
        self.default_ollama_host = (
            str(default_ollama_host or os.getenv("OLLAMA_HOST") or "http://host.docker.internal:11434").strip()
        )
        self.default_ollama_cloud_host = (
            str(os.getenv("OLLAMA_CLOUD_HOST") or "https://ollama.com").strip()
        )
        self.default_timeout_seconds = float(default_timeout_seconds or get_llm_timeout_seconds())
        self.default_think = get_default_ollama_think_value()

    async def process_request(self, request: VALIServiceRequest) -> VALIServiceResponse:
        started = time.perf_counter()
        try:
            payload = request.payload if isinstance(request.payload, dict) else {}
            requirements = request.requirements if isinstance(request.requirements, dict) else {}
            provider = str(payload.get("provider") or "ollama").strip().lower()
            if provider not in ("ollama", "ollama_cloud"):
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
            is_cloud = provider == "ollama_cloud"
            base_url = str(payload.get("base_url") or (
                self.default_ollama_cloud_host if is_cloud else self.default_ollama_host
            )).strip()
            api_key = str(payload.get("api_key") or (
                os.getenv("OLLAMA_CLOUD_API_KEY") if is_cloud else os.getenv("OLLAMA_API_KEY")
            ) or "").strip() or None
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
            available_models = await get_ollama_model_names(base_url, api_key=api_key)
            used_model = requested_model
            if available_models and requested_model not in available_models:
                used_model = fallback_model if fallback_model in available_models else requested_model
            inference = await run_ollama_inference(
                prompt, used_model, base_url, timeout_seconds, think=think, api_key=api_key
            )
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

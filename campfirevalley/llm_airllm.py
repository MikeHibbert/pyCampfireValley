"""AirLLM provider for CampfireValley.

AirLLM enables running large models (70B+) on consumer GPUs via
layer-wise streaming (loading one layer at a time). This module
provides an Ollama-compatible REST API wrapper so that CampfireValley
can use an AirLLM server as an LLM backend.

Configuration:
    Set ``OLLAMA_BASE_URL`` to the AirLLM wrapper's address
    (default: ``http://airllm-wrapper:8012``).
    Set ``OLLAMA_MODEL`` to the AirLLM model name
    (e.g. ``Qwen/Qwen3-32B``).

The AirLLM wrapper exposes Ollama-compatible ``/api/chat`` and
``/api/generate`` endpoints, so CampfireValley's existing Ollama
code paths work without modification — only the base URL and model
name differ.
"""

from __future__ import annotations

import os
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def get_airllm_base_url() -> str:
    """Return the AirLLM wrapper's base URL."""
    return os.getenv("AIRLLM_BASE_URL", "http://airllm-wrapper:8012")


def get_airllm_model() -> str:
    """Return the configured AirLLM model name."""
    return os.getenv("AIRLLM_MODEL", "Qwen/Qwen3-32B")


def is_airllm_configured() -> bool:
    """Check if AirLLM is the active provider."""
    return os.getenv("LLM_PROVIDER", "").lower() == "airllm"


async def run_airllm_inference(
    prompt: str,
    model: str = "",
    think: bool = False,
    system_part: str = "",
    user_part: str = "",
) -> Dict[str, Any]:
    """Run inference via the AirLLM wrapper (Ollama-compatible API).

    Returns a dict with keys:
        - ``text``: the generated response text
        - ``endpoint``: ``"generate"`` or ``"chat"``
        - ``raw_status``: HTTP status code
    """
    import httpx
    from .llm_service import get_llm_timeout_seconds, _extract_ollama_text

    host = get_airllm_base_url()
    model_name = str(model or "").strip() or get_airllm_model()
    timeout = get_llm_timeout_seconds()

    # Try /api/generate first (simpler, faster for single-turn)
    generate_payload: Dict[str, Any] = {
        "model": model_name,
        "prompt": user_part if system_part else prompt,
        "stream": False,
        "think": think,
        "options": {"temperature": 0.0, "num_ctx": 4096, "use_cache": False, "cfg_scale": 2.0},
    }
    if system_part:
        generate_payload["system"] = system_part

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(f"{host}/api/generate", json=generate_payload)
            if resp.status_code == 200:
                body = resp.json() if resp.content else {}
                return {
                    "text": _extract_ollama_text(body),
                    "endpoint": "generate",
                    "raw_status": resp.status_code,
                }
            logger.warning("AirLLM generate failed with status %s, trying chat", resp.status_code)
    except Exception as e:
        logger.warning("AirLLM generate failed: %s, trying chat", e)

    # Fall back to /api/chat
    messages: list[dict] = []
    if system_part:
        messages.append({"role": "system", "content": system_part})
    messages.append({"role": "user", "content": user_part or prompt})

    chat_payload: Dict[str, Any] = {
        "model": model_name,
        "messages": messages,
        "stream": False,
        "think": think,
        "options": {"temperature": 0.0, "num_ctx": 4096, "use_cache": False, "cfg_scale": 2.0},
    }

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(f"{host}/api/chat", json=chat_payload)
            if resp.status_code == 200:
                body = resp.json() if resp.content else {}
                msg = body.get("message", {})
                return {
                    "text": msg.get("content", "") or _extract_ollama_text(body),
                    "endpoint": "chat",
                    "raw_status": resp.status_code,
                }
    except Exception as e:
        logger.error("AirLLM chat also failed: %s", e)

    return {"text": "", "endpoint": "failed", "raw_status": 0}
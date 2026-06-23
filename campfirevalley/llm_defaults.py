"""Shared LLM default settings."""

import os


DEFAULT_OLLAMA_MODEL_FALLBACK = "gemma4:e4b"


def get_default_ollama_model() -> str:
    value = (os.getenv("DEFAULT_OLLAMA_MODEL") or "").strip()
    return value or DEFAULT_OLLAMA_MODEL_FALLBACK

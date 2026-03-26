import base64
from dataclasses import dataclass
from typing import Optional, Dict, Any
import httpx

from .config_manager import get_config_manager


@dataclass
class STTConfig:
    default_engine: str = "parakeet_local"
    parakeet_endpoint: str = "http://localhost:8765/transcribe"
    timeout_seconds: float = 30.0


class STTEngine:
    async def transcribe(self, *, audio_bytes: Optional[bytes] = None, audio_url: Optional[str] = None) -> str:
        raise NotImplementedError


class ParakeetLocalEngine(STTEngine):
    def __init__(self, cfg: STTConfig):
        self.cfg = cfg

    async def transcribe(self, *, audio_bytes: Optional[bytes] = None, audio_url: Optional[str] = None) -> str:
        headers = {"Content-Type": "application/json"}
        payload: Dict[str, Any] = {}
        if audio_url:
            payload["audio_url"] = audio_url
        elif audio_bytes is not None:
            payload["audio_base64"] = base64.b64encode(audio_bytes).decode("utf-8")
        else:
            raise ValueError("audio_bytes or audio_url required")
        async with httpx.AsyncClient(timeout=self.cfg.timeout_seconds) as client:
            r = await client.post(self.cfg.parakeet_endpoint, json=payload, headers=headers)
            r.raise_for_status()
            data = r.json()
            return data.get("text", "").strip()


class NoopEngine(STTEngine):
    async def transcribe(self, *, audio_bytes: Optional[bytes] = None, audio_url: Optional[str] = None) -> str:
        return ""


async def get_stt_config() -> STTConfig:
    try:
        manager = get_config_manager()
        cfg = await manager.get_config("stt", {})
        return STTConfig(
            default_engine=cfg.get("default_engine", "parakeet_local"),
            parakeet_endpoint=cfg.get("parakeet", {}).get("endpoint", "http://localhost:8765/transcribe"),
            timeout_seconds=float(cfg.get("timeout_seconds", 30.0)),
        )
    except Exception:
        return STTConfig()


async def get_engine() -> STTEngine:
    cfg = await get_stt_config()
    if cfg.default_engine == "parakeet_local":
        return ParakeetLocalEngine(cfg)
    return NoopEngine()


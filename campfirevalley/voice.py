import os
import re
import time
from pathlib import Path
from typing import Optional, Dict, Any


def _read_admin_token() -> Optional[str]:
    p = Path(".secrets") / "admin_token"
    if p.exists():
        return p.read_text(encoding="utf-8").strip()
    return os.environ.get("CAMPFIRE_ADMIN_TOKEN")


def is_admin(token: Optional[str]) -> bool:
    if not token:
        return False
    expected = _read_admin_token()
    if not expected:
        return False
    return token.strip() == expected.strip()


def parse_intent(text: str) -> Dict[str, Any]:
    lower = text.lower().strip()
    m = re.search(r"(?:send|route)\s+to\s+([a-zA-Z0-9_\-]+):\s*(.+)", lower)
    if m:
        return {"type": "chat", "campfire": m.group(1), "content": m.group(2)}
    m2 = re.search(r"(?:campfire|target)\s*=\s*([a-zA-Z0-9_\-]+)\s*[:\-]\s*(.+)", lower)
    if m2:
        return {"type": "chat", "campfire": m2.group(1), "content": m2.group(2)}
    return {"type": "chat", "campfire": None, "content": text}


def make_voice_torch(valley_name: str, campfire: str, text: str, admin: bool) -> Dict[str, Any]:
    target_address = campfire if ":" in campfire else f"{valley_name}:{campfire}"
    return {
        "claim": "voice_text",
        "source_campfire": "voice",
        "channel": "voice",
        "torch_id": f"voice_{int(time.time()*1000)}",
        "sender_valley": valley_name,
        "target_address": target_address,
        "data": {"text": text, "admin": admin},
        "signature": "voice_placeholder",
    }

"""FastAPI backend for CampfireValley web visualization interface"""

import asyncio
import copy
import html
import json
import os
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi import Body, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, Response
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import yaml
import re
import math
import uuid
import httpx

# Prometheus metrics
from prometheus_client import Counter, Gauge, Histogram, generate_latest, CONTENT_TYPE_LATEST

from .models import VisualizationState, WebSocketMessage, NodeUpdate, ConnectionUpdate
from .visualization import ValleyVisualizer
from ..valley import Valley
from ..config import ConfigManager
from ..voice import is_admin, parse_intent, make_voice_torch
from ..stt import get_engine
import base64
from ..models import CampfireConfig, Torch
from ..monitoring import get_monitoring_system, LogLevel
from ..service_catalog import build_service_catalog
from ..llm_defaults import get_default_ollama_model
from ..zeitgeist_plugins import (
    create_google_auth_start,
    finish_google_oauth,
    get_zeitgeist_plugin_catalog,
    gmail_plugin_status,
    google_calendar_plugin_status,
    google_docs_plugin_status,
    google_drive_plugin_status,
    google_sheets_plugin_status,
    peek_google_auth_state,
)


class WebSocketManager:
    """Manages WebSocket connections for real-time updates"""
    
    def __init__(self):
        self.active_connections: List[WebSocket] = []
    
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        campfire_active_connections.set(len(self.active_connections))
    
    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        campfire_active_connections.set(len(self.active_connections))
    
    async def send_personal_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)
    
    async def broadcast(self, message: str):
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except:
                # Remove dead connections
                self.active_connections.remove(connection)


# Prometheus metrics definitions
campfire_requests_total = Counter(
    'campfire_requests_total',
    'Total number of requests to campfires',
    ['campfire_id', 'action']
)

campfire_active_connections = Gauge(
    'campfire_active_connections',
    'Number of active WebSocket connections'
)

campfire_torch_queue_size = Gauge(
    'campfire_torch_queue_size',
    'Current torch queue size for campfires',
    ['campfire_id', 'campfire_type']
)

campfire_camper_count = Gauge(
    'campfire_camper_count',
    'Number of active campers per campfire',
    ['campfire_id', 'campfire_type']
)

campfire_processing_time = Histogram(
    'campfire_processing_time_seconds',
    'Time spent processing tasks',
    ['campfire_id', 'task_type']
)

campfire_throughput = Gauge(
    'campfire_throughput_rate',
    'Current throughput rate for campfires',
    ['campfire_id', 'campfire_type']
)

campfire_error_rate = Gauge(
    'campfire_error_rate',
    'Current error rate for campfires',
    ['campfire_id', 'campfire_type']
)


# Initialize FastAPI app
app = FastAPI(title="CampfireValley Visualization", version="1.1.0")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Get the correct static files path
static_path = os.path.join(os.path.dirname(__file__), "static")


class NoCacheStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope):
        resp = await super().get_response(path, scope)
        try:
            resp.headers["Cache-Control"] = "no-store, max-age=0"
            resp.headers["Pragma"] = "no-cache"
            resp.headers["Expires"] = "0"
        except Exception:
            pass
        return resp


app.mount("/static", NoCacheStaticFiles(directory=static_path), name="static")

# WebSocket manager
manager = WebSocketManager()

# Global state
current_valley: Optional[Valley] = None
visualizer: Optional[ValleyVisualizer] = None
current_state: Optional[VisualizationState] = None
auditor_dialog: Dict[str, Dict] = {"active": False, "fields": {}, "awaiting": []}
dock_enable_task: Optional[asyncio.Task] = None
dock_enable_state: Dict[str, Any] = {"status": "idle", "detail": None, "updated_at": None}
campfire_parent: Dict[str, str] = {}


def _get_config_dir() -> Path:
    return Path(os.getenv("CONFIG_DIR", "/app/data/configs"))


def _get_embeddings_dir() -> Path:
    return Path(os.getenv("EMBEDDINGS_DIR", "/app/data/embeddings"))


def _get_logs_dir() -> Path:
    return Path(os.getenv("LOGS_DIR", "/app/data/logs"))


def _get_rounds_dir() -> Path:
    return _get_config_dir() / "rounds_plans"


def _log_path_for(campfire_name: str) -> Path:
    log_dir = _get_logs_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / f"{_slugify(campfire_name)}.jsonl"


def _append_log(campfire_name: str, role: str, text: str) -> None:
    entry = {
        "ts": datetime.utcnow().isoformat(),
        "campfire": campfire_name,
        "role": role,
        "text": text,
    }
    path = _log_path_for(campfire_name)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _read_logs(campfire_name: str, limit: int = 200) -> List[dict]:
    path = _log_path_for(campfire_name)
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        tail = lines[-limit:] if limit > 0 else lines
        out: List[dict] = []
        for line in tail:
            try:
                obj = json.loads(line)
                if isinstance(obj, dict):
                    out.append(obj)
            except Exception:
                continue
        return out
    except Exception:
        return []


def _write_logs(campfire_name: str, entries: List[dict]) -> None:
    path = _log_path_for(campfire_name)
    with path.open("w", encoding="utf-8") as f:
        for e in entries:
            if not isinstance(e, dict):
                continue
            f.write(json.dumps(e, ensure_ascii=False) + "\n")

def _slugify(text: str) -> str:
    t = re.sub(r"[^a-zA-Z0-9_\-]+", "_", text.strip())
    return t.strip("_") or "campfire"


def _rounds_plan_path(plan_name: str) -> Path:
    rounds_dir = _get_rounds_dir()
    rounds_dir.mkdir(parents=True, exist_ok=True)
    return rounds_dir / f"rounds_plan_{_slugify(plan_name)}.yaml"


def _list_rounds_plans() -> List[Dict[str, Any]]:
    rounds_dir = _get_rounds_dir()
    rounds_dir.mkdir(parents=True, exist_ok=True)
    plans: List[Dict[str, Any]] = []
    for path in sorted(rounds_dir.glob("rounds_plan_*.yaml")):
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception:
            continue
        if not isinstance(raw, dict):
            continue
        plan_name = str(raw.get("name") or "").strip()
        if not plan_name:
            continue
        plans.append({
            "name": plan_name,
            "description": str(raw.get("description") or "").strip(),
            "campfire": str(raw.get("campfire") or "").strip(),
            "round_count": len(raw.get("rounds") or []),
            "updated_at": str(raw.get("updated_at") or ""),
            "created_at": str(raw.get("created_at") or ""),
        })
    plans.sort(key=lambda p: ((p.get("name") or "").lower(), p.get("updated_at") or ""), reverse=False)
    return plans


def _load_rounds_plan(plan_name: str) -> Dict[str, Any]:
    name = (plan_name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Missing plan name")
    path = _rounds_plan_path(name)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Rounds plan not found")
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load rounds plan: {e}")
    if not isinstance(raw, dict):
        raise HTTPException(status_code=500, detail="Rounds plan file is invalid")
    return raw


def _hash_embed(texts: List[str], dims: int = 384) -> List[List[float]]:
    vectors: List[List[float]] = []
    for t in texts:
        v = [0.0] * dims
        for token in re.findall(r"[a-zA-Z0-9']+", (t or "").lower()):
            idx = (hash(token) & 0x7FFFFFFF) % dims
            v[idx] += 1.0
        norm = math.sqrt(sum(x * x for x in v)) or 1.0
        vectors.append([x / norm for x in v])
    return vectors


def _embed_texts(texts: List[str]) -> List[List[float]]:
    impl = (os.getenv("BELIEFS_EMBEDDING_IMPL") or "hash").strip().lower()
    if impl != "st":
        return _hash_embed(texts)
    try:
        from sentence_transformers import SentenceTransformer
        model_name = os.getenv("BELIEFS_EMBED_MODEL", "all-MiniLM-L6-v2")
        model = SentenceTransformer(model_name)
        emb = model.encode(texts, normalize_embeddings=True)
        return [row.tolist() for row in emb]
    except Exception:
        return _hash_embed(texts)


def _get_beliefs_collection():
    import chromadb
    embed_dir = _get_embeddings_dir()
    embed_dir.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(embed_dir / "chroma"))
    return client.get_or_create_collection(name="campfirevalley_beliefs")


def _query_beliefs(campfire_name: str, query: str, k: int = 5) -> List[str]:
    collection = _get_beliefs_collection()
    qemb = _embed_texts([query])[0]
    result = collection.query(
        query_embeddings=[qemb],
        n_results=k,
        where={"campfire": campfire_name},
        include=["documents"]
    )
    docs = (result or {}).get("documents") or []
    if docs and isinstance(docs[0], list):
        return [d for d in docs[0] if isinstance(d, str)]
    return []


def _extract_beliefs(campfire_name: str, campfire_config: Optional[CampfireConfig], messages: List[dict]) -> List[str]:
    beliefs: List[str] = []
    if campfire_config:
        sys_prompt = (campfire_config.config or {}).get("prompts", {}).get("system") if isinstance(campfire_config.config, dict) else ""
        sys_prompt = sys_prompt or campfire_config.prompts.get("system") if isinstance(campfire_config.prompts, dict) else ""
        if sys_prompt:
            beliefs.append(f"Role: {sys_prompt.strip()[:240]}")
        persona = (campfire_config.config or {}).get("persona") if isinstance(campfire_config.config, dict) else None
        if isinstance(persona, dict):
            if persona.get("persona"):
                beliefs.append(f"Persona: {str(persona.get('persona')).strip()[:200]}")
            if persona.get("name"):
                beliefs.append(f"Name: {str(persona.get('name')).strip()[:120]}")
    beliefs.append(f"Campfire name: {campfire_name}")

    for m in messages[-60:]:
        role = (m.get("role") or "").lower()
        text = (m.get("text") or "").strip()
        if not text:
            continue
        if role == "user":
            pref = re.search(r"\b(i\s+prefer|please\s+be|keep\s+it|always|never)\b(.+)", text, re.IGNORECASE)
            if pref:
                beliefs.append(f"User preference: {pref.group(0).strip()[:220]}")
            if "my name is" in text.lower():
                beliefs.append(f"User identity: {text.strip()[:180]}")
        if role == "system":
            if "you are" in text.lower() or "rules" in text.lower():
                beliefs.append(f"Instruction: {text.strip()[:220]}")

    deduped: List[str] = []
    seen = set()
    for b in beliefs:
        k = b.lower()
        if k in seen:
            continue
        seen.add(k)
        deduped.append(b)
    return deduped[:40]


def _default_rag_documents(campfire_name: str, persona: Optional[str] = None) -> List[str]:
    p = (persona or "").strip()
    head = f"Campfire: {campfire_name}"
    if p:
        head += f"\nPersona: {p}"
    return [
        head
        + "\n\nUse this as your working context:\n"
          "- In CampfireValley, a campfire is a software role/module or collaborative workspace, not a physical fire.\n"
          "- Treat campers, auditors, torches, and rounds as software orchestration concepts unless the user explicitly says otherwise.\n"
          "- Ask 1-2 clarifying questions when requirements are ambiguous.\n"
          "- Prefer concrete, step-by-step answers.\n"
          "- When you make an assumption, state it plainly.\n"
          "- If the user asks for changes, propose the minimal safe change that satisfies the request.\n"
    ]


def _software_campfire_system_prompt(name: str, persona: Optional[str] = None) -> str:
    campfire_name = (name or "Campfire").strip() or "Campfire"
    role = (persona or "").strip()
    role_line = f"Primary role/persona: {role}.\n" if role else ""
    return (
        f"You are {campfire_name}, a software campfire inside the CampfireValley Python system.\n"
        "In this context, a campfire is an AI role/module or collaborative workspace, not a literal outdoor fire.\n"
        "Campers are specialized sub-roles, auditors coordinate work, torches carry requests and results, and rounds chain outputs across campfires.\n"
        f"{role_line}"
        "Help with software tasks, orchestration, analysis, planning, and implementation work in that context.\n"
        "If a request is ambiguous, ask a brief clarifying question instead of inventing physical campfire details.\n"
        "Respond concisely and use CampfireValley terminology correctly."
    )


def _is_auditor_target(target: Any) -> bool:
    if not isinstance(target, str):
        return False
    t = target.strip().lower()
    return t == "auditor" or t.endswith(" auditor")


def _parent_from_auditor_name(auditor_name: str) -> Optional[str]:
    if not isinstance(auditor_name, str):
        return None
    t = auditor_name.strip()
    if not t.lower().endswith(" auditor"):
        return None
    return t[: -len(" Auditor")].strip() or None


def _parse_remove_camper_command(text: str) -> Optional[str]:
    if not text or not isinstance(text, str):
        return None
    t = text.strip()
    low = t.lower()
    if not (
        low.startswith("remove camper") or low.startswith("remove a camper")
        or low.startswith("delete camper") or low.startswith("delete a camper")
    ):
        return None
    m = re.search(r"(?:remove|delete)\s+(?:a\s+)?camper\s+(.+)$", t, re.IGNORECASE)
    if m:
        name = m.group(1).strip()
        return name if name else None
    return ""


def _parse_delete_campfire_command(text: str) -> Optional[dict]:
    if not text or not isinstance(text, str):
        return None
    t = text.strip().strip("`").strip()
    low = t.lower()
    confirm = False
    if low.startswith("confirm "):
        confirm = True
        t = t[len("confirm "):].strip()
        low = t.lower()
    if not (
        low.startswith("delete campfire")
        or low.startswith("remove campfire")
        or low.startswith("delete a campfire")
        or low.startswith("remove a campfire")
        or low.startswith("delete team")
        or low.startswith("remove team")
    ):
        return None
    m = re.search(r"(?:delete|remove)\s+(?:a\s+)?(?:campfire|team)\s*(.*)$", t, re.IGNORECASE)
    name = ""
    if m:
        name = (m.group(1) or "").strip().strip("\"'").strip()
    return {"name": name, "confirm": confirm}


def _parse_rename_camper_command(text: str) -> Optional[dict]:
    if not text or not isinstance(text, str):
        return None
    t = text.strip()
    low = t.lower()
    if not (
        low.startswith("rename camper") or low.startswith("rename a camper")
        or low.startswith("rename campa") or low.startswith("rename a campa")
    ):
        return None
    rest = t.split(" ", 1)[1] if " " in t else ""
    rest = rest.replace("camper", "", 1).replace("campa", "", 1).strip()
    if not rest:
        return {"old": "", "new": ""}
    m = re.match(r"^(?P<old>\"[^\"]+\"|'[^']+'|.+?)\s*(?:to|as|->)\s*(?P<new>\"[^\"]+\"|'[^']+'|.+)$", rest, re.IGNORECASE)
    if m:
        old = (m.group("old") or "").strip().strip("\"'").strip()
        new = (m.group("new") or "").strip().strip("\"'").strip()
        return {"old": old, "new": new}
    old = rest.strip().strip("\"'").strip()
    return {"old": old, "new": ""}


def _rename_file_if_exists(src: Path, dst: Path) -> None:
    try:
        if src.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            if dst.exists():
                return
            src.rename(dst)
    except Exception:
        pass


def _rename_campfire_artifacts(old_name: str, new_name: str) -> None:
    if not old_name or not new_name:
        return
    _rename_file_if_exists(_log_path_for(old_name), _log_path_for(new_name))
    cfg_dir = _get_config_dir()
    _rename_file_if_exists(
        cfg_dir / f"camper_{_slugify(old_name)}_beliefs.yaml",
        cfg_dir / f"camper_{_slugify(new_name)}_beliefs.yaml",
    )
    _rename_file_if_exists(
        cfg_dir / f"campfire_{_slugify(old_name)}.yaml",
        cfg_dir / f"campfire_{_slugify(new_name)}.yaml",
    )


def _parse_set_schedule_command(text: str) -> Optional[dict]:
    if not text or not isinstance(text, str):
        return None
    t = text.strip()
    low = t.lower()
    if not low.startswith("set schedule"):
        return None
    rest = t[len("set schedule"):].strip()
    m = re.match(r"^(?P<num>\d+)\s*(?P<unit>s|sec|secs|second|seconds|m|min|mins|minute|minutes)?\s*(?P<input>.*)$", rest, re.IGNORECASE)
    if not m:
        return {}
    n = int(m.group("num"))
    unit = (m.group("unit") or "s").lower()
    if unit.startswith("m"):
        n = n * 60
    input_text = (m.group("input") or "").strip()
    return {"interval_seconds": n, "input": input_text}


def _campers_for_parent(parent: str) -> List[str]:
    if not current_valley or not parent:
        return []
    out: List[str] = []
    for name, p in list(campfire_parent.items()):
        if p != parent:
            continue
        if name not in current_valley.campfires:
            continue
        if _is_auditor_target(name):
            continue
        out.append(name)
    return sorted(out)


def _top_level_campfires() -> List[str]:
    if not current_valley:
        return []
    child_names = set(campfire_parent.keys())
    out: List[str] = []
    for name in sorted(current_valley.campfires.keys()):
        if _is_auditor_target(name):
            continue
        if name in child_names:
            continue
        out.append(name)
    return out


def _parse_run_rounds_command(text: str) -> Optional[dict]:
    if not text or not isinstance(text, str):
        return None
    t = text.strip().strip("`").strip()
    low = t.lower()
    preview = False
    prefix = ""
    for p, is_preview in (
        ("preview rounds", True),
        ("run rounds", False),
        ("execute rounds", False),
    ):
        if low.startswith(p):
            preview = is_preview
            prefix = p
            break
    if not prefix:
        return None
    rest = t[len(prefix):].strip()
    if ":" not in rest:
        return {"preview": preview, "rounds": [], "task": ""}
    chain_part, task = rest.split(":", 1)
    rounds = [p.strip().strip("\"'").strip() for p in re.split(r"\s*->\s*", chain_part) if p and p.strip()]
    return {"preview": preview, "rounds": rounds, "task": task.strip()}


def _cleanup_campfire_artifacts(campfire_name: str) -> None:
    if not campfire_name:
        return
    try:
        p = _log_path_for(campfire_name)
        if p.exists():
            p.unlink()
    except Exception:
        pass
    try:
        if current_valley and getattr(current_valley, "_workflow_path_for", None):
            wf_path = current_valley._workflow_path_for(campfire_name)
            if wf_path.exists():
                wf_path.unlink()
    except Exception:
        pass
    try:
        cfg_dir = _get_config_dir()
        belief_path = cfg_dir / f"camper_{_slugify(campfire_name)}_beliefs.yaml"
        if belief_path.exists():
            belief_path.unlink()
    except Exception:
        pass
    try:
        cfg_dir = _get_config_dir()
        campfire_path = cfg_dir / f"campfire_{_slugify(campfire_name)}.yaml"
        if campfire_path.exists():
            campfire_path.unlink()
    except Exception:
        pass
    try:
        collection = _get_beliefs_collection()
        collection.delete(where={"campfire": campfire_name})
    except Exception:
        pass


def _collect_cascade_delete_targets(root_name: str) -> Dict[str, List[str]]:
    root = (root_name or "").strip()
    if not root:
        return {"campfires": [], "auditors": [], "campers": [], "all": []}
    seen: set[str] = set()
    campfires: List[str] = []
    auditors: List[str] = []
    campers: List[str] = []

    def visit_campfire(name: str) -> None:
        nm = (name or "").strip()
        if not nm or nm in seen:
            return
        seen.add(nm)
        campfires.append(nm)
        auditor_name = f"{nm} Auditor"
        if current_valley and auditor_name in current_valley.campfires and auditor_name not in seen:
            seen.add(auditor_name)
            auditors.append(auditor_name)
        child_candidates: List[str] = list(_campers_for_parent(nm))
        try:
            wf = current_valley.get_workflow(nm) if current_valley and getattr(current_valley, "get_workflow", None) else None
            for step in (wf.get("steps") if isinstance(wf, dict) else []) or []:
                if not isinstance(step, dict):
                    continue
                camper_name = (step.get("camper") or "").strip()
                if camper_name and camper_name not in child_candidates:
                    child_candidates.append(camper_name)
        except Exception:
            pass
        for child in child_candidates:
            child_name = (child or "").strip()
            if not child_name or child_name in seen:
                continue
            if current_valley and child_name in current_valley.campfires:
                campers.append(child_name)
            seen.add(child_name)
            child_auditor = f"{child_name} Auditor"
            if current_valley and child_auditor in current_valley.campfires and child_auditor not in seen:
                seen.add(child_auditor)
                auditors.append(child_auditor)

    visit_campfire(root)
    return {
        "campfires": campfires,
        "auditors": auditors,
        "campers": campers,
        "all": campers + auditors + campfires,
    }


def _delete_summary_for_campfire(root_name: str) -> Dict[str, List[str]]:
    root = (root_name or "").strip()
    if not root:
        return {"campfires": [], "auditors": [], "campers": [], "all": []}
    campfires: List[str] = []
    campers: List[str] = []
    auditors: List[str] = []
    seen: set[str] = set()

    def add_unique(bucket: List[str], name: str) -> None:
        nm = (name or "").strip()
        if not nm or nm in seen:
            return
        seen.add(nm)
        bucket.append(nm)

    add_unique(campfires, root)

    if current_valley:
        add_unique(auditors, f"{root} Auditor" if f"{root} Auditor" in current_valley.campfires else "")

    # Parent map is the strongest signal for live linked campers.
    for child_name, parent_name in list(campfire_parent.items()):
        if (parent_name or "").strip() != root:
            continue
        if current_valley and child_name not in current_valley.campfires:
            continue
        add_unique(campers, child_name)

    # Workflow steps provide a fallback when a linked camper exists but the parent map is stale.
    try:
        wf = current_valley.get_workflow(root) if current_valley and getattr(current_valley, "get_workflow", None) else None
        for step in (wf.get("steps") if isinstance(wf, dict) else []) or []:
            if not isinstance(step, dict):
                continue
            camper_name = (step.get("camper") or "").strip()
            if current_valley and camper_name in current_valley.campfires:
                add_unique(campers, camper_name)
    except Exception:
        pass

    if current_valley:
        for camper_name in list(campers):
            auditor_name = f"{camper_name} Auditor"
            if auditor_name in current_valley.campfires:
                add_unique(auditors, auditor_name)

    return {
        "campfires": campfires,
        "auditors": auditors,
        "campers": campers,
        "all": campfires + auditors + campers,
    }


def _move_beliefs_embeddings(old_name: str, new_name: str) -> None:
    if not old_name or not new_name:
        return
    try:
        collection = _get_beliefs_collection()
        got = collection.get(where={"campfire": old_name}, include=["documents", "metadatas"])
        ids = (got or {}).get("ids") or []
        docs = (got or {}).get("documents") or []
        metas = (got or {}).get("metadatas") or []
        if not ids:
            return
        try:
            collection.delete(ids=ids)
        except Exception:
            pass
        new_docs = [d for d in docs if isinstance(d, str)]
        if not new_docs:
            return
        new_metas = []
        for m in metas:
            mm = m if isinstance(m, dict) else {}
            mm = dict(mm)
            mm["campfire"] = new_name
            new_metas.append(mm)
        while len(new_metas) < len(new_docs):
            new_metas.append({"campfire": new_name})
        emb = _embed_texts(new_docs)
        collection.add(
            ids=[f"{new_name}:{i}:{uuid.uuid4().hex}" for i in range(len(new_docs))],
            documents=new_docs,
            embeddings=emb,
            metadatas=new_metas[: len(new_docs)],
        )
    except Exception:
        return


def _auditor_orchestrator_instruction() -> str:
    return (
        "You are the Campfire Auditor and Orchestrator.\n"
        "If the user asks about current campfire status/settings (workflow/execution order, schedule, tools, model, campers), answer directly in plain text.\n"
        "Only produce a JSON plan if the user explicitly asks to change the team/workflow/schedule, to create a plan, or to set up a campfire/team.\n"
        "Never create or manage auditors as separate campers.\n"
        "If the user asks to set up or create a team for the current campfire, plan campers and workflow for the current campfire unless they explicitly say new, another, or separate campfire/team.\n"
        "Only include campfire_to_create when the user explicitly asks for a new, another, or separate campfire/team.\n"
        "Names like 'Intake Camper' are camper names, not campfire names. Put those in campers_to_create, not campfire_to_create.\n"
        "When producing a JSON plan, return ONLY valid JSON with keys:\n"
        "- campfire_to_create: optional object {name, persona, model, system_prompt} for explicit new campfire/team requests only\n"
        "- campers_to_create: array of {name, persona, model, system_prompt, rag_template}\n"
        "- task_plan: array of {camper, task}\n"
        "- message_to_user: string\n"
        "- run_after_create: optional boolean\n"
        "Do not include any extra text outside the JSON when returning a plan."
    )


def _extract_first_json_object(text: str) -> Optional[dict]:
    if not text or not isinstance(text, str):
        return None
    s = text.strip()
    try:
        parsed = json.loads(s)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        pass
    start = s.find("{")
    end = s.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    candidate = s[start:end + 1]
    try:
        parsed = json.loads(candidate)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None


def _clear_beliefs_for_campfire(campfire_name: str) -> Dict[str, Any]:
    name = (campfire_name or "").strip()
    if not name:
        return {"cleared": False, "reason": "missing_campfire"}
    file_removed = False
    try:
        belief_path = _get_config_dir() / f"camper_{_slugify(name)}_beliefs.yaml"
        if belief_path.exists():
            belief_path.unlink()
            file_removed = True
    except Exception:
        file_removed = False
    try:
        collection = _get_beliefs_collection()
        collection.delete(where={"campfire": name})
    except Exception:
        pass
    return {"cleared": True, "campfire": name, "belief_file_removed": file_removed}


graph_node_context: Dict[str, Dict[str, Any]] = {"campfires": {}, "campers": {}}


def _node_label_from_graph_node(n: Any) -> str:
    if not isinstance(n, dict):
        return ""
    props = n.get("properties") or {}
    for k in ("target", "name", "id"):
        v = props.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    t = n.get("title")
    if isinstance(t, str) and t.strip():
        return t.strip()
    return ""


def _node_center_from_graph_node(n: Any) -> Optional[tuple[float, float]]:
    if not isinstance(n, dict):
        return None
    pos = n.get("pos")
    size = n.get("size")
    if not (isinstance(pos, list) and len(pos) >= 2):
        return None
    x, y = float(pos[0]), float(pos[1])
    w, h = 160.0, 120.0
    if isinstance(size, list) and len(size) >= 2:
        try:
            w, h = float(size[0]), float(size[1])
        except Exception:
            w, h = 160.0, 120.0
    return (x + w / 2.0, y + h / 2.0)


def _refresh_graph_context_from_snapshot(graph: Any) -> None:
    global graph_node_context
    graph_node_context = {"campfires": {}, "campers": {}}
    if not isinstance(graph, dict):
        return
    nodes = graph.get("nodes") or []
    if not isinstance(nodes, list):
        return
    by_id: Dict[str, dict] = {}
    for n in nodes:
        if not isinstance(n, dict):
            continue
        nid = n.get("id")
        if nid is None:
            continue
        by_id[str(nid)] = n
        ntype = (n.get("type") or "").strip()
        label = _node_label_from_graph_node(n)
        center = _node_center_from_graph_node(n)
        if ntype == "campfire/campfire" and label and center:
            graph_node_context["campfires"][label] = {"center": center}
        if ntype == "campfire/camper" and label and center:
            graph_node_context["campers"][label] = {"center": center}
    links = graph.get("links") or []
    inferred: Dict[str, str] = {}
    if isinstance(links, list):
        for lk in links:
            origin_id = None
            target_id = None
            if isinstance(lk, list) and len(lk) >= 5:
                origin_id = lk[1]
                target_id = lk[3]
            elif isinstance(lk, dict):
                origin_id = lk.get("origin_id")
                target_id = lk.get("target_id")
            if origin_id is None or target_id is None:
                continue
            o = by_id.get(str(origin_id))
            t = by_id.get(str(target_id))
            if not o or not t:
                continue
            if (o.get("type") or "") != "campfire/campfire":
                continue
            if (t.get("type") or "") != "campfire/camper":
                continue
            campfire_name = _node_label_from_graph_node(o)
            camper_name = _node_label_from_graph_node(t)
            if campfire_name and camper_name and camper_name != campfire_name:
                inferred[camper_name] = campfire_name
    for camper, parent in inferred.items():
        campfire_parent[camper] = parent


def _default_llm_provider() -> str:
    provider = (os.getenv("LLM_PROVIDER") or "").strip().lower()
    if provider in {"ollama", "openrouter"}:
        return provider
    return "ollama" if not os.getenv("OPENROUTER_API_KEY") else "openrouter"


def _coerce_model(provider: str, model: str) -> str:
    m = (model or "").strip()
    if m:
        return m
    return get_default_ollama_model() if provider == "ollama" else "gpt-4o-mini"


def _pick_provider_and_model(requested_model: Optional[str]) -> tuple[str, str]:
    requested = (requested_model or "").strip()
    if not requested:
        p = _default_llm_provider()
        return p, _coerce_model(p, "")
    lower = requested.lower()
    if ("gpt" in lower or "claude" in lower or "openai" in lower) and os.getenv("OPENROUTER_API_KEY"):
        return "openrouter", requested
    if "gemma" in lower or "llama" in lower or "mistral" in lower:
        return "ollama", requested
    p = _default_llm_provider()
    return p, _coerce_model(p, requested if p == "openrouter" else get_default_ollama_model())


def _parse_add_camper_command(text: str) -> Optional[str]:
    if not text or not isinstance(text, str):
        return None
    t = text.strip()
    low = t.lower()
    if not (
        low.startswith("add camper") or low.startswith("add a camper")
        or low.startswith("create camper") or low.startswith("create a camper")
        or low.startswith("add camera") or low.startswith("add a camera")
        or low.startswith("create camera") or low.startswith("create a camera")
    ):
        return None
    m = re.search(r"(?:named|called)\s+(\"[^\"]+\"|'[^']+'|.+)$", t, re.IGNORECASE)
    if m:
        name = m.group(1).strip().strip("\"'").strip()
        return name if name else None
    m2 = re.search(r"(?:add|create)\s+(?:a\s+)?(?:camper|camera)\s+(\"[^\"]+\"|'[^']+'|.+)$", t, re.IGNORECASE)
    if m2:
        name = m2.group(1).strip().strip("\"'").strip()
        return name if name else None
    m3 = re.match(r"^(?:add|create)\s+(?:a\s+)?(?:camper|camera)\s*:\s*(.+)$", t, re.IGNORECASE)
    if m3:
        name = (m3.group(1) or "").strip().strip("\"'").strip()
        return name if name else None
    return ""


def _looks_like_orchestration_action_request(text: str) -> bool:
    if not text or not isinstance(text, str):
        return False
    low = text.strip().lower()
    if not low:
        return False
    explicit_prefixes = (
        "add camper",
        "add a camper",
        "create camper",
        "create a camper",
        "create a campfire",
        "create campfire",
        "make a campfire",
        "build a campfire",
        "set up a campfire",
        "setup a campfire",
        "camp plan",
        "plan workflow",
        "move ",
        "reorder ",
        "swap ",
        "remove camper",
        "delete campfire",
        "remove campfire",
        "delete team",
        "remove team",
        "rename camper",
        "run rounds",
        "execute rounds",
        "preview rounds",
        "set workflow",
        "clear workflow",
        "set schedule",
        "clear schedule",
    )
    if any(low.startswith(prefix) for prefix in explicit_prefixes):
        return True
    natural_action_patterns = (
        r"^(?:please\s+)?(?:add|added|adding|create|created|creating|make|made|making|build|built|building|set\s*up|setup|configure|configured|configuring)\b.*\b(?:camper|campfire|team)\b",
        r"^(?:please\s+)?(?:plan|planned|planning|set|clear|update|updated|updating)\b.*\b(?:workflow|schedule)\b",
        r"^(?:please\s+)?(?:run|running|execute|executing|preview|previewing)\b.*\brounds\b",
        r"^(?:please\s+)?(?:remove|removed|removing|delete|deleted|deleting|rename|renamed|renaming|move|moved|moving|reorder|reordered|reordering|swap|swapped|swapping)\b.*\b(?:camper|campfire|team|workflow|schedule)\b",
    )
    return any(re.match(pattern, low) for pattern in natural_action_patterns)


def _parse_create_campfire_request(text: str) -> Optional[dict]:
    if not text or not isinstance(text, str):
        return None
    t = text.strip().strip("`").strip()
    if not t:
        return None
    m = re.match(
        r"^(?:please\s+)?(?:create|make|build|set\s*up|setup)\s+(?:me\s+|us\s+)?(?:a|an)?\s*(?:(?P<modifier>new|another|separate)\s+)?(?:campfire|team)\b(?P<rest>.*)$",
        t,
        re.IGNORECASE,
    )
    if not m:
        return None
    explicit_new = bool((m.group("modifier") or "").strip())
    rest = (m.group("rest") or "").strip()
    name = None
    m_name = re.search(
        r"(?:named|called)\s+(\"[^\"]+\"|'[^']+'|.+?)(?=\s+(?:that|to|for|with)\b|[.!?]|$)",
        rest,
        re.IGNORECASE,
    )
    if m_name:
        name = (m_name.group(1) or "").strip().strip("\"'").strip()
    goal = ""
    for marker in ("that can", "to", "for", "which can"):
        mm = re.search(rf"\b{marker}\b\s*(.+)$", rest, re.IGNORECASE)
        if mm:
            goal = (mm.group(1) or "").strip()
            break
    if not goal:
        goal = rest
    if m_name:
        goal = re.sub(
            r"(?:named|called)\s+(\"[^\"]+\"|'[^']+'|.+?)(?=\s+(?:that|to|for|with)\b|[.!?]|$)",
            "",
            goal,
            flags=re.IGNORECASE,
        ).strip()
    goal = goal.strip(" .,:;-")
    return {"name": name or "", "goal": goal or t, "raw": t, "explicit_new": explicit_new}


def _display_name_token(token: str) -> str:
    tok = (token or "").strip()
    if not tok:
        return ""
    if any(ch.isupper() for ch in tok[1:]):
        return tok
    return tok[:1].upper() + tok[1:]


def _derive_campfire_name(seed_text: str) -> str:
    tokens = re.findall(r"[A-Za-z0-9][A-Za-z0-9+/._-]*", seed_text or "")
    skip = {
        "a", "an", "and", "build", "campfire", "can", "create", "for", "help", "make",
        "new", "of", "plan", "problem", "set", "setup", "solve", "team", "that", "the",
        "this", "to", "up", "with", "workflow", "one", "two", "three", "four", "five",
        "six", "seven", "eight", "nine", "ten",
    }
    kept: List[str] = []
    for tok in tokens:
        low = tok.lower()
        if low in skip:
            continue
        if len(tok) < 3 and not any(ch.isdigit() for ch in tok):
            continue
        shown = _display_name_token(tok)
        if shown:
            kept.append(shown)
        if len(kept) >= 3:
            break
    if not kept:
        return "New Campfire"
    return (" ".join(kept) + " Campfire").strip()[:80]


def _looks_like_camper_name(name: str) -> bool:
    t = (name or "").strip().lower()
    if not t:
        return False
    return t == "camper" or t.endswith(" camper")


def _derive_parent_campfire_name_for_camper(camper_name: str) -> str:
    raw = (camper_name or "").strip()
    if not raw:
        return "New Campfire"
    base = re.sub(r"\s+camper\s*$", "", raw, flags=re.IGNORECASE).strip(" -_/")
    if not base:
        base = raw
    if base.lower().endswith(" campfire"):
        return base
    return f"{base} Campfire"


def _build_parent_campfire_config(
    name: str,
    goal_text: str = "",
    persona: str = "",
    model_hint: Optional[str] = None,
    system_prompt: str = "",
) -> CampfireConfig:
    provider, model = _pick_provider_and_model(model_hint)
    prompt = (system_prompt or "").strip()
    if not prompt:
        effective_goal = goal_text.strip() or "coordinate a specialist camper team"
        prompt = (
            f"You are {name}. Coordinate a specialist camper team to solve this goal: {effective_goal}. "
            f"Use the saved workflow when the user asks you to run work, ask clarifying questions when needed, "
            f"and keep final outputs concise and actionable."
        )
    return CampfireConfig(
        name=name,
        type="LLMCampfire",
        config={
            "llm": {
                "provider": provider,
                "base_url": os.getenv("OLLAMA_HOST", "http://host.docker.internal:11434"),
                "model": model,
            },
            "prompts": {"system": prompt},
            "persona": {"name": name, "persona": persona or "team orchestrator", "model": model},
            "rag": {"documents": _default_rag_documents(name, persona or goal_text)},
        },
    )


def _unique_campfire_name(base_name: str) -> str:
    candidate = (base_name or "").strip() or "New Campfire"
    if not current_valley or candidate not in current_valley.campfires:
        return candidate
    idx = 2
    while f"{candidate} {idx}" in current_valley.campfires:
        idx += 1
    return f"{candidate} {idx}"


def _normalize_label(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def _match_camper_label(raw: str, campers: List[str]) -> Optional[str]:
    r = (raw or "").strip()
    if not r:
        return None
    nr = _normalize_label(r)
    if not nr:
        return None
    exact = {c: _normalize_label(c) for c in campers}
    for c, nc in exact.items():
        if nc == nr:
            return c
    for c, nc in exact.items():
        if nr and (nr in nc or nc in nr):
            return c
    return None


def _ordinal_to_index(token: str) -> Optional[int]:
    t = (token or "").strip().lower()
    if not t:
        return None
    if t in {"last", "end", "final", "bottom"}:
        return 1_000_000
    words = {
        "first": 1,
        "second": 2,
        "third": 3,
        "fourth": 4,
        "fifth": 5,
        "sixth": 6,
        "seventh": 7,
        "eighth": 8,
        "ninth": 9,
        "tenth": 10,
    }
    if t in words:
        return words[t] - 1
    m = re.match(r"^(\d+)", t)
    if m:
        try:
            n = int(m.group(1))
            return max(0, n - 1)
        except Exception:
            return None
    return None


def _parse_reorder_steps(text: str, campers: List[str]) -> List[tuple[str, int]]:
    if not text or not isinstance(text, str):
        return []
    t = text.strip()
    parts = re.split(r"\bthen\b", t, flags=re.IGNORECASE)
    moves: List[tuple[str, int]] = []
    for p in parts:
        seg = p.strip().strip(",")
        if not seg:
            continue
        m = re.search(
            r"(?:move|put|place|set)?\s*(.+?)\s+(?:to|as)?\s*(?:the\s+)?((?:\d+)(?:st|nd|rd|th)?|first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|last|end|final|bottom)\s*(?:step|place|position)?\b",
            seg,
            re.IGNORECASE,
        )
        if not m:
            continue
        raw_name = (m.group(1) or "").strip().strip("\"'").strip()
        ord_token = (m.group(2) or "").strip()
        idx = _ordinal_to_index(ord_token)
        if idx is None:
            continue
        match = _match_camper_label(raw_name, campers)
        if not match:
            continue
        moves.append((match, idx))
    return moves
    return ""


def set_valley(valley: Valley):
    """Set the valley instance for visualization"""
    global current_valley, visualizer, dock_enable_state
    current_valley = valley
    visualizer = ValleyVisualizer(valley)
    dock_running = bool(getattr(valley, "dock", None) and getattr(valley.dock, "is_running", None) and valley.dock.is_running())
    dock_enable_state = {
        "status": "enabled" if dock_running else "idle",
        "detail": None,
        "updated_at": datetime.utcnow().isoformat(),
    }
    
@app.get("/", response_class=HTMLResponse)
async def get_main_page():
    """Serve the main visualization interface"""
    html_path = os.path.join(static_path, "index.html")
    try:
        with open(html_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    except FileNotFoundError:
        return HTMLResponse(
            content="<h1>CampfireValley Web Interface</h1><p>Static files not found. Please ensure the web interface is properly installed.</p>",
            status_code=404
        )

@app.get("/metrics")
async def get_metrics():
    """Prometheus metrics endpoint"""
    # Update metrics with current state
    if current_valley and visualizer:
        try:
            # Update campfire metrics
            campfires = current_valley.get_campfires()
            for campfire_id, campfire in campfires.items():
                campfire_type = getattr(campfire, 'type', 'unknown')
                
                # Update torch queue size
                torch_queue = getattr(campfire, 'torch_queue', 0)
                campfire_torch_queue_size.labels(
                    campfire_id=campfire_id, 
                    campfire_type=campfire_type
                ).set(torch_queue)
                
                # Update camper count
                camper_count = getattr(campfire, 'camper_count', 0)
                campfire_camper_count.labels(
                    campfire_id=campfire_id, 
                    campfire_type=campfire_type
                ).set(camper_count)
                
                # Update throughput (mock data for demo)
                throughput = getattr(campfire, 'throughput', 0) or (torch_queue * 2.5)
                campfire_throughput.labels(
                    campfire_id=campfire_id, 
                    campfire_type=campfire_type
                ).set(throughput)
                
                # Update error rate (mock data for demo)
                error_rate = getattr(campfire, 'error_rate', 0) or 0.02
                campfire_error_rate.labels(
                    campfire_id=campfire_id, 
                    campfire_type=campfire_type
                ).set(error_rate)
                
        except Exception as e:
            # Log error but don't fail metrics endpoint
            print(f"Error updating metrics: {e}")
    
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
    
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time communication"""
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            
            if message.get("type") == "get_state":
                # Generate current state from valley
                if visualizer:
                    state = await visualizer.get_current_state()
                    response = WebSocketMessage(
                        type="state_update",
                        data=state.dict()
                    )
                    await manager.send_personal_message(response.json(), websocket)
                else:
                    # Send empty state
                    empty_state = VisualizationState(nodes=[], connections=[])
                    response = WebSocketMessage(
                        type="state_update",
                        data=empty_state.dict()
                    )
                    await manager.send_personal_message(response.json(), websocket)
            
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    
@app.get("/api/valley/status")
async def get_valley_status():
    """Get current valley status"""
    if current_valley:
        return {
            "status": "active" if current_valley._running else "inactive",
            "name": current_valley.name,
            "timestamp": datetime.now().isoformat(),
            "campfires": len(current_valley.campfires),
            "active_connections": len(manager.active_connections)
        }
    else:
        return {
            "status": "no_valley",
            "timestamp": datetime.now().isoformat(),
            "campfires": 0,
            "active_connections": len(manager.active_connections)
        }


@app.get("/api/mcp/status")
async def get_mcp_status():
    if not current_valley:
        raise HTTPException(status_code=404, detail="No valley available")
    broker = getattr(current_valley, "mcp_broker", None)
    connected = bool(broker and getattr(broker, "is_connected", None) and broker.is_connected())
    return {
        "status": "ok",
        "connected": connected,
        "broker": broker.__class__.__name__ if broker else None,
        "connection_string": getattr(current_valley, "mcp_broker_url", None),
    }


@app.get("/api/mcp/stats")
async def get_mcp_stats():
    if not current_valley:
        raise HTTPException(status_code=404, detail="No valley available")
    broker = getattr(current_valley, "mcp_broker", None)
    if not broker or not getattr(broker, "is_connected", None) or not broker.is_connected():
        return {"status": "ok", "connected": False, "stats": None}
    subs = list(getattr(broker, "_subscriptions", {}).keys()) if hasattr(broker, "_subscriptions") else []
    if getattr(broker, "get_message_stats", None):
        return {"status": "ok", "connected": True, "stats": await broker.get_message_stats(), "subscriptions": subs}
    return {"status": "ok", "connected": True, "stats": None, "subscriptions": subs}


@app.get("/api/dock/status")
async def get_dock_status():
    if not current_valley:
        raise HTTPException(status_code=404, detail="No valley available")
    dock = getattr(current_valley, "dock", None)
    if not dock:
        return {"status": "ok", "running": False, "mode": None, "known_valleys": 0}
    return {
        "status": "ok",
        "running": bool(getattr(dock, "is_running", None) and dock.is_running()),
        "mode": getattr(dock, "dock_mode", None).value if getattr(dock, "dock_mode", None) else None,
        "known_valleys": len(getattr(dock, "get_known_valleys")() or {}) if getattr(dock, "get_known_valleys", None) else 0,
        "routing_cache": getattr(dock, "get_routing_cache")() if getattr(dock, "get_routing_cache", None) else {},
    }


@app.get("/api/dock/valleys")
async def get_dock_valleys():
    if not current_valley:
        raise HTTPException(status_code=404, detail="No valley available")
    dock = getattr(current_valley, "dock", None)
    if not dock or not getattr(dock, "get_known_valleys", None):
        return {"status": "ok", "valleys": []}
    known = dock.get_known_valleys() or {}
    valleys = []
    for name, membership in known.items():
        md = getattr(membership, "metadata", None)
        valleys.append({
            "name": name,
            "valley_id": (getattr(md, "get", None) and md.get("valley_id")) or (md.get("valley_id") if isinstance(md, dict) else "") or "",
            "public_address": (getattr(md, "get", None) and md.get("public_address")) or (md.get("public_address") if isinstance(md, dict) else "") or "",
            "trust_level": getattr(membership, "trust_level", None).value if getattr(membership, "trust_level", None) else None,
            "last_seen": getattr(membership, "last_seen", None).isoformat() if getattr(membership, "last_seen", None) else None,
            "capabilities": getattr(membership, "capabilities", None) or [],
            "exposed_campfires": (getattr(md, "get", None) and md.get("exposed_campfires")) or (md.get("exposed_campfires") if isinstance(md, dict) else []) or [],
            "exposed_services": (getattr(md, "get", None) and md.get("exposed_services")) or (md.get("exposed_services") if isinstance(md, dict) else []) or [],
        })
    valleys.sort(key=lambda v: v["name"])
    return {"status": "ok", "valleys": valleys}


@app.post("/api/dock/mode")
async def set_dock_mode(payload: dict = Body(...)):
    if not current_valley:
        raise HTTPException(status_code=404, detail="No valley available")
    mode = (payload.get("mode") or "").strip().lower()
    if mode not in {"private", "partial", "public"}:
        raise HTTPException(status_code=400, detail="Invalid mode")

    current_valley.config.env["dock_mode"] = mode

    broker = getattr(current_valley, "mcp_broker", None)
    if not broker or not getattr(broker, "is_connected", None) or not broker.is_connected():
        return {"status": "ok", "mode": mode, "running": False}

    dock = getattr(current_valley, "dock", None)
    if dock and getattr(dock, "is_running", None) and dock.is_running():
        try:
            await dock.stop_gateway()
        except Exception:
            pass

    from ..dock import Dock
    current_valley.dock = Dock(
        valley=current_valley,
        mcp_broker=broker,
        party_box=getattr(current_valley, "party_box", None),
        federation_manager=getattr(current_valley, "federation_manager", None),
        vali_coordinator=getattr(current_valley, "vali_coordinator", None),
    )
    await current_valley.dock.start_gateway()
    return {"status": "ok", "mode": mode, "running": True}


@app.post("/api/dock/broadcast")
async def broadcast_dock_discovery():
    if not current_valley:
        raise HTTPException(status_code=404, detail="No valley available")
    dock = getattr(current_valley, "dock", None)
    if not dock or not getattr(dock, "is_running", None) or not dock.is_running():
        raise HTTPException(status_code=400, detail="Dock not running")
    await dock.broadcast_discovery()
    return {"status": "ok"}


@app.post("/api/dock/enable")
async def enable_dock(payload: dict = Body(...)):
    if not current_valley:
        raise HTTPException(status_code=404, detail="No valley available")
    redis_url = (payload.get("redis_url") or os.getenv("REDIS_URL") or "redis://redis:6379").strip()
    if not redis_url:
        raise HTTPException(status_code=400, detail="Missing redis_url")
    global dock_enable_task, dock_enable_state

    if getattr(current_valley, "mcp_broker", None) and current_valley.mcp_broker.is_connected() and getattr(current_valley, "dock", None) and current_valley.dock.is_running():
        return {"status": "ok", "enabled": True, "state": dock_enable_state}

    if dock_enable_task and not dock_enable_task.done():
        return {"status": "ok", "enabled": False, "state": dock_enable_state}

    dock_enable_state = {"status": "starting", "detail": None, "updated_at": datetime.utcnow().isoformat()}

    async def _do_enable():
        global dock_enable_state
        try:
            from ..mcp import RedisMCPBroker
            broker = getattr(current_valley, "mcp_broker", None)
            if not broker:
                broker = RedisMCPBroker(redis_url, valley_name=current_valley.name)
                current_valley.mcp_broker = broker
                current_valley.mcp_broker_url = redis_url

            dock_enable_state = {"status": "connecting", "detail": None, "updated_at": datetime.utcnow().isoformat()}
            ok = await asyncio.wait_for(broker.connect(), timeout=4)
            if not ok or not broker.is_connected():
                raise RuntimeError("MCP connect failed")

            try:
                from ..vali import VALICoordinator
                dock_enable_state = {"status": "starting_vali", "detail": None, "updated_at": datetime.utcnow().isoformat()}
                current_valley.vali_coordinator = VALICoordinator(
                    mcp_broker=broker,
                    federation_manager=getattr(current_valley, "federation_manager", None),
                    valley_name=current_valley.name
                )
                await asyncio.wait_for(current_valley.vali_coordinator.start(), timeout=4)
            except Exception:
                current_valley.vali_coordinator = None

            from ..dock import Dock
            dock_enable_state = {"status": "starting_dock", "detail": None, "updated_at": datetime.utcnow().isoformat()}
            current_valley.dock = Dock(
                valley=current_valley,
                mcp_broker=broker,
                party_box=getattr(current_valley, "party_box", None),
                federation_manager=getattr(current_valley, "federation_manager", None),
                vali_coordinator=getattr(current_valley, "vali_coordinator", None)
            )
            await asyncio.wait_for(current_valley.dock.start_gateway(), timeout=4)

            dock_enable_state = {"status": "enabled", "detail": None, "updated_at": datetime.utcnow().isoformat()}
        except Exception as e:
            current_valley.dock = None
            dock_enable_state = {"status": "error", "detail": str(e), "updated_at": datetime.utcnow().isoformat()}

    dock_enable_task = asyncio.create_task(_do_enable())
    return {"status": "ok", "enabled": False, "state": dock_enable_state}


@app.get("/api/dock/enable/status")
async def get_dock_enable_status():
    running = bool(dock_enable_task and not dock_enable_task.done())
    return {"status": "ok", "running": running, "state": dock_enable_state}
    
@app.get("/api/visualization/state")
async def get_visualization_state():
    """Get current visualization state"""
    if visualizer:
        state = await visualizer.get_current_state()
        return state.dict()
    else:
        return VisualizationState(nodes=[], connections=[]).dict()
    
@app.post("/api/campfire/{campfire_id}/action")
async def campfire_action(campfire_id: str, action: Dict):
    """Perform action on a campfire"""
    action_type = action.get("type", "unknown")
    
    # Track the request in metrics
    campfire_requests_total.labels(campfire_id=campfire_id, action=action_type).inc()
    
    if not current_valley:
        raise HTTPException(status_code=404, detail="No valley available")
    
    # Find the campfire
    campfire = current_valley.campfires.get(campfire_id)
    
    if not campfire:
        raise HTTPException(status_code=404, detail=f"Campfire {campfire_id} not found")
    
    # Perform the action
    if action_type == "start":
        await campfire.start()
    elif action_type == "stop":
        await campfire.stop()
    elif action_type == "restart":
        await campfire.stop()
        await campfire.start()
    else:
        raise HTTPException(status_code=400, detail=f"Unknown action: {action_type}")
    
    return {"status": "success", "campfire_id": campfire_id, "action": action}


@app.get("/api/campfires")
async def get_campfires(include_auditors: bool = False):
    """Get list of all campfires"""
    if not current_valley:
        return []
    
    campfires = []
    for campfire_name, cf in current_valley.campfires.items():
        if not include_auditors and str(campfire_name).endswith(" Auditor"):
            continue
        campfires.append({
            "id": campfire_name,
            "type": cf.__class__.__name__,
            "running": getattr(cf, '_running', False),
            "camper_count": len(getattr(cf, 'campers', [])),
            "parent": campfire_parent.get(campfire_name),
        })
    
    return campfires


@app.get("/api/services")
async def list_services(include_auditors: bool = False):
    if not current_valley:
        raise HTTPException(status_code=404, detail="No valley available")
    vid = ""
    try:
        e = current_valley.config.env or {}
        vid = (e.get("valley_id") or "").strip()
    except Exception:
        vid = ""
    if not vid:
        try:
            vid = uuid.uuid4().hex
            current_valley.config.env["valley_id"] = vid
            try:
                ConfigManager.save_valley_config(current_valley.config, current_valley.manifest_path)
            except Exception:
                pass
        except Exception:
            vid = current_valley.name
    visible = []
    try:
        visible = list((current_valley.config.campfires or {}).get("visible") or [])
    except Exception:
        visible = []
    return build_service_catalog(
        current_valley,
        include_auditors=include_auditors,
        parent_lookup=campfire_parent,
        visible_names=visible,
    )


@app.get("/api/campfire/tools")
async def get_campfire_tools(campfire: str):
    if not current_valley:
        raise HTTPException(status_code=404, detail="No valley available")
    name = (campfire or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Missing campfire")
    if name not in campfire_parent and not name.lower().endswith(" camper"):
        raise HTTPException(status_code=400, detail="Tools are configurable per-camper only")
    cf = current_valley.campfires.get(name)
    if not cf:
        raise HTTPException(status_code=404, detail="Campfire not found")
    cfg = getattr(cf, "config", None)
    tools = {}
    if isinstance(cfg, CampfireConfig):
        conf = cfg.config or {}
        tools = (conf.get("tools") or {}).get("zeitgeist") or {}
    elif isinstance(cfg, dict):
        conf = cfg.get("config") or {}
        tools = (conf.get("tools") or {}).get("zeitgeist") or {}
    persisted = {}
    path = _get_config_dir() / f"campfire_{_slugify(name)}.yaml"
    if path.exists():
        try:
            persisted_cfg = ConfigManager.load_campfire_config(str(path))
            persisted = ((persisted_cfg.config or {}).get("tools") or {}).get("zeitgeist") or {}
        except Exception:
            persisted = {}
    return {"status": "ok", "campfire": name, "tools": tools, "persisted": persisted}


def _campfire_zeitgeist_tools(campfire: str) -> Dict[str, Any]:
    if not current_valley:
        raise HTTPException(status_code=404, detail="No valley available")
    name = (campfire or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Missing campfire")
    if name not in campfire_parent and not name.lower().endswith(" camper"):
        raise HTTPException(status_code=400, detail="Tools are configurable per-camper only")
    cf = current_valley.campfires.get(name)
    if not cf:
        raise HTTPException(status_code=404, detail="Campfire not found")
    cfg = getattr(cf, "config", None)
    if isinstance(cfg, CampfireConfig):
        conf = cfg.config or {}
    elif isinstance(cfg, dict):
        conf = cfg.get("config") or {}
    else:
        conf = {}
    tools = (conf.get("tools") or {}).get("zeitgeist") or {}
    if not isinstance(tools, dict):
        tools = {}
    return {"campfire": name, "tools": tools, "cf": cf, "cfg": cfg}


@app.post("/api/campfire/tools")
async def set_campfire_tools(payload: dict = Body(...)):
    if not current_valley:
        raise HTTPException(status_code=404, detail="No valley available")
    campfire = (payload.get("campfire") or "").strip()
    zeitgeist = payload.get("zeitgeist") or {}
    if not campfire:
        raise HTTPException(status_code=400, detail="Missing campfire")
    if campfire not in campfire_parent and not campfire.lower().endswith(" camper"):
        raise HTTPException(status_code=400, detail="Tools are configurable per-camper only")
    cf = current_valley.campfires.get(campfire)
    if not cf:
        raise HTTPException(status_code=404, detail="Campfire not found")
    cfg = getattr(cf, "config", None)
    if isinstance(cfg, CampfireConfig):
        cfg.config = cfg.config or {}
        cfg.config["tools"] = cfg.config.get("tools") or {}
        cfg.config["tools"]["zeitgeist"] = zeitgeist
    elif isinstance(cfg, dict):
        cfg.setdefault("config", {})
        cfg["config"].setdefault("tools", {})
        cfg["config"]["tools"]["zeitgeist"] = zeitgeist
    path = _get_config_dir() / f"campfire_{_slugify(campfire)}.yaml"
    try:
        if isinstance(cfg, CampfireConfig):
            ConfigManager.save_campfire_config(cfg, str(path))
        else:
            conf = CampfireConfig(name=campfire, type=cfg.get("type") or "LLMCampfire", config=cfg.get("config") or {})
            ConfigManager.save_campfire_config(conf, str(path))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to persist tools: {e}")
    return {"status": "ok", "campfire": campfire, "tools": zeitgeist}


@app.get("/api/zeitgeist/plugins")
async def get_zeitgeist_plugins(campfire: str):
    resolved = _campfire_zeitgeist_tools(campfire)
    zeitgeist = resolved["tools"]
    return {
        "status": "ok",
        "campfire": resolved["campfire"],
        "catalog": get_zeitgeist_plugin_catalog(zeitgeist),
        "plugins": {
            "gmail": gmail_plugin_status(zeitgeist),
            "google_docs": google_docs_plugin_status(zeitgeist),
            "google_calendar": google_calendar_plugin_status(zeitgeist),
            "google_drive": google_drive_plugin_status(zeitgeist),
            "google_sheets": google_sheets_plugin_status(zeitgeist),
        },
    }


@app.get("/api/zeitgeist/plugins/google/auth/start")
async def start_google_plugin_auth(campfire: str, request: Request):
    resolved = _campfire_zeitgeist_tools(campfire)
    try:
        flow = create_google_auth_start(str(request.base_url), resolved["tools"], resolved["campfire"])
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {
        "status": "ok",
        "campfire": resolved["campfire"],
        "provider": "google",
        "auth_url": flow.get("auth_url"),
        "state": flow.get("state"),
        "redirect_uri": flow.get("redirect_uri"),
    }


@app.get("/api/zeitgeist/plugins/gmail/auth/start")
async def start_gmail_plugin_auth(campfire: str, request: Request):
    return await start_google_plugin_auth(campfire, request)


@app.get("/api/zeitgeist/plugins/google/auth/callback", response_class=HTMLResponse)
async def finish_google_plugin_auth(code: str, state: str, request: Request):
    try:
        pending = peek_google_auth_state(state)
        campfire_name = str((pending or {}).get("campfire") or "").strip()
        resolved_tools = _campfire_zeitgeist_tools(campfire_name)["tools"] if campfire_name else {}
        result = await finish_google_oauth(code, state, str(request.base_url), resolved_tools)
    except HTTPException:
        raise
    except Exception as e:
        return HTMLResponse(
            content=(
                "<html><body style='font-family: Arial, sans-serif; padding: 24px;'>"
                f"<h2>Google Connection Failed</h2><p>{html.escape(str(e))}</p>"
                "<p>You can return to CampfireValley and try connecting Google again.</p>"
                "</body></html>"
            ),
            status_code=400,
        )
    campfire_name = str((result or {}).get("campfire") or "").strip()
    return HTMLResponse(
        content=(
            "<html><body style='font-family: Arial, sans-serif; padding: 24px;'>"
            "<h2>Google Services Connected</h2>"
            f"<p>Campfire: {html.escape(campfire_name or '(unknown)')}</p>"
            "<p>Gmail, Google Docs, and Google Calendar can now be used through Zeitgeist where enabled.</p>"
            "</body></html>"
        )
    )


@app.get("/api/zeitgeist/plugins/gmail/auth/callback", response_class=HTMLResponse)
async def finish_gmail_plugin_auth(code: str, state: str, request: Request):
    return await finish_google_plugin_auth(code, state, request)


@app.get("/api/ollama/models")
async def list_ollama_models():
    host = os.getenv("OLLAMA_HOST", "http://host.docker.internal:11434").rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(f"{host}/api/tags")
        if r.status_code != 200:
            raise HTTPException(status_code=502, detail=f"Ollama returned {r.status_code}")
        data = r.json()
        models = []
        for m in (data.get("models") or []):
            name = (m.get("name") if isinstance(m, dict) else None) or ""
            name = str(name).strip()
            if name:
                models.append(name)
        models = sorted(set(models))
        return {"status": "ok", "models": models}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to query Ollama: {e}")


@app.get("/api/settings/defaults")
def get_runtime_defaults():
    return {
        "status": "ok",
        "defaults": {
            "ollama_model": get_default_ollama_model(),
        },
    }


async def _party_box_summary() -> Dict[str, Any]:
    pb = getattr(current_valley, "party_box", None) if current_valley else None
    if not pb or not getattr(pb, "list_attachments", None):
        return {"enabled": False, "categories": {}}
    categories = ["incoming", "outgoing", "quarantine", "attachments"]
    out: Dict[str, Any] = {"enabled": True, "categories": {}}
    for c in categories:
        try:
            items = await pb.list_attachments(category=c)
        except Exception:
            items = []
        if not isinstance(items, list):
            items = []
        items = [str(x) for x in items if x is not None]
        out["categories"][c] = {"count": len(items), "items": items[:50]}
    return out


@app.get("/api/campfire/details")
async def get_campfire_details(campfire: str):
    if not current_valley:
        raise HTTPException(status_code=404, detail="No valley available")
    name = (campfire or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Missing campfire")
    cf = current_valley.campfires.get(name)
    if not cf:
        raise HTTPException(status_code=404, detail="Campfire not found")
    cfg = getattr(cf, "config", None)
    cfg_dump = cfg.model_dump(by_alias=True) if isinstance(cfg, CampfireConfig) else (cfg if isinstance(cfg, dict) else None)
    llm = {}
    tools = {}
    dock_cfg = {}
    if isinstance(cfg, CampfireConfig):
        conf = cfg.config or {}
        llm = conf.get("llm") or {}
        tools = (conf.get("tools") or {}).get("zeitgeist") or {}
        dock_cfg = conf.get("dock") or {}
    elif isinstance(cfg, dict):
        conf = cfg.get("config") or {}
        llm = conf.get("llm") or {}
        tools = (conf.get("tools") or {}).get("zeitgeist") or {}
        dock_cfg = conf.get("dock") or {}
    dock_identifier = ""
    if isinstance(dock_cfg, dict):
        dock_identifier = (dock_cfg.get("identifier") or "").strip()
    valley_id = ""
    try:
        e = current_valley.config.env or {}
        valley_id = (e.get("valley_id") or "").strip()
    except Exception:
        valley_id = ""
    if not valley_id:
        try:
            valley_id = uuid.uuid4().hex
            current_valley.config.env["valley_id"] = valley_id
            try:
                ConfigManager.save_valley_config(current_valley.config, current_valley.manifest_path)
            except Exception:
                pass
        except Exception:
            valley_id = current_valley.name
    address_suffix = dock_identifier or re.sub(r"[^a-zA-Z0-9]+", "-", str(name).lower()).strip("-") or str(name)
    workflow = current_valley.get_workflow(name) if getattr(current_valley, "get_workflow", None) else None
    schedule = current_valley.get_schedule(name) if getattr(current_valley, "get_schedule", None) else None
    party_box = await _party_box_summary()
    campers = sorted([c for c, p in campfire_parent.items() if p == name])
    camper_id_map: Dict[str, str] = {}
    for nm in campers:
        try:
            cf2 = current_valley.campfires.get(nm)
            cfg2 = getattr(cf2, "config", None)
            conf2: Dict[str, Any] = {}
            if isinstance(cfg2, CampfireConfig):
                conf2 = cfg2.config or {}
            elif isinstance(cfg2, dict):
                conf2 = cfg2.get("config") if isinstance(cfg2.get("config"), dict) else cfg2
            ident2 = conf2.get("identity") if isinstance(conf2.get("identity"), dict) else {}
            uid2 = (ident2.get("uuid") or "").strip()
            if uid2:
                camper_id_map[nm] = uid2
        except Exception:
            continue
    return {
        "status": "ok",
        "campfire": name,
        "type": cf.__class__.__name__,
        "running": getattr(cf, "_running", False),
        "camper_count": len(getattr(cf, "campers", [])),
        "campers": campers,
        "camper_ids": camper_id_map,
        "llm": llm,
        "tools": tools,
        "dock": {"identifier": dock_identifier, "address": f"valley:{valley_id}/{address_suffix}"},
        "workflow": workflow,
        "schedule": schedule,
        "party_box": party_box,
        "config": cfg_dump,
    }


@app.get("/api/valley/details")
async def get_valley_details():
    if not current_valley:
        raise HTTPException(status_code=404, detail="No valley available")
    all_names = sorted(list(current_valley.campfires.keys()))
    auditor_campfires = [c for c in all_names if str(c).endswith(" Auditor")]
    campers = []
    for n in all_names:
        s = str(n)
        if s in campfire_parent:
            campers.append(s)
            continue
        if s.lower().endswith(" camper"):
            campers.append(s)
            continue
    campers = sorted(set(campers))
    campfires = [c for c in all_names if str(c) not in set(campers) and str(c) not in set(auditor_campfires)]
    vid = ""
    try:
        e = current_valley.config.env or {}
        vid = (e.get("valley_id") or "").strip()
    except Exception:
        vid = ""
    if not vid:
        try:
            vid = uuid.uuid4().hex
            current_valley.config.env["valley_id"] = vid
            try:
                ConfigManager.save_valley_config(current_valley.config, current_valley.manifest_path)
            except Exception:
                pass
        except Exception:
            vid = ""
    status = {
        "name": current_valley.name,
        "identifier": vid,
        "campfire_total": len(campfires),
        "camper_total": len(campers),
        "campfires": campfires,
        "campers": campers,
        "auditor_campfires": auditor_campfires,
    }
    try:
        dock_resp = await get_dock_valleys()
    except Exception:
        dock_resp = {"valleys": []}
    try:
        sched = await list_schedules()
    except Exception:
        sched = {"schedules": []}
    party_box = await _party_box_summary()
    return {"status": "ok", "valley": status, "dock": dock_resp.get("valleys") or [], "schedules": sched.get("schedules") or [], "party_box": party_box}


@app.post("/api/auditors/cleanup")
async def cleanup_legacy_auditor_campfires():
    if not current_valley:
        raise HTTPException(status_code=404, detail="No valley available")
    removed: List[str] = []
    for name in list(current_valley.campfires.keys()):
        if not str(name).endswith(" Auditor"):
            continue
        try:
            await current_valley.deprovision_campfire(name)
            removed.append(str(name))
        except Exception:
            continue
        try:
            campfire_parent.pop(str(name), None)
        except Exception:
            pass
        try:
            _cleanup_campfire_artifacts(str(name))
        except Exception:
            pass
    return {"status": "ok", "removed": removed}


@app.post("/api/campfire/delete")
async def delete_campfire(payload: Dict[str, Any]):
    if not current_valley:
        raise HTTPException(status_code=404, detail="No valley available")
    name = str((payload or {}).get("campfire") or "").strip()
    confirm = bool((payload or {}).get("confirm"))
    if not name:
        raise HTTPException(status_code=400, detail="Missing campfire name")
    summary = _delete_summary_for_campfire(name)
    if not summary["campfires"]:
        raise HTTPException(status_code=404, detail=f"Campfire {name} not found")
    if not confirm:
        return {
            "status": "confirm_required",
            "campfire": name,
            "summary": {
                "campfires": summary["campfires"],
                "auditors": summary["auditors"],
                "campers": summary["campers"],
                "total": len(summary["all"]),
            },
            "message": f"Delete '{name}' and all linked auditors/campers?",
        }

    removed: List[str] = []
    failed: List[str] = []
    target_names = list(summary["all"])
    for target_name in target_names:
        existed_before = bool(current_valley and target_name in current_valley.campfires)
        try:
            if existed_before:
                await current_valley.deprovision_campfire(target_name)
        except Exception:
            pass
        try:
            campfire_parent.pop(target_name, None)
        except Exception:
            pass
        try:
            _cleanup_campfire_artifacts(target_name)
        except Exception:
            pass
        exists_after = bool(current_valley and target_name in current_valley.campfires)
        if existed_before and not exists_after:
            removed.append(target_name)
        elif existed_before and exists_after:
            failed.append(target_name)

    # Reconcile against the actual final runtime state so the response matches reality
    # even if deleting the parent implicitly removed some linked nodes.
    if current_valley:
        removed = [n for n in target_names if n not in current_valley.campfires]
        failed = [n for n in target_names if n in current_valley.campfires]
    if not failed:
        removed = list(target_names)

    msg = (
        f"Deleted campfire '{name}' and related nodes."
        if not failed else
        f"Deleted campfire '{name}' with some cleanup failures."
    )
    return {
        "status": "ok" if not failed else "partial",
        "campfire": name,
        "removed": removed,
        "failed": failed,
        "message": msg,
        "summary": {
            "campfires": summary["campfires"],
            "auditors": summary["auditors"],
            "campers": summary["campers"],
            "total": len(summary["all"]),
        },
    }

@app.get("/api/valley/identifier")
async def get_valley_identifier():
    if not current_valley:
        raise HTTPException(status_code=404, detail="No valley available")
    vid = ""
    try:
        e = current_valley.config.env or {}
        vid = (e.get("valley_id") or "").strip()
    except Exception:
        vid = ""
    generated = False
    if not vid:
        try:
            vid = uuid.uuid4().hex
            current_valley.config.env["valley_id"] = vid
            generated = True
            try:
                ConfigManager.save_valley_config(current_valley.config, current_valley.manifest_path)
            except Exception:
                pass
        except Exception:
            vid = ""
    return {"status": "ok", "valley": current_valley.name, "identifier": vid, "generated": generated}

@app.post("/api/valley/identifier")
async def set_valley_identifier(payload: dict = Body(...)):
    if not current_valley:
        raise HTTPException(status_code=404, detail="No valley available")
    raw = (payload.get("identifier") or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="Missing identifier")
    try:
        _ = uuid.UUID(raw)
    except Exception:
        raise HTTPException(status_code=400, detail="Identifier must be a valid UUID")
    current_valley.config.env["valley_id"] = raw
    try:
        ConfigManager.save_valley_config(current_valley.config, current_valley.manifest_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to persist valley identifier: {e}")
    return {"status": "ok", "valley": current_valley.name, "identifier": raw}


@app.get("/api/campfire/llm")
async def get_campfire_llm(campfire: str):
    if not current_valley:
        raise HTTPException(status_code=404, detail="No valley available")
    name = (campfire or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Missing campfire")
    if name not in campfire_parent and not name.lower().endswith(" camper"):
        raise HTTPException(status_code=400, detail="LLM model is configurable per-camper only")
    cf = current_valley.campfires.get(name)
    if not cf:
        raise HTTPException(status_code=404, detail="Campfire not found")
    cfg = getattr(cf, "config", None)
    if isinstance(cfg, CampfireConfig):
        conf = cfg.config or {}
        llm = conf.get("llm") or {}
    elif isinstance(cfg, dict):
        conf = cfg.get("config") or {}
        llm = conf.get("llm") or {}
    else:
        llm = {}
    provider = (llm.get("provider") or "").strip() or "ollama"
    model = (llm.get("model") or "").strip() or None
    return {"status": "ok", "campfire": name, "provider": provider, "model": model}


@app.post("/api/campfire/llm")
async def set_campfire_llm(payload: dict = Body(...)):
    if not current_valley:
        raise HTTPException(status_code=404, detail="No valley available")
    campfire = (payload.get("campfire") or "").strip()
    provider = (payload.get("provider") or "ollama").strip().lower()
    model = (payload.get("model") or "").strip()
    if not campfire or not model:
        raise HTTPException(status_code=400, detail="Missing campfire or model")
    if campfire not in campfire_parent and not campfire.lower().endswith(" camper"):
        raise HTTPException(status_code=400, detail="LLM model is configurable per-camper only")
    if provider != "ollama":
        raise HTTPException(status_code=400, detail="Only ollama provider is supported in the UI currently")
    cf = current_valley.campfires.get(campfire)
    if not cf:
        raise HTTPException(status_code=404, detail="Campfire not found")
    cfg = getattr(cf, "config", None)
    if isinstance(cfg, CampfireConfig):
        cfg.config = cfg.config or {}
        cfg.config["llm"] = cfg.config.get("llm") or {}
        cfg.config["llm"]["provider"] = provider
        cfg.config["llm"]["model"] = model
        to_save = cfg
    elif isinstance(cfg, dict):
        cfg.setdefault("config", {})
        cfg["config"].setdefault("llm", {})
        cfg["config"]["llm"]["provider"] = provider
        cfg["config"]["llm"]["model"] = model
        to_save = CampfireConfig(name=campfire, type=cfg.get("type") or "LLMCampfire", config=cfg.get("config") or {})
    else:
        raise HTTPException(status_code=400, detail="Campfire config not editable")
    path = _get_config_dir() / f"campfire_{_slugify(campfire)}.yaml"
    try:
        ConfigManager.save_campfire_config(to_save, str(path))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to persist llm config: {e}")
    return {"status": "ok", "campfire": campfire, "provider": provider, "model": model}


@app.get("/api/campfire/identity")
async def get_backend_campfire_identity(campfire: str):
    if not current_valley:
        raise HTTPException(status_code=404, detail="No valley available")
    name = (campfire or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Missing campfire")
    cf = current_valley.campfires.get(name)
    if not cf:
        raise HTTPException(status_code=404, detail="Campfire not found")
    cfg = getattr(cf, "config", None)
    conf: Dict[str, Any] = {}
    if isinstance(cfg, CampfireConfig):
        conf = cfg.config or {}
    elif isinstance(cfg, dict):
        conf = cfg.get("config") if isinstance(cfg.get("config"), dict) else cfg
    ident = conf.get("identity") if isinstance(conf.get("identity"), dict) else {}
    uid = (ident.get("uuid") or "").strip()
    if not uid:
        uid = uuid.uuid4().hex
        try:
            if isinstance(cfg, CampfireConfig):
                cfg.config = cfg.config or {}
                cfg.config["identity"] = {"uuid": uid}
            elif isinstance(cfg, dict):
                conf.setdefault("identity", {})
                conf["identity"]["uuid"] = uid
        except Exception:
            pass
    return {"status": "ok", "campfire": name, "uuid": uid}


@app.get("/api/campfire/identifier")
async def get_campfire_identifier(campfire: str):
    if not current_valley:
        raise HTTPException(status_code=404, detail="No valley available")
    name = (campfire or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Missing campfire")
    cf = current_valley.campfires.get(name)
    if not cf:
        raise HTTPException(status_code=404, detail="Campfire not found")
    cfg = getattr(cf, "config", None)
    conf: Dict[str, Any] = {}
    if isinstance(cfg, CampfireConfig):
        conf = cfg.config or {}
    elif isinstance(cfg, dict):
        conf = cfg.get("config") if isinstance(cfg.get("config"), dict) else cfg
    dock_cfg = conf.get("dock") if isinstance(conf.get("dock"), dict) else {}
    identifier = (dock_cfg.get("identifier") or "").strip() if isinstance(dock_cfg, dict) else ""
    return {
        "status": "ok",
        "campfire": name,
        "identifier": identifier,
        "address": f"valley:{current_valley.name}/{identifier or name}",
    }


@app.post("/api/campfire/identifier")
async def set_campfire_identifier(payload: dict = Body(...)):
    if not current_valley:
        raise HTTPException(status_code=404, detail="No valley available")
    campfire = (payload.get("campfire") or "").strip()
    identifier = (payload.get("identifier") or "").strip()
    if not campfire:
        raise HTTPException(status_code=400, detail="Missing campfire")
    if "/" in identifier or ":" in identifier:
        raise HTTPException(status_code=400, detail="Identifier cannot contain '/' or ':'")
    cf = current_valley.campfires.get(campfire)
    if not cf:
        raise HTTPException(status_code=404, detail="Campfire not found")
    if identifier:
        for other_name, other_cf in (current_valley.campfires or {}).items():
            other_name_s = str(other_name)
            if other_name_s == campfire:
                continue
            if other_name_s == identifier:
                raise HTTPException(status_code=409, detail=f"Identifier conflicts with campfire name '{other_name_s}'")
            other_cfg = getattr(other_cf, "config", None)
            other_conf: Dict[str, Any] = {}
            if isinstance(other_cfg, CampfireConfig):
                other_conf = other_cfg.config or {}
            elif isinstance(other_cfg, dict):
                other_conf = other_cfg.get("config") if isinstance(other_cfg.get("config"), dict) else other_cfg
            other_dock = other_conf.get("dock") if isinstance(other_conf.get("dock"), dict) else {}
            other_ident = (other_dock.get("identifier") or "").strip() if isinstance(other_dock, dict) else ""
            if other_ident and other_ident == identifier:
                raise HTTPException(status_code=409, detail=f"Identifier already in use by '{other_name_s}'")
    cfg = getattr(cf, "config", None)
    if isinstance(cfg, CampfireConfig):
        cfg.config = cfg.config or {}
        dock_cfg = cfg.config.get("dock") if isinstance(cfg.config.get("dock"), dict) else {}
        if identifier:
            dock_cfg["identifier"] = identifier
            cfg.config["dock"] = dock_cfg
        else:
            if isinstance(dock_cfg, dict):
                dock_cfg.pop("identifier", None)
            if dock_cfg:
                cfg.config["dock"] = dock_cfg
            else:
                cfg.config.pop("dock", None)
        to_save = cfg
    elif isinstance(cfg, dict):
        cfg.setdefault("config", {})
        conf = cfg["config"] if isinstance(cfg.get("config"), dict) else {}
        dock_cfg = conf.get("dock") if isinstance(conf.get("dock"), dict) else {}
        if identifier:
            dock_cfg["identifier"] = identifier
            conf["dock"] = dock_cfg
        else:
            if isinstance(dock_cfg, dict):
                dock_cfg.pop("identifier", None)
            if dock_cfg:
                conf["dock"] = dock_cfg
            else:
                conf.pop("dock", None)
        cfg["config"] = conf
        to_save = CampfireConfig(name=campfire, type=cfg.get("type") or "LLMCampfire", config=cfg.get("config") or {})
    else:
        raise HTTPException(status_code=400, detail="Campfire config not editable")
    path = _get_config_dir() / f"campfire_{_slugify(campfire)}.yaml"
    try:
        ConfigManager.save_campfire_config(to_save, str(path))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to persist identifier: {e}")
    return {
        "status": "ok",
        "campfire": campfire,
        "identifier": identifier,
        "address": f"valley:{current_valley.name}/{identifier or campfire}",
    }


def _normalize_round_specs(rounds: List[Any]) -> List[Dict[str, str]]:
    normalized: List[Dict[str, Any]] = []
    if not current_valley:
        return normalized

    local_aliases = {str(current_valley.name)}
    try:
        env = current_valley.config.env or {}
        local_id = (env.get("valley_id") or "").strip()
        if local_id:
            local_aliases.add(local_id)
    except Exception:
        pass

    def _local_round_services() -> List[Dict[str, Any]]:
        visible = []
        try:
            visible = list((current_valley.config.campfires or {}).get("visible") or [])
        except Exception:
            visible = []
        catalog = build_service_catalog(
            current_valley,
            include_auditors=False,
            parent_lookup=campfire_parent,
            visible_names=visible,
        )
        return list(catalog.get("services") or [])

    def _remote_round_services() -> List[Dict[str, Any]]:
        dock = getattr(current_valley, "dock", None)
        if not dock or not getattr(dock, "get_known_valleys", None):
            return []
        known = dock.get_known_valleys() or {}
        services: List[Dict[str, Any]] = []
        for valley_name, membership in known.items():
            md = getattr(membership, "metadata", None)
            data = md if isinstance(md, dict) else {}
            for raw_service in data.get("exposed_services") or []:
                if not isinstance(raw_service, dict):
                    continue
                service = dict(raw_service)
                service["_remote"] = True
                service["_valley_name"] = valley_name
                services.append(service)
        return services

    def _matches_task(service: Dict[str, Any], task_type: str) -> bool:
        wanted = (task_type or "").strip().lower()
        if not wanted:
            return True
        values = []
        values.extend(service.get("task_types") or [])
        accepts = service.get("accepts") if isinstance(service.get("accepts"), dict) else {}
        values.extend(accepts.get("task_types") or [])
        for raw_value in values:
            text = str(raw_value or "").strip().lower()
            if not text:
                continue
            if text == wanted or wanted in text or text in wanted:
                return True
        return False

    def _service_address(service: Dict[str, Any]) -> str:
        addresses = service.get("addresses") if isinstance(service.get("addresses"), dict) else {}
        return str(addresses.get("valley_id") or addresses.get("valley_name") or "").strip()

    def _service_label(service: Dict[str, Any]) -> str:
        name = str(service.get("name") or service.get("service_id") or "service").strip()
        task_bits = [str(v).strip() for v in (service.get("task_types") or []) if str(v).strip()]
        if task_bits:
            return f"{name} [{', '.join(task_bits[:2])}]"
        return name

    def _resolve_explicit_target(target: str, mode: str, instruction: str, idx: int) -> Optional[Dict[str, Any]]:
        raw_target = str(target or "").strip()
        if not raw_target:
            return None
        if raw_target.lower().startswith("valley:"):
            parts = [p.strip() for p in raw_target.split(":", 1)[1].split("/") if p.strip()]
            target_valley = parts[0] if parts else ""
            target_name = parts[1] if len(parts) >= 2 else (parts[0] if parts else raw_target)
            return {
                "campfire": target_name,
                "label": target_name,
                "mode": mode,
                "instruction": instruction,
                "target_address": raw_target,
                "target_valley": target_valley,
                "source": "remote" if target_valley and target_valley not in local_aliases else "local",
            }
        resolved = current_valley._resolve_campfire_by_identifier(raw_target) if getattr(current_valley, "_resolve_campfire_by_identifier", None) else None
        target_name = resolved or raw_target
        if target_name not in current_valley.campfires or _is_auditor_target(target_name):
            return None
        return {
            "campfire": target_name,
            "label": target_name,
            "mode": mode,
            "instruction": instruction,
            "target_address": f"valley:{current_valley.name}/{target_name}",
            "target_valley": current_valley.name,
            "source": "local",
        }

    def _resolve_service_match(service_id: str, task_type: str, mode: str, instruction: str) -> Optional[Dict[str, Any]]:
        sid = str(service_id or "").strip().lower()
        task = str(task_type or "").strip()
        local_services = [s for s in _local_round_services() if bool(s.get("supports_rounds"))]
        remote_services = [s for s in _remote_round_services() if bool(s.get("supports_rounds"))]

        def _matches_service_id(service: Dict[str, Any]) -> bool:
            if not sid:
                return True
            identifiers = [
                service.get("service_id"),
                service.get("identifier"),
                service.get("name"),
            ]
            identifiers.append(_service_address(service))
            for value in identifiers:
                text = str(value or "").strip().lower()
                if text and text == sid:
                    return True
            return False

        candidates: List[Dict[str, Any]] = []
        for service in local_services + remote_services:
            if not _matches_service_id(service):
                continue
            if not _matches_task(service, task):
                continue
            candidates.append(service)
        if not candidates:
            return None
        chosen = candidates[0]
        address = _service_address(chosen)
        if not address:
            return None
        label = _service_label(chosen)
        target_name = str(chosen.get("name") or chosen.get("service_id") or address).strip()
        target_valley = ""
        if address.lower().startswith("valley:"):
            parts = [p.strip() for p in address.split(":", 1)[1].split("/") if p.strip()]
            target_valley = parts[0] if parts else ""
        return {
            "campfire": target_name,
            "label": label,
            "mode": mode,
            "instruction": instruction,
            "target_address": address,
            "target_valley": target_valley,
            "source": "remote" if chosen.get("_remote") and target_valley not in local_aliases else "local",
            "service_id": chosen.get("service_id") or "",
            "task_type": task,
            "service_kind": chosen.get("service_kind") or chosen.get("kind") or "",
            "role_tags": chosen.get("role_tags") or [],
        }

    total = len(rounds or [])
    for idx, raw in enumerate(rounds or []):
        if isinstance(raw, str):
            mode = "final" if idx == total - 1 else "replace"
            instruction = ""
            resolved_spec = _resolve_explicit_target(raw, mode, instruction, idx)
        elif isinstance(raw, dict):
            mode = str(raw.get("mode") or "").strip().lower() or ("final" if idx == total - 1 else "replace")
            instruction = str(raw.get("instruction") or raw.get("task") or raw.get("prompt") or "").strip()
            explicit_target = str(
                raw.get("target_address")
                or raw.get("address")
                or raw.get("target")
                or raw.get("campfire")
                or raw.get("name")
                or ""
            ).strip()
            service_id = str(raw.get("service_id") or "").strip()
            task_type = str(raw.get("task_type") or "").strip()
            resolved_spec = None
            if explicit_target:
                resolved_spec = _resolve_explicit_target(explicit_target, mode, instruction, idx)
            if resolved_spec is None and (service_id or task_type):
                resolved_spec = _resolve_service_match(service_id, task_type, mode, instruction)
            if resolved_spec and service_id and not resolved_spec.get("service_id"):
                resolved_spec["service_id"] = service_id
            if resolved_spec and task_type and not resolved_spec.get("task_type"):
                resolved_spec["task_type"] = task_type
        else:
            continue
        if not resolved_spec:
            continue
        if mode not in {"replace", "augment", "merge", "final"}:
            mode = "replace"
        resolved_spec["mode"] = mode
        resolved_spec["instruction"] = instruction
        normalized.append(resolved_spec)
    if normalized:
        normalized[-1]["mode"] = "final"
    return normalized[:12]


async def _run_round_chain_request(rounds: List[Any], text: str, sender: str = "service", correlation_id: Optional[str] = None):
    if not current_valley:
        raise HTTPException(status_code=404, detail="No valley available")
    goal = (text or "").strip()
    if not goal:
        raise HTTPException(status_code=400, detail="Missing text")
    normalized = _normalize_round_specs(rounds)
    if not normalized:
        raise HTTPException(status_code=400, detail="No valid round services supplied")
    first_target = normalized[0].get("target_address") or normalized[0].get("campfire")
    corr = (correlation_id or "").strip() or f"rounds_{uuid.uuid4().hex}"
    torch = Torch(
        claim="round_chain",
        source_campfire="service",
        channel="service",
        torch_id=f"service_{uuid.uuid4().hex}",
        sender_valley=sender,
        target_address=first_target if str(first_target).lower().startswith("valley:") else f"valley:{current_valley.name}/{first_target}",
        data={"text": goal, "original_text": goal},
        signature="service_placeholder",
        metadata={"correlation_id": corr, "rounds": normalized, "round_index": 0},
    )
    resp = await current_valley.process_torch(torch)
    return getattr(resp, "data", None) if resp is not None else None


@app.post("/api/voice/ingest")
async def voice_ingest(payload: dict = Body(...)):
    if not current_valley:
        raise HTTPException(status_code=404, detail="No valley available")
    text = payload.get("text", "")
    campfire = payload.get("campfire")
    token = payload.get("admin_token")
    role_prompt = payload.get("role_prompt") or ""
    auditor_mode = bool(payload.get("auditor_mode"))
    # Fallback: if text is missing or looks like a placeholder, transcribe audio
    placeholder = (text or "").strip().lower()
    force_stt = (not text) or (placeholder in {"voice sample", "(no content)", "sample"})
    if force_stt:
        audio_b64 = payload.get("audio_base64")
        audio_url = payload.get("audio_url")
        if not audio_b64 and not audio_url:
            raise HTTPException(status_code=400, detail="Missing text or audio input")
        try:
            engine = await get_engine()
            audio_bytes = base64.b64decode(audio_b64) if audio_b64 else None
            text = await engine.transcribe(audio_bytes=audio_bytes, audio_url=audio_url)
            if not text:
                raise HTTPException(status_code=502, detail="STT returned empty transcript")
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"STT error: {e}")
    admin = is_admin(token)
    intent = parse_intent(text)
    target = campfire or intent.get("campfire")
    content = intent.get("content") or text
    if not target:
        raise HTTPException(status_code=400, detail="Missing campfire target")
    _append_log(target or "Unknown", "user", content)
    if isinstance(target, str) and target.startswith("valley:"):
        dock = getattr(current_valley, "dock", None)
        broker = getattr(current_valley, "mcp_broker", None)
        if not dock or not getattr(dock, "is_running", None) or not dock.is_running():
            raise HTTPException(status_code=400, detail="Dock not running")
        if not broker or not getattr(broker, "is_connected", None) or not broker.is_connected():
            raise HTTPException(status_code=400, detail="MCP broker not connected")

        reply_channel = f"reply:{current_valley.name}:{uuid.uuid4().hex}"
        future = asyncio.get_running_loop().create_future()

        async def _reply_cb(_channel: str, msg: dict):
            if not future.done():
                future.set_result(msg)

        await broker.subscribe(reply_channel, _reply_cb)
        try:
            torch_dict = make_voice_torch(current_valley.name, target, content, admin)
            torch_dict["metadata"] = {"reply_channel": reply_channel}
            torch = Torch(**torch_dict)
            ok = await dock.send_torch(target, torch)
            if not ok:
                raise HTTPException(status_code=502, detail="Failed to send torch to remote valley")
            try:
                msg = await asyncio.wait_for(future, timeout=20)
            except asyncio.TimeoutError:
                raise HTTPException(status_code=504, detail="Timed out waiting for remote response")
        finally:
            try:
                await broker.unsubscribe(reply_channel)
            except Exception:
                pass

        response_text = None
        if isinstance(msg, dict):
            response_text = msg.get("llm_response") or msg.get("text")
        if response_text:
            _append_log(target, "assistant", str(response_text))
        return {"status": "ok", "campfire": target, "response": msg}
    if auditor_mode or _is_auditor_target(target):
        parent = str(target) if auditor_mode else (campfire_parent.get(target) or _parent_from_auditor_name(target))
        cmd = (content or "").strip()
        if cmd.startswith("`"):
            cmd = cmd.strip("`").strip()
        low = cmd.lower()
        create_campfire_request = _parse_create_campfire_request(cmd)
        delete_campfire_request = _parse_delete_campfire_command(cmd)
        run_rounds_request = _parse_run_rounds_command(cmd)
        allow_actions = _looks_like_orchestration_action_request(cmd) or (
            create_campfire_request is not None
        ) or (delete_campfire_request is not None) or (run_rounds_request is not None)
        if delete_campfire_request is not None:
            target_campfire = str(delete_campfire_request.get("name") or "").strip()
            if not target_campfire:
                target_campfire = str(parent or "").strip()
            if not target_campfire:
                msg = "Which campfire should I delete?"
                _append_log(target, "assistant", msg)
                return {"status": "ok", "campfire": target, "response": {"text": msg}}
            summary = _delete_summary_for_campfire(target_campfire)
            if not summary["campfires"]:
                msg = f"Campfire '{target_campfire}' not found."
                _append_log(target, "assistant", msg)
                return {"status": "ok", "campfire": target, "response": {"text": msg, "ok": False}}
            if not bool(delete_campfire_request.get("confirm")):
                msg = (
                    f"Delete campfire '{target_campfire}'?\n"
                    f"Campfires: {', '.join(summary['campfires']) or '(none)'}\n"
                    f"Auditors: {', '.join(summary['auditors']) or '(none)'}\n"
                    f"Campers: {', '.join(summary['campers']) or '(none)'}\n"
                    f"Total nodes to delete: {len(summary['all'])}"
                )
                _append_log(target, "assistant", msg)
                return {
                    "status": "ok",
                    "campfire": target,
                    "response": {
                        "text": msg,
                        "options": [target_campfire],
                        "options_action": "delete_campfire_confirm",
                        "ok": True,
                    },
                }
            delete_result = await delete_campfire({"campfire": target_campfire, "confirm": True})
            removed_items = delete_result.get("removed") or []
            failed_items = delete_result.get("failed") or []
            msg = str(delete_result.get("message") or f"Deleted campfire '{target_campfire}'.")
            final_payload = {
                "text": msg,
                "ok": delete_result.get("status") == "ok",
                "removed": removed_items,
                "failed": failed_items,
                "summary": delete_result.get("summary"),
            }
            _append_log(target, "assistant", msg)
            return {"status": "ok", "campfire": target, "response": final_payload}
        if run_rounds_request is not None:
            requested_rounds = run_rounds_request.get("rounds") or []
            round_task = str(run_rounds_request.get("task") or "").strip()
            preview_only = bool(run_rounds_request.get("preview"))
            if not requested_rounds or not round_task:
                available = [str(s.get("name") or s.get("service_id") or "") for s in (build_service_catalog(current_valley, include_auditors=False, parent_lookup=campfire_parent, visible_names=list((current_valley.config.campfires or {}).get("visible") or [])).get("services") or [])]
                msg = (
                    "Use `run rounds Campfire A -> Campfire B -> Campfire C: your task`.\n"
                    "Or call the API with `service_id` and `task_type` fields in each round.\n"
                    "Use `preview rounds ...` to inspect the chain without running it.\n"
                    "Available local services: "
                    + (", ".join(available) if available else "(none)")
                )
                _append_log(target, "assistant", msg)
                return {"status": "ok", "campfire": target, "response": {"text": msg, "ok": False, "available": available}}
            normalized_rounds = _normalize_round_specs(requested_rounds)
            if not normalized_rounds:
                available = [str(s.get("name") or s.get("service_id") or "") for s in (build_service_catalog(current_valley, include_auditors=False, parent_lookup=campfire_parent, visible_names=list((current_valley.config.campfires or {}).get("visible") or [])).get("services") or [])]
                msg = (
                    "No valid round services were found in that rounds chain.\n"
                    "Available local services: "
                    + (", ".join(available) if available else "(none)")
                )
                _append_log(target, "assistant", msg)
                return {"status": "ok", "campfire": target, "response": {"text": msg, "ok": False, "available": available}}
            round_lines = [f"{i+1}. {r.get('label') or r.get('campfire') or r.get('service_id') or r.get('target_address')} ({r.get('mode')})" for i, r in enumerate(normalized_rounds)]
            plan_text = "Rounds chain:\n" + "\n".join(round_lines) + f"\n\nTask:\n{round_task}"
            corr = f"rounds_{uuid.uuid4().hex}"
            if preview_only:
                msg = plan_text + f"\n\nCorrelation: {corr}"
                _append_log(target, "assistant", msg)
                return {
                    "status": "ok",
                    "campfire": target,
                    "response": {"text": msg, "ok": True, "correlation_id": corr, "rounds": normalized_rounds},
                }
            final_data = await _run_round_chain_request(normalized_rounds, round_task, sender=current_valley.name, correlation_id=corr)
            final_text = ""
            if isinstance(final_data, dict):
                final_text = (final_data.get("text") or final_data.get("llm_response") or "").strip()
            msg = plan_text + f"\n\nCorrelation: {corr}\n\n---\n\nFinal response:\n" + (final_text or "(no response)")
            _append_log(target, "assistant", msg)
            return {
                "status": "ok",
                "campfire": target,
                "response": {"text": msg, "ok": bool(final_text), "correlation_id": corr, "rounds": normalized_rounds, "final": final_data},
            }
        if parent and (low.startswith("camp plan") or low.startswith("plan workflow")):
            plan_only = low.startswith("camp plan only") or low.startswith("plan workflow only")
            goal = cmd
            for prefix in ("camp plan only", "camp plan", "plan workflow only", "plan workflow"):
                if low.startswith(prefix):
                    goal = cmd[len(prefix):].strip()
                    break
            goal = goal.strip(" :,-")
            if not goal:
                goal = cmd

            wf = current_valley.get_workflow(parent) if getattr(current_valley, "get_workflow", None) else None
            campers = [c for c in _campers_for_parent(parent) if c and c != parent]
            if not campers and isinstance(wf, dict) and isinstance(wf.get("steps"), list):
                for s in wf.get("steps") or []:
                    if not isinstance(s, dict):
                        continue
                    nm = (s.get("camper") or "").strip()
                    if nm and nm != parent and nm not in campers:
                        campers.append(nm)
            if not campers:
                msg = f"No campers linked to '{parent}'. Add campers first, then try again."
                _append_log(target, "assistant", msg)
                return {"status": "ok", "campfire": target, "response": {"text": msg, "ok": False}}

            known = set(campers)
            corr = f"plan_{uuid.uuid4().hex}"

            def _extract_plan_items(raw: str) -> List[dict]:
                if not raw or not isinstance(raw, str):
                    return []
                m = re.search(r"```json\\s*([\\s\\S]+?)```", raw, flags=re.IGNORECASE)
                candidate = (m.group(1).strip() if m else raw.strip())
                dec = json.JSONDecoder()
                for i, ch in enumerate(candidate):
                    if ch not in "[{":
                        continue
                    try:
                        obj, _ = dec.raw_decode(candidate[i:])
                        if isinstance(obj, list):
                            return [x for x in obj if isinstance(x, dict)]
                        if isinstance(obj, dict) and isinstance(obj.get("steps"), list):
                            return [x for x in obj.get("steps") if isinstance(x, dict)]
                    except Exception:
                        continue
                return []

            proposals: List[Dict[str, Any]] = []
            for idx, camper in enumerate(campers[:12], start=1):
                cf = current_valley.campfires.get(camper)
                if not cf:
                    continue
                prompt = (
                    f"You are {camper}.\n\n"
                    f"Goal:\n{goal}\n\n"
                    f"Available campers:\n- " + "\n- ".join(campers) + "\n\n"
                    f"Task:\nPropose 1-3 workflow steps to achieve the goal. Each step must be assigned to one of the available campers.\n\n"
                    f"Return ONLY JSON (no markdown, no commentary) as a list of objects. Schema:\n"
                    f"[{{\"camper\": \"<one of available campers>\", \"task\": \"<imperative instruction>\"}}]\n"
                )
                step_torch = Torch(
                    claim="workflow_step",
                    source_campfire=f"{parent} Auditor",
                    channel="planning",
                    torch_id=f"plan_{uuid.uuid4().hex}",
                    sender_valley=current_valley.name,
                    target_address=f"valley:{current_valley.name}/{camper}",
                    data={"text": prompt, "service_mode": True, "parent": parent, "step": idx, "planning": True},
                    signature="plan_placeholder",
                    metadata={"correlation_id": corr, "parent": parent, "step": idx, "camper": camper, "planning": True},
                )
                resp = await cf.process_torch(step_torch)
                raw = ""
                if resp is not None and hasattr(resp, "data") and isinstance(resp.data, dict):
                    raw = (resp.data.get("llm_response") or resp.data.get("text") or "").strip()
                items = _extract_plan_items(raw)
                proposals.append({"camper": camper, "raw": raw, "items": items})

            planned_steps: List[Dict[str, str]] = []
            seen = set()
            for p in proposals:
                default_camper = (p.get("camper") or "").strip()
                items = p.get("items") if isinstance(p.get("items"), list) else []
                for it in items:
                    if not isinstance(it, dict):
                        continue
                    c = (it.get("camper") or default_camper or "").strip()
                    t = (it.get("task") or it.get("text") or it.get("step") or "").strip()
                    if not c or c not in known:
                        c = default_camper
                    if not c or not t:
                        continue
                    k = (c.lower(), t.lower())
                    if k in seen:
                        continue
                    seen.add(k)
                    planned_steps.append({"camper": c, "task": t})
                    if len(planned_steps) >= 20:
                        break
                if len(planned_steps) >= 20:
                    break

            if not planned_steps:
                planned_steps = [{"camper": c, "task": "Provide your role-specific analysis and recommendations."} for c in campers[:5]]

            if "Editor / Reporter Camper" in known:
                rest = [s for s in planned_steps if (s.get("camper") or "").strip() != "Editor / Reporter Camper"]
                planned_steps = rest + [{"camper": "Editor / Reporter Camper", "task": "Synthesize prior outputs into the final client-facing report, including a 'Role Contributions' section with quotes."}]

            plan_lines = [f"{i+1}. {s.get('camper')}: {s.get('task')}" for i, s in enumerate(planned_steps)]
            plan_text = "Planned steps:\n" + ("\n".join(plan_lines) if plan_lines else "(none)")

            if plan_only:
                msg = plan_text + f"\n\nCorrelation: {corr}"
                _append_log(target, "assistant", msg)
                return {"status": "ok", "campfire": target, "response": {"text": msg, "ok": True, "correlation_id": corr, "steps": planned_steps}}

            run_torch = Torch(
                claim="service_request",
                source_campfire=f"{parent} Auditor",
                channel="service",
                torch_id=f"service_{uuid.uuid4().hex}",
                sender_valley=current_valley.name,
                target_address=f"valley:{current_valley.name}/{parent}",
                data={"text": goal},
                signature="service_placeholder",
                metadata={"correlation_id": corr, "workflow_override_steps": planned_steps, "planned": True},
            )
            final_resp = await current_valley.process_torch(run_torch)
            final_text = ""
            if final_resp is not None and hasattr(final_resp, "data") and isinstance(final_resp.data, dict):
                final_text = (final_resp.data.get("text") or final_resp.data.get("llm_response") or "").strip()
            msg = plan_text + f"\n\nCorrelation: {corr}\n\n---\n\nFinal report:\n" + (final_text or "(no response)")
            _append_log(target, "assistant", msg)
            return {"status": "ok", "campfire": target, "response": {"text": msg, "ok": bool(final_text), "correlation_id": corr, "steps": planned_steps, "final": getattr(final_resp, "data", None)}}
        if parent and ("move " in low or "reorder" in low or "swap" in low):
            wf = current_valley.get_workflow(parent) if getattr(current_valley, "get_workflow", None) else None
            campers = [c for c in _campers_for_parent(parent) if c and c != parent]
            if not campers and isinstance(wf, dict) and isinstance(wf.get("steps"), list):
                for s in wf.get("steps") or []:
                    if not isinstance(s, dict):
                        continue
                    nm = (s.get("camper") or "").strip()
                    if nm and nm != parent and nm not in campers:
                        campers.append(nm)
            moves = _parse_reorder_steps(cmd, campers)
            if moves:
                task_by_camper: Dict[str, str] = {}
                if isinstance(wf, dict) and isinstance(wf.get("steps"), list):
                    for s in wf.get("steps") or []:
                        if not isinstance(s, dict):
                            continue
                        nm = (s.get("camper") or "").strip()
                        tk = (s.get("task") or "").strip()
                        if nm and tk:
                            task_by_camper[nm] = tk

                def _angle_for(camper_name: str) -> float:
                    cctx = graph_node_context.get("campers", {}).get(camper_name, {})
                    pctx = graph_node_context.get("campfires", {}).get(parent, {})
                    cc = cctx.get("center")
                    pc = pctx.get("center")
                    if not (isinstance(cc, (list, tuple)) and len(cc) == 2 and isinstance(pc, (list, tuple)) and len(pc) == 2):
                        return 0.0
                    dx = float(cc[0]) - float(pc[0])
                    dy = float(cc[1]) - float(pc[1])
                    a = math.atan2(dy, dx)
                    a = a + (math.pi / 2.0)
                    if a < 0:
                        a += 2.0 * math.pi
                    return a

                base_order = []
                if isinstance(wf, dict) and isinstance(wf.get("steps"), list):
                    for s in wf.get("steps") or []:
                        if isinstance(s, dict):
                            nm = (s.get("camper") or "").strip()
                            if nm and nm in campers:
                                base_order.append(nm)
                for c in campers:
                    if c not in base_order:
                        base_order.append(c)

                if not base_order:
                    base_order = sorted(campers, key=_angle_for) if campers else []
                
                for name, idx in moves:
                    if name in base_order:
                        base_order.remove(name)
                    idx = max(0, min(idx, len(base_order)))
                    base_order.insert(idx, name)
                steps = [{"camper": n, "task": task_by_camper.get(n) or "Execute"} for n in base_order]
                ok = current_valley.set_workflow(parent, steps) if getattr(current_valley, "set_workflow", None) else False
                msg = "Workflow updated." if ok else "Failed to update workflow."
                if ok:
                    msg += "\n\nNew execution order:\n" + "\n".join([f"{i+1}. {n}" for i, n in enumerate(base_order)])
                _append_log(target, "assistant", msg)
                return {"status": "ok", "campfire": target, "response": {"text": msg, "ok": ok, "workflow": current_valley.get_workflow(parent) if getattr(current_valley, "get_workflow", None) else None}}
        if parent and low.startswith("show workflow"):
            wf = None
            if getattr(current_valley, "get_workflow", None):
                wf = current_valley.get_workflow(parent)
            steps = []
            if isinstance(wf, dict) and isinstance(wf.get("steps"), list):
                steps = wf.get("steps")
            if not steps:
                msg = f"No workflow set for '{parent}'."
            else:
                msg = f"Workflow for '{parent}': " + " -> ".join([str(s.get("camper")) for s in steps if isinstance(s, dict) and s.get("camper")])
            _append_log(target, "assistant", msg)
            return {"status": "ok", "campfire": target, "response": {"text": msg, "workflow": wf}}
        if parent and ("execution order" in low or "run order" in low or ("workflow" in low and not any(x in low for x in ("show workflow", "set workflow", "clear workflow")))):
            wf = None
            if getattr(current_valley, "get_workflow", None):
                wf = current_valley.get_workflow(parent)
            campers = [c for c in _campers_for_parent(parent) if c and c != parent]
            wf_campers = []
            if isinstance(wf, dict) and isinstance(wf.get("steps"), list):
                for s in wf.get("steps") or []:
                    if isinstance(s, dict) and s.get("camper"):
                        wf_campers.append(str(s.get("camper")))
            wf_is_valid = bool(wf_campers) and all(c in campers for c in wf_campers)

            if wf_is_valid:
                steps = []
                for i, s in enumerate(wf.get("steps") or [], start=1):
                    if isinstance(s, dict):
                        nm = s.get("camper") or s.get("name") or s.get("id") or ""
                        st = s.get("task") or s.get("instruction") or s.get("action") or ""
                        steps.append(f"{i}. {nm}: {st}".strip())
                    else:
                        steps.append(f"{i}. {s}")
                msg = "Execution order (workflow):\n" + ("\n".join(steps) if steps else "(empty)")
            else:
                def _angle_for(camper_name: str) -> float:
                    cctx = graph_node_context.get("campers", {}).get(camper_name, {})
                    pctx = graph_node_context.get("campfires", {}).get(parent, {})
                    cc = cctx.get("center")
                    pc = pctx.get("center")
                    if not (isinstance(cc, (list, tuple)) and len(cc) == 2 and isinstance(pc, (list, tuple)) and len(pc) == 2):
                        return 0.0
                    dx = float(cc[0]) - float(pc[0])
                    dy = float(cc[1]) - float(pc[1])
                    a = math.atan2(dy, dx)
                    a = a + (math.pi / 2.0)
                    if a < 0:
                        a += 2.0 * math.pi
                    return a
                ordered = sorted(campers, key=_angle_for) if campers else []
                msg = "Execution order (visual):\n" + ("\n".join([f"{i+1}. {n}" for i, n in enumerate(ordered)]) if ordered else "(no campers linked)")
            _append_log(target, "assistant", msg)
            return {"status": "ok", "campfire": target, "response": {"text": msg, "workflow": wf, "campers": campers}}
        if parent and any(k in low for k in ("self diagnostic", "self-diagnostic", "diagnostic", "health check", "audit logs", "self audit", "self-audit")):
            try:
                campers = [c for c in _campers_for_parent(parent) if c and c != parent]
                wf = current_valley.get_workflow(parent) if getattr(current_valley, "get_workflow", None) else None
                wf_campers = []
                if isinstance(wf, dict) and isinstance(wf.get("steps"), list):
                    seen = set()
                    for s in wf.get("steps") or []:
                        if isinstance(s, dict) and s.get("camper"):
                            nm = str(s.get("camper")).strip()
                            if not nm:
                                continue
                            if campers and nm not in campers:
                                continue
                            if nm in seen:
                                continue
                            seen.add(nm)
                            wf_campers.append(nm)
                def _angle_for(camper_name: str) -> float:
                    cctx = graph_node_context.get("campers", {}).get(camper_name, {})
                    pctx = graph_node_context.get("campfires", {}).get(parent, {})
                    cc = cctx.get("center")
                    pc = pctx.get("center")
                    if not (isinstance(cc, (list, tuple)) and len(cc) == 2 and isinstance(pc, (list, tuple)) and len(pc) == 2):
                        return 0.0
                    dx = float(cc[0]) - float(pc[0])
                    dy = float(cc[1]) - float(pc[1])
                    a = math.atan2(dy, dx)
                    a = a + (math.pi / 2.0)
                    if a < 0:
                        a += 2.0 * math.pi
                    return a
                expected = wf_campers if wf_campers else sorted(campers, key=_angle_for)
                now = datetime.utcnow()
                window = now - timedelta(minutes=30)
                monitoring = get_monitoring_system()
                try:
                    if getattr(monitoring, "log_handler", None) is None:
                        await monitoring.initialize()
                except Exception:
                    pass
                mon_logs = []
                try:
                    if getattr(monitoring, "log_handler", None):
                        mon_logs = await monitoring.log_handler.get_logs(limit=2000)
                except Exception:
                    mon_logs = []
                # Determine correlation id: explicit "cid:XXXX" in command or latest seen for expected campers
                cid = None
                m = re.search(r"\bcid:([A-Za-z0-9_\-:]+)", cmd)
                explicit_cid = False
                if m:
                    cid = m.group(1)
                    explicit_cid = True
                if not cid and mon_logs:
                    try:
                        # Find most recent correlation id that appears for any expected camper
                        for le in reversed(mon_logs):
                            corr = getattr(le, "correlation_id", None)
                            src = getattr(le, "source", None)
                            ts = getattr(le, "timestamp", None)
                            if not corr or not src or not isinstance(ts, datetime):
                                continue
                            if ts < window:
                                continue
                            if src.startswith("campfire.") and src[9:] in expected:
                                cid = corr
                                break
                    except Exception:
                        cid = None
                details = []
                seen_map: Dict[str, Optional[datetime]] = {}
                errs = 0
                for nm in expected:
                    recent = []
                    if mon_logs:
                        try:
                            source = f"campfire.{nm}"
                            for le in mon_logs:
                                try:
                                    if getattr(le, "source", None) != source:
                                        continue
                                    if cid and getattr(le, "correlation_id", None) != cid:
                                        continue
                                    lts = getattr(le, "timestamp", None)
                                    if not isinstance(lts, datetime):
                                        continue
                                    if not explicit_cid and lts < window:
                                        continue
                                    recent.append((lts, {"role": le.level.name.lower(), "text": le.message, "level": le.level}))
                                except Exception:
                                    continue
                            recent.sort(key=lambda x: x[0])
                        except Exception:
                            pass
                    last_ts = recent[-1][0].isoformat() if recent else ""
                    first_ts = recent[0][0].isoformat() if recent else ""
                    last_role = recent[-1][1].get("role") if recent else ""
                    last_text = recent[-1][1].get("text") if recent else ""
                    has_error = False
                    last_error_text = ""
                    try:
                        for tsv, e in reversed(recent):
                            lvl = e.get("level")
                            if lvl in {LogLevel.ERROR, LogLevel.CRITICAL}:
                                has_error = True
                                last_error_text = (e.get("text") or "").strip()
                                break
                    except Exception:
                        has_error = False
                    if has_error:
                        errs += 1
                    seen_map[nm] = recent[0][0] if recent else None
                    preview = (last_error_text or last_text or "").strip()
                    if len(preview) > 160:
                        preview = preview[:160] + "…"
                    status = "OK" if recent and not has_error else ("ERROR" if has_error else "MISSING")
                    details.append(f"- {status} | {nm} | first={first_ts or '-'} | last={last_ts or '-'} | last_role={last_role or '-'} | last='{preview}'")
                order_ok = True
                last_time = None
                for nm in expected:
                    tsv = seen_map.get(nm)
                    if tsv is None:
                        order_ok = False
                        break
                    if last_time and tsv < last_time:
                        order_ok = False
                        break
                    last_time = tsv
                total = len(expected)
                seen_count = sum(1 for nm in expected if seen_map.get(nm) is not None)
                completed = False
                try:
                    if cid and mon_logs:
                        wsrc = f"workflow.{parent}"
                        completed = any(
                            getattr(le, "source", None) == wsrc
                            and getattr(le, "correlation_id", None) == cid
                            and isinstance(getattr(le, "timestamp", None), datetime)
                            and (explicit_cid or getattr(le, "timestamp", None) >= window)
                            and isinstance(getattr(le, "message", None), str)
                            and "Workflow completed for" in getattr(le, "message", "")
                            for le in mon_logs
                        )
                except Exception:
                    completed = False
                in_progress = bool(cid) and (not completed) and (seen_count > 0) and (seen_count < total)
                strict_ok = True
                try:
                    if completed and cid and mon_logs:
                        wsrc = f"workflow.{parent}"
                        for le in reversed(mon_logs):
                            if getattr(le, "source", None) != wsrc:
                                continue
                            if getattr(le, "correlation_id", None) != cid:
                                continue
                            ctx = getattr(le, "context", None)
                            if isinstance(ctx, dict):
                                st = ctx.get("steps_total")
                                so = ctx.get("steps_ok")
                                if isinstance(st, int) and isinstance(so, int):
                                    strict_ok = (st == so)
                            break
                except Exception:
                    strict_ok = True
                result_word = "PASS" if (order_ok and errs == 0 and (total == 0 or seen_count == total) and completed and strict_ok) else ("IN_PROGRESS" if in_progress else "FAIL")
                head = f"Self-audit: {result_word}\nCampfire: {parent}\nTime window: last 30m\nExpected order: " + (" -> ".join(expected) if expected else "(none)")
                verdict = f"Summary: order_ok={order_ok} | errors={errs} | seen={seen_count}/{total} | completed={completed} | strict_ok={strict_ok}"
                reason = ""
                if seen_count == 0:
                    wf_has_steps = bool(wf_campers)
                    if not wf_has_steps:
                        reason = "\nReason: no saved workflow found for this campfire. Visual order is shown, but steps won’t execute until a workflow is set."
                    else:
                        reason = "\nReason: workflow exists, but no camper activity was found in the selected time window."
                if in_progress:
                    reason = "\nReason: workflow execution is still in progress. Run 'self audit' again after the Discord reply is posted."
                actions = ""
                if seen_count == 0:
                    wf_has_steps = bool(wf_campers)
                    if not wf_has_steps:
                        actions = "\nNext steps:\n- Ask: 'show workflow' to confirm whether one exists\n- If none, say: 'set workflow {\"steps\": [ {\"camper\": \"Intake Camper\", \"task\": \"Execute\"}, ... ]}'\n- Or say natural commands like: 'reorder Intake Camper first, Editor / Reporter Camper second'\n- Then send a test request (Discord/file upload), and retry: 'self audit'"
                    else:
                        actions = "\nNext steps:\n- Send a new test request (Discord/file upload) to this campfire\n- Then run: 'self audit'\n- If you want to audit a specific run, use: 'self audit cid:<correlation_id>'"
                if in_progress:
                    actions = "\nNext steps:\n- Wait for the Discord response to finish\n- Then run: 'self audit cid:" + str(cid) + "'"
                body = "\n".join(details) if details else "(no recent activity)"
                suffix = f"\nCorrelation: {cid}" if cid else ""
                msg = head + "\n" + verdict + reason + actions + suffix + "\n" + body
                _append_log(target, "assistant", msg)
                return {"status": "ok", "campfire": target, "response": {"text": msg, "order_ok": order_ok, "errors": errs, "expected": expected, "correlation_id": cid}}
            except Exception as e:
                msg = f"Self-diagnostic failed: {e}"
                _append_log(target, "assistant", msg)
                return {"status": "ok", "campfire": target, "response": {"text": msg, "order_ok": False, "errors": 1, "expected": []}}
        if parent and low.startswith("clear workflow"):
            ok = False
            if getattr(current_valley, "clear_workflow", None):
                ok = current_valley.clear_workflow(parent)
            msg = f"Cleared workflow for '{parent}'." if ok else f"Failed to clear workflow for '{parent}'."
            _append_log(target, "assistant", msg)
            return {"status": "ok", "campfire": target, "response": {"text": msg, "ok": ok}}
        if parent and low.startswith("set workflow"):
            rest = cmd[len("set workflow"):].strip()
            parsed = None
            if rest:
                try:
                    parsed = json.loads(rest)
                except Exception:
                    parsed = None
            steps = []
            if isinstance(parsed, list):
                steps = parsed
            elif isinstance(parsed, dict) and isinstance(parsed.get("steps"), list):
                steps = parsed.get("steps")
            elif not parsed and rest:
                try:
                    import ast
                    evaluated = ast.literal_eval(rest)
                    if isinstance(evaluated, list):
                        steps = evaluated
                    elif isinstance(evaluated, dict) and isinstance(evaluated.get("steps"), list):
                        steps = evaluated.get("steps")
                except Exception:
                    pass
            ok = False
            if getattr(current_valley, "set_workflow", None):
                ok = current_valley.set_workflow(parent, steps)
            wf = current_valley.get_workflow(parent) if ok and getattr(current_valley, "get_workflow", None) else None
            msg = f"Workflow updated for '{parent}'." if ok else f"Failed to update workflow for '{parent}'. Note: The JSON payload must be properly formatted."
            _append_log(target, "assistant", msg)
            return {"status": "ok", "campfire": target, "response": {"text": msg, "ok": ok, "workflow": wf}}

        if parent and low.startswith("show schedule"):
            schedule = current_valley.get_schedule(parent) if getattr(current_valley, "get_schedule", None) else None
            msg = f"Schedule for '{parent}': disabled."
            if isinstance(schedule, dict) and schedule.get("enabled"):
                msg = f"Schedule for '{parent}': every {schedule.get('interval_seconds')}s."
            _append_log(target, "assistant", msg)
            return {"status": "ok", "campfire": target, "response": {"text": msg, "schedule": schedule}}
        if parent and low.startswith("clear schedule"):
            ok = current_valley.clear_schedule(parent) if getattr(current_valley, "clear_schedule", None) else False
            msg = f"Cleared schedule for '{parent}'." if ok else f"Failed to clear schedule for '{parent}'."
            _append_log(target, "assistant", msg)
            return {"status": "ok", "campfire": target, "response": {"text": msg, "ok": ok}}
        if parent and low.startswith("set schedule"):
            parsed = _parse_set_schedule_command(cmd) or {}
            interval = parsed.get("interval_seconds")
            if not interval:
                msg = "Usage: set schedule <seconds|minutes> [optional input text]"
                _append_log(target, "assistant", msg)
                return {"status": "ok", "campfire": target, "response": {"text": msg}}
            ok = current_valley.set_schedule(parent, interval, parsed.get("input")) if getattr(current_valley, "set_schedule", None) else False
            schedule = current_valley.get_schedule(parent) if ok and getattr(current_valley, "get_schedule", None) else None
            msg = f"Schedule enabled for '{parent}' every {interval}s." if ok else f"Failed to set schedule for '{parent}'."
            _append_log(target, "assistant", msg)
            return {"status": "ok", "campfire": target, "response": {"text": msg, "ok": ok, "schedule": schedule}}

        if parent and (("process" in low) or any(k in low for k in ("settings", "environment", "config", "configuration", "tools", "zeitgeist", "web search", "image ocr", "ocr", "llm", "model"))):
            effective = parent if parent in current_valley.campfires else None
            if not effective:
                non_auditors = [c for c in current_valley.campfires.keys() if not str(c).endswith(" Auditor")]
                effective = non_auditors[0] if non_auditors else None
            cf = current_valley.campfires.get(effective) if effective else None
            llm = {}
            tools = {}
            if cf and getattr(cf, "config", None):
                cfg = cf.config
                if isinstance(cfg, CampfireConfig):
                    conf = cfg.config or {}
                elif isinstance(cfg, dict):
                    conf = cfg.get("config") or {}
                else:
                    conf = {}
                llm = conf.get("llm") or {}
                tools = (conf.get("tools") or {}).get("zeitgeist") or {}
            campers = [c for c in _campers_for_parent(parent) if c and c != parent]
            wf = current_valley.get_workflow(parent) if getattr(current_valley, "get_workflow", None) else None
            sched = current_valley.get_schedule(parent) if getattr(current_valley, "get_schedule", None) else None
            if isinstance(wf, dict) and isinstance(wf.get("steps"), list):
                filtered_steps = []
                for s in wf.get("steps") or []:
                    if not isinstance(s, dict):
                        continue
                    nm = s.get("camper")
                    if nm and str(nm) in campers:
                        filtered_steps.append(s)
                wf = dict(wf)
                wf["steps"] = filtered_steps
            plugin_names = []
            plugins_block = tools.get("plugins") if isinstance(tools.get("plugins"), dict) else {}
            for plugin_name, plugin_cfg in plugins_block.items():
                if isinstance(plugin_cfg, dict) and plugin_cfg.get("enabled"):
                    plugin_names.append(str(plugin_name))
            msg = (
                f"Campfire: {parent}\n"
                f"LLM: {(llm.get('provider') or 'ollama')} / {(llm.get('model') or '(default)')}\n"
                f"Zeitgeist: enabled={bool(tools.get('enabled'))}, web_search={bool(tools.get('web_search'))}, image_ocr={bool(tools.get('image_ocr'))}\n"
                f"Zeitgeist Plugins: " + (", ".join(plugin_names) if plugin_names else "(none)") + "\n"
                f"Campers ({len(campers)}): " + (", ".join(campers) if campers else "(none)") + "\n"
                f"Workflow: " + (json.dumps(wf, indent=2) if wf else "(none)") + "\n"
                f"Schedule: " + (json.dumps(sched, indent=2) if sched else "(none)")
            )
            _append_log(target, "assistant", msg)
            return {"status": "ok", "campfire": target, "response": {"text": msg}}

        requested_rename = _parse_rename_camper_command(content)
        if requested_rename is not None and parent:
            options = _campers_for_parent(parent)
            old_name = (requested_rename.get("old") or "").strip()
            new_name = (requested_rename.get("new") or "").strip()
            if not old_name:
                msg = f"Which camper should I rename in '{parent}'?"
                _append_log(target, "assistant", msg)
                return {"status": "ok", "campfire": target, "response": {"text": msg, "options": options, "options_action": "rename"}}
            if old_name not in options:
                msg = f"Camper '{old_name}' not found for '{parent}'."
                _append_log(target, "assistant", msg)
                return {"status": "ok", "campfire": target, "response": {"text": msg, "options": options, "options_action": "rename"}}
            if not new_name:
                msg = f"What should '{old_name}' be renamed to?"
                _append_log(target, "assistant", msg)
                return {"status": "ok", "campfire": target, "response": {"text": msg, "rename_from": old_name}}
            if new_name in current_valley.campfires:
                msg = f"Name '{new_name}' already exists. Pick a different name."
                _append_log(target, "assistant", msg)
                return {"status": "ok", "campfire": target, "response": {"text": msg, "rename_from": old_name}}

            old_cf = current_valley.campfires.get(old_name)
            old_cfg = getattr(old_cf, "config", None)
            new_cfg = None
            if isinstance(old_cfg, CampfireConfig):
                new_cfg = CampfireConfig(
                    name=new_name,
                    type=old_cfg.type,
                    config=copy.deepcopy(old_cfg.config) if isinstance(old_cfg.config, dict) else (old_cfg.config or {}),
                )
            else:
                new_cfg = CampfireConfig(
                    name=new_name,
                    type="LLMCampfire",
                    config={
                        "llm": {"provider": "ollama", "base_url": os.getenv("OLLAMA_HOST", "http://host.docker.internal:11434"), "model": get_default_ollama_model()},
                        "prompts": {"system": _software_campfire_system_prompt(new_name, "generic")},
                        "persona": {"name": new_name, "persona": "generic", "model": get_default_ollama_model()},
                        "rag": {"documents": _default_rag_documents(new_name, "generic")},
                    },
                )
            ok = await current_valley.provision_campfire(new_cfg)
            if not ok:
                msg = f"Failed to rename '{old_name}' to '{new_name}'."
                _append_log(target, "assistant", msg)
                return {"status": "ok", "campfire": target, "response": {"text": msg}}

            _rename_campfire_artifacts(old_name, new_name)
            _move_beliefs_embeddings(old_name, new_name)

            if old_name in campfire_parent:
                campfire_parent[new_name] = campfire_parent.pop(old_name)

            wf = current_valley.get_workflow(parent) if getattr(current_valley, "get_workflow", None) else None
            if isinstance(wf, dict) and isinstance(wf.get("steps"), list) and getattr(current_valley, "set_workflow", None):
                updated_steps = []
                for s in wf.get("steps") or []:
                    if not isinstance(s, dict):
                        continue
                    camper = s.get("camper")
                    if camper == old_name:
                        ss = dict(s)
                        ss["camper"] = new_name
                        updated_steps.append(ss)
                    else:
                        updated_steps.append(s)
                current_valley.set_workflow(parent, updated_steps)

            try:
                await current_valley.deprovision_campfire(old_name)
            except Exception:
                pass

            msg = f"Renamed camper '{old_name}' to '{new_name}'."
            _append_log(target, "assistant", msg)
            return {"status": "ok", "campfire": target, "response": {"text": msg, "created": [new_name], "removed": [old_name], "renamed": {"from": old_name, "to": new_name}, "parent": parent}}

        requested_remove = _parse_remove_camper_command(content)
        if requested_remove is not None and parent:
            name = requested_remove.strip() if isinstance(requested_remove, str) else ""
            options = _campers_for_parent(parent)
            if not name:
                msg = f"Which camper should I remove from '{parent}'?"
                _append_log(target, "assistant", msg)
                return {"status": "ok", "campfire": target, "response": {"text": msg, "options": options, "options_action": "remove"}}
            if name not in options:
                msg = f"Camper '{name}' not found for '{parent}'."
                _append_log(target, "assistant", msg)
                return {"status": "ok", "campfire": target, "response": {"text": msg, "options": options, "options_action": "remove"}}

            removed = []
            try:
                await current_valley.deprovision_campfire(name)
                removed.append(name)
            except Exception:
                pass

            try:
                campfire_parent.pop(name, None)
            except Exception:
                pass

            _cleanup_campfire_artifacts(name)

            msg = f"Removed camper '{name}' from '{parent}'."
            _append_log(target, "assistant", msg)
            return {"status": "ok", "campfire": target, "response": {"text": msg, "removed": [name], "parent": parent}}

        requested_name = _parse_add_camper_command(content)
        if requested_name is not None:
            name = requested_name.strip() if isinstance(requested_name, str) else ""
            if not name:
                name = f"Camper-{datetime.utcnow().strftime('%H%M%S')}"
            camper_parent = (parent or "").strip()
            created_parent = None
            if not camper_parent:
                camper_parent = _unique_campfire_name(_derive_parent_campfire_name_for_camper(name))
                parent_cfg = _build_parent_campfire_config(
                    camper_parent,
                    goal_text=f"coordinate work for {name}",
                )
                ok_parent = await current_valley.provision_campfire(parent_cfg)
                if not ok_parent:
                    msg = f"Failed to create campfire '{camper_parent}' for camper '{name}'."
                    _append_log(target, "assistant", msg)
                    return {"status": "ok", "campfire": target, "response": {"text": msg, "ok": False}}
                created_parent = camper_parent
            if name in current_valley.campfires:
                existing_parent = campfire_parent.get(name)
                if existing_parent == camper_parent:
                    msg = f"Camper '{name}' already exists in '{camper_parent}'."
                    _append_log(target, "assistant", msg)
                    return {"status": "ok", "campfire": target, "response": {"text": msg, "parent": camper_parent}}
                name = _unique_campfire_name(f"{camper_parent} {name}")
            provider, model = _pick_provider_and_model(None)
            base_url = os.getenv("OLLAMA_HOST", "http://host.docker.internal:11434")
            cfg = CampfireConfig(
                name=name,
                type="LLMCampfire",
                config={
                    "llm": {"provider": provider, "base_url": base_url, "model": model},
                    "prompts": {"system": _software_campfire_system_prompt(name, "generic")},
                    "persona": {"name": name, "persona": "generic", "model": model},
                    "rag": {"documents": _default_rag_documents(name, "generic")},
                },
            )
            ok = await current_valley.provision_campfire(cfg)
            if ok and camper_parent:
                campfire_parent[name] = camper_parent
            msg = f"Created camper '{name}'. Select it to configure via chat/voice."
            if ok and created_parent:
                msg = f"Created campfire '{created_parent}' with camper '{name}'. Select the camper to configure via chat/voice."
            if not ok:
                msg = f"Failed to create camper '{name}'."
            _append_log(target, "assistant", msg)
            return {
                "status": "ok",
                "campfire": target,
                "response": {
                    "text": msg,
                    "created": [name] if ok else [],
                    "created_campfire": created_parent,
                    "parent": camper_parent or parent,
                },
            }

        effective = parent if parent in current_valley.campfires else None
        if not effective:
            non_auditors = [c for c in current_valley.campfires.keys() if not str(c).endswith(" Auditor")]
            effective = non_auditors[0] if non_auditors else None
        if not effective:
            return {"status": "ok", "campfire": target, "response": {"text": "No campfire available."}}

        auditor_system = ""
        if isinstance(role_prompt, str) and role_prompt.strip():
            auditor_system = role_prompt.strip() + "\n\n"
        auditor_system = auditor_system + _auditor_orchestrator_instruction()

        torch_dict = make_voice_torch(current_valley.name, effective, str(content).strip(), admin)
        if isinstance(torch_dict.get("data"), dict):
            torch_dict["data"]["system_prompt_override"] = auditor_system
            torch_dict["data"]["auditor_target"] = target
        torch = Torch(**torch_dict)
        resp = await current_valley.process_torch(torch)
        response = resp.data if resp and hasattr(resp, "data") else None
        result = {"status": "ok", "campfire": target, "response": response}
        response_text = None
        if isinstance(response, dict):
            response_text = response.get("llm_response") or response.get("text")
        elif isinstance(response, str):
            response_text = response
        plan = _extract_first_json_object(str(response_text or ""))
        if response_text and (not plan or (auditor_mode and not allow_actions)):
            _append_log(target, "assistant", str(response_text))

        if auditor_mode and not allow_actions:
            return result
        if not plan:
            return result

        plan_parent = parent
        explicit_new_campfire = bool(
            isinstance(create_campfire_request, dict) and create_campfire_request.get("explicit_new")
        )
        creating_new_campfire = explicit_new_campfire or (parent is None and isinstance(plan.get("campfire_to_create"), dict))
        configuring_current_campfire = bool(create_campfire_request is not None) and not creating_new_campfire and bool(parent)
        create_spec = plan.get("campfire_to_create") if isinstance(plan.get("campfire_to_create"), dict) else {}
        campers_to_create = plan.get("campers_to_create") or []
        task_plan = plan.get("task_plan") or []
        message_to_user = plan.get("message_to_user") or ""
        created_parent = None
        created = []
        results = []
        camper_name_map: Dict[str, str] = {}

        if creating_new_campfire:
            requested_name = ""
            if isinstance(create_spec, dict):
                requested_name = str(create_spec.get("name") or "").strip()
            if not requested_name and isinstance(create_campfire_request, dict):
                requested_name = str(create_campfire_request.get("name") or "").strip()
            goal_text = ""
            if isinstance(create_campfire_request, dict):
                goal_text = str(create_campfire_request.get("goal") or "").strip()
            if not goal_text:
                goal_text = str(message_to_user or cmd).strip()
            requested_name_is_camper = _looks_like_camper_name(requested_name)
            if not requested_name_is_camper and isinstance(campers_to_create, list):
                for raw in campers_to_create[:8]:
                    if not isinstance(raw, dict):
                        continue
                    camper_candidate = str(raw.get("name") or "").strip()
                    if camper_candidate and _normalize_label(camper_candidate) == _normalize_label(requested_name):
                        requested_name_is_camper = True
                        break
            if requested_name_is_camper:
                base_name = _derive_parent_campfire_name_for_camper(requested_name)
            else:
                base_name = requested_name or _derive_campfire_name(goal_text)
            plan_parent = _unique_campfire_name(base_name)
            persona = str(create_spec.get("persona") or "").strip() if isinstance(create_spec, dict) else ""
            sys_prompt = ""
            if isinstance(create_spec, dict):
                sys_prompt = str(create_spec.get("system_prompt") or "").strip()
            parent_cfg = _build_parent_campfire_config(
                plan_parent,
                goal_text=goal_text,
                persona=persona,
                model_hint=create_spec.get("model") if isinstance(create_spec, dict) else None,
                system_prompt=sys_prompt,
            )
            ok = await current_valley.provision_campfire(parent_cfg)
            if not ok:
                msg = f"Failed to create campfire '{plan_parent}'."
                _append_log(target, "assistant", msg)
                return {"status": "ok", "campfire": target, "response": {"text": msg, "ok": False}}
            created_parent = plan_parent

        if isinstance(campers_to_create, list):
            for raw in campers_to_create[:8]:
                if not isinstance(raw, dict):
                    continue
                original_name = (raw.get("name") or "").strip()
                if not original_name:
                    continue
                name = original_name
                low_name = name.lower()
                if low_name == "auditor" or low_name.endswith(" auditor"):
                    continue
                if name in current_valley.campfires:
                    existing_parent = campfire_parent.get(name)
                    if existing_parent == plan_parent:
                        camper_name_map[original_name] = name
                        continue
                    if not plan_parent:
                        camper_name_map[original_name] = name
                        continue
                    name = _unique_campfire_name(f"{plan_parent or parent or 'Campfire'} {original_name}")
                camper_name_map[original_name] = name
                persona = raw.get("persona")
                provider, model = _pick_provider_and_model(raw.get("model"))
                sys_prompt = (raw.get("system_prompt") or _software_campfire_system_prompt(name, str(persona) if persona else None)).strip()
                rag_template = raw.get("rag_template")
                rag_docs = [str(rag_template).strip()] if isinstance(rag_template, str) and rag_template.strip() else _default_rag_documents(name, str(persona) if persona else None)
                cfg = CampfireConfig(
                    name=name,
                    type="LLMCampfire",
                    config={
                        "llm": {"provider": provider, "base_url": os.getenv("OLLAMA_HOST", "http://host.docker.internal:11434"), "model": model},
                        "prompts": {"system": sys_prompt},
                        "persona": {"name": name, "persona": persona, "model": model},
                        "rag": {"documents": rag_docs},
                    },
                )
                ok = await current_valley.provision_campfire(cfg)
                if ok:
                    created.append(name)
                    if plan_parent:
                        campfire_parent[name] = plan_parent

        workflow_steps = []
        if isinstance(task_plan, list):
            for raw in task_plan[:12]:
                if not isinstance(raw, dict):
                    continue
                camper = (raw.get("camper") or "").strip()
                task = (raw.get("task") or "").strip()
                if camper in camper_name_map:
                    camper = camper_name_map[camper]
                if not camper or not task:
                    continue
                if camper not in current_valley.campfires:
                    continue
                workflow_steps.append({"camper": camper, "task": task})

        if creating_new_campfire:
            workflow_saved = False
            if workflow_steps and getattr(current_valley, "set_workflow", None):
                workflow_saved = current_valley.set_workflow(plan_parent, workflow_steps)
            created_camper_names = created if created else sorted(_campers_for_parent(plan_parent))
            msg = (
                f"Created campfire '{plan_parent}'.\n"
                f"Campers: " + (", ".join(created_camper_names) if created_camper_names else "(none)") + "\n"
                f"Workflow saved: {'yes' if workflow_saved else 'no'}.\n"
                f"The team is ready, but no work has been started yet."
            )
            final_payload = {
                "text": msg,
                "ok": True,
                "created_campfire": plan_parent,
                "created": created,
                "workflow": current_valley.get_workflow(plan_parent) if getattr(current_valley, "get_workflow", None) else None,
                "plan": plan,
                "parent": plan_parent,
                "message_to_user": message_to_user,
            }
            _append_log(target, "assistant", str(final_payload.get("text")))
            return {"status": "ok", "campfire": target, "response": final_payload}

        if configuring_current_campfire:
            workflow_saved = False
            if workflow_steps and getattr(current_valley, "set_workflow", None):
                workflow_saved = current_valley.set_workflow(plan_parent, workflow_steps)
            current_names = sorted(_campers_for_parent(plan_parent))
            msg = (
                f"Updated campfire '{plan_parent}'.\n"
                f"Campers: " + (", ".join(current_names) if current_names else "(none)") + "\n"
                f"Workflow saved: {'yes' if workflow_saved else 'no'}.\n"
                f"The team is ready, but no work has been started yet."
            )
            final_payload = {
                "text": msg,
                "ok": True,
                "created": created,
                "workflow": current_valley.get_workflow(plan_parent) if getattr(current_valley, "get_workflow", None) else None,
                "plan": plan,
                "parent": plan_parent,
                "message_to_user": message_to_user,
            }
            _append_log(target, "assistant", str(final_payload.get("text")))
            return {"status": "ok", "campfire": target, "response": final_payload}

        if workflow_steps:
            for raw in workflow_steps:
                camper = (raw.get("camper") or "").strip()
                task = (raw.get("task") or "").strip()
                _append_log(camper, "user", task)
                try:
                    r = await asyncio.wait_for(current_valley.send_voice_text(camper, task, admin=False), timeout=60)
                except Exception as e:
                    results.append({"camper": camper, "ok": False, "error": str(e)})
                    continue
                resp = (r or {}).get("response")
                out = None
                if isinstance(resp, dict):
                    out = resp.get("llm_response") or resp.get("text")
                elif isinstance(resp, str):
                    out = resp
                if out:
                    _append_log(camper, "assistant", str(out))
                results.append({"camper": camper, "ok": True, "response": resp})

        final_payload = {"text": message_to_user or "Orchestration plan prepared.", "created": created, "results": results, "plan": plan, "parent": plan_parent, "created_campfire": created_parent}
        _append_log(target, "assistant", str(final_payload.get("text")))
        return {"status": "ok", "campfire": target, "response": final_payload}
    try:
        result = await current_valley.send_voice_text(target, content, admin)
    except ValueError as e:
        if target not in current_valley.campfires:
            cfg = {
                "llm": {
                    "provider": "ollama",
                    "base_url": os.getenv("OLLAMA_HOST", "http://host.docker.internal:11434"),
                    "model": get_default_ollama_model(),
                },
                "prompts": {"system": _software_campfire_system_prompt(str(target), "concise, helpful")},
                "persona": {"name": target, "provider": "ollama", "model": get_default_ollama_model()},
                "rag": {"documents": _default_rag_documents(str(target), "concise, helpful")},
            }
            ok = await current_valley.provision_campfire(CampfireConfig(name=target, type="LLMCampfire", config=cfg))
            if ok:
                result = await current_valley.send_voice_text(target, content, admin)
            else:
                raise HTTPException(status_code=502, detail=f"Failed to provision campfire '{target}'")
        else:
            raise HTTPException(status_code=500, detail=str(e))
    response = (result or {}).get("response")
    response_text = None
    if isinstance(response, dict):
        response_text = response.get("llm_response") or response.get("text")
    elif isinstance(response, str):
        response_text = response
    if response_text:
        _append_log(target or "Unknown", "assistant", str(response_text))
    return result


@app.get("/api/rounds/plans")
async def list_rounds_plans():
    if not current_valley:
        raise HTTPException(status_code=404, detail="No valley available")
    return {"status": "ok", "plans": _list_rounds_plans()}


@app.get("/api/rounds/plans/{plan_name}")
async def get_rounds_plan(plan_name: str):
    if not current_valley:
        raise HTTPException(status_code=404, detail="No valley available")
    plan = _load_rounds_plan(plan_name)
    return {"status": "ok", "plan": plan}


@app.post("/api/rounds/plans")
async def save_rounds_plan(payload: dict = Body(...)):
    if not current_valley:
        raise HTTPException(status_code=404, detail="No valley available")
    name = str(payload.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Missing plan name")
    rounds = payload.get("rounds") or []
    if not isinstance(rounds, list) or not rounds:
        raise HTTPException(status_code=400, detail="Missing rounds")
    normalized_rounds = _normalize_round_specs(rounds)
    if not normalized_rounds:
        raise HTTPException(status_code=400, detail="No valid round services supplied")
    existing = None
    path = _rounds_plan_path(name)
    if path.exists():
        try:
            existing = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception:
            existing = None
    now = datetime.utcnow().isoformat()
    plan = {
        "name": name,
        "description": str(payload.get("description") or "").strip(),
        "campfire": str(payload.get("campfire") or "").strip(),
        "task": str(payload.get("task") or "").strip(),
        "rounds": normalized_rounds,
        "updated_at": now,
        "created_at": str((existing or {}).get("created_at") or now),
    }
    try:
        path.write_text(yaml.safe_dump(plan, sort_keys=False), encoding="utf-8")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save rounds plan: {e}")
    return {"status": "ok", "plan": plan}


@app.delete("/api/rounds/plans/{plan_name}")
async def delete_rounds_plan(plan_name: str):
    if not current_valley:
        raise HTTPException(status_code=404, detail="No valley available")
    path = _rounds_plan_path(plan_name)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Rounds plan not found")
    try:
        path.unlink()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete rounds plan: {e}")
    return {"status": "ok", "deleted": plan_name}


@app.post("/api/rounds/plans/run")
async def run_saved_rounds_plan(payload: dict = Body(...)):
    if not current_valley:
        raise HTTPException(status_code=404, detail="No valley available")
    plan_name = str(payload.get("name") or "").strip()
    if not plan_name:
        raise HTTPException(status_code=400, detail="Missing plan name")
    plan = _load_rounds_plan(plan_name)
    text = str(payload.get("text") or plan.get("task") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Missing text")
    preview = bool(payload.get("preview"))
    sender = (payload.get("sender_valley") or current_valley.name or "service").strip()
    corr = (payload.get("correlation_id") or "").strip() or f"rounds_{uuid.uuid4().hex}"
    rounds = _normalize_round_specs(plan.get("rounds") or [])
    if not rounds:
        raise HTTPException(status_code=400, detail="Saved rounds plan has no valid services")
    if preview:
        return {"status": "ok", "correlation_id": corr, "plan": plan, "rounds": rounds}
    data = await _run_round_chain_request(rounds, text, sender=sender, correlation_id=corr)
    return {"status": "ok", "correlation_id": corr, "plan": plan, "rounds": rounds, "response": data}


@app.get("/api/rounds/catalog")
async def get_rounds_catalog():
    if not current_valley:
        raise HTTPException(status_code=404, detail="No valley available")
    visible = []
    try:
        visible = list((current_valley.config.campfires or {}).get("visible") or [])
    except Exception:
        visible = []
    local_catalog = build_service_catalog(
        current_valley,
        include_auditors=False,
        parent_lookup=campfire_parent,
        visible_names=visible,
    )
    local_services = [s for s in (local_catalog.get("services") or []) if bool(s.get("supports_rounds"))]
    remote_services: List[Dict[str, Any]] = []
    dock = getattr(current_valley, "dock", None)
    if dock and getattr(dock, "get_known_valleys", None):
        known = dock.get_known_valleys() or {}
        for valley_name, membership in known.items():
            md = getattr(membership, "metadata", None)
            data = md if isinstance(md, dict) else {}
            for raw_service in data.get("exposed_services") or []:
                if not isinstance(raw_service, dict):
                    continue
                svc = dict(raw_service)
                svc["_remote"] = True
                svc["_valley_name"] = valley_name
                remote_services.append(svc)
    return {
        "status": "ok",
        "local": local_services,
        "remote": remote_services,
        "dock": {
            "running": bool(dock and getattr(dock, "is_running", None) and dock.is_running()),
            "known_valleys": len((dock.get_known_valleys() or {}) if dock and getattr(dock, "get_known_valleys", None) else {}),
        },
    }


@app.get("/api/watch/runs/{watch_id}/report", response_class=HTMLResponse)
async def get_watch_run_report(watch_id: str):
    if not current_valley:
        raise HTTPException(status_code=404, detail="No valley available")
    if not getattr(current_valley, "render_watch_report_html", None):
        raise HTTPException(status_code=404, detail="Watch reporting not available")
    html_doc = current_valley.render_watch_report_html(watch_id)
    if not html_doc:
        raise HTTPException(status_code=404, detail="Watch run not found")
    return HTMLResponse(content=html_doc)


@app.post("/api/rounds/run")
async def run_rounds(payload: dict = Body(...)):
    if not current_valley:
        raise HTTPException(status_code=404, detail="No valley available")
    rounds = payload.get("rounds") or []
    text = (payload.get("text") or "").strip()
    preview = bool(payload.get("preview"))
    sender = (payload.get("sender_valley") or "service").strip() or "service"
    corr = (payload.get("correlation_id") or "").strip() or f"rounds_{uuid.uuid4().hex}"
    normalized_rounds = _normalize_round_specs(rounds)
    if not normalized_rounds:
        raise HTTPException(status_code=400, detail="No valid round services supplied")
    if not text:
        raise HTTPException(status_code=400, detail="Missing text")
    if preview:
        return {"status": "ok", "correlation_id": corr, "rounds": normalized_rounds}
    data = await _run_round_chain_request(normalized_rounds, text, sender=sender, correlation_id=corr)
    return {"status": "ok", "correlation_id": corr, "rounds": normalized_rounds, "response": data}


@app.post("/api/service/call")
async def service_call(payload: dict = Body(...)):
    if not current_valley:
        raise HTTPException(status_code=404, detail="No valley available")
    campfire = (payload.get("campfire") or "").strip()
    text = (payload.get("text") or "").strip()
    if not campfire or not text:
        raise HTTPException(status_code=400, detail="Missing campfire or text")
    sender = (payload.get("sender_valley") or "service").strip() or "service"
    torch = Torch(
        claim="service_request",
        source_campfire="service",
        channel="service",
        torch_id=f"service_{uuid.uuid4().hex}",
        sender_valley=sender,
        target_address=f"valley:{current_valley.name}/{campfire}",
        data={"text": text},
        signature="service_placeholder",
    )
    resp = await current_valley.process_torch(torch)
    if resp is None:
        return {"status": "ok", "response": None}
    data = getattr(resp, "data", None)
    return {"status": "ok", "response": data}


@app.get("/api/schedules")
async def list_schedules():
    if not current_valley:
        raise HTTPException(status_code=404, detail="No valley available")
    schedules = []
    for name in list(getattr(current_valley, "campfires", {}).keys()):
        if getattr(current_valley, "get_schedule", None):
            schedule = current_valley.get_schedule(name)
        else:
            schedule = None
        if schedule:
            last = getattr(current_valley, "_last_schedule_run", {}).get(name)
            schedules.append({"campfire": name, "schedule": schedule, "last_run": last})
    return {"status": "ok", "schedules": schedules}


@app.get("/api/logs/{campfire_name}")
async def get_logs(campfire_name: str, limit: int = 200):
    try:
        limit = int(limit)
    except Exception:
        limit = 200
    limit = max(1, min(limit, 2000))
    return {"status": "ok", "campfire": campfire_name, "entries": _read_logs(campfire_name, limit=limit)}


@app.post("/api/debug/ui-log")
async def ui_debug_log(payload: dict = Body(...)):
    event = (payload.get("event") or "").strip() or "ui_event"
    data = payload.get("data")
    try:
        body = json.dumps({"event": event, "data": data}, ensure_ascii=False)
    except Exception:
        body = str({"event": event, "data": str(data)})
    _append_log("UI Debug", "system", body)
    return {"status": "ok"}


@app.post("/api/campfire/export")
async def export_campfire(payload: dict = Body(...)):
    if not current_valley:
        raise HTTPException(status_code=404, detail="No valley available")
    campfire_name = (payload.get("campfire") or "").strip()
    if not campfire_name:
        raise HTTPException(status_code=400, detail="Missing campfire")
    cf = current_valley.campfires.get(campfire_name)
    if not cf:
        raise HTTPException(status_code=404, detail="Campfire not found")

    cfg = getattr(cf, "config", None)
    cfg_dump = cfg.model_dump(by_alias=True) if isinstance(cfg, CampfireConfig) else None
    logs = _read_logs(campfire_name, limit=2000)

    cfg_dir = _get_config_dir()
    belief_file = cfg_dir / f"camper_{_slugify(campfire_name)}_beliefs.yaml"
    beliefs_block = {}
    if belief_file.exists():
        try:
            beliefs_block = yaml.safe_load(belief_file.read_text(encoding="utf-8")) or {}
        except Exception:
            beliefs_block = {}

    bundle = {
        "version": "1",
        "exported_at": datetime.utcnow().isoformat(),
        "campfire": campfire_name,
        "campfire_config": cfg_dump,
        "logs": logs,
        "beliefs": {
            "beliefs": (beliefs_block.get("beliefs") if isinstance(beliefs_block, dict) else []) or [],
        },
    }

    out_yaml = yaml.safe_dump(bundle, sort_keys=False, allow_unicode=True)
    filename = f"campfire_export_{_slugify(campfire_name)}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.yaml"
    return {"status": "ok", "filename": filename, "yaml": out_yaml}


@app.post("/api/campfire/import")
async def import_campfire(payload: dict = Body(...)):
    if not current_valley:
        raise HTTPException(status_code=404, detail="No valley available")
    raw = payload.get("yaml")
    if not raw or not isinstance(raw, str):
        raise HTTPException(status_code=400, detail="Missing yaml")
    data = yaml.safe_load(raw) or {}
    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="Invalid yaml")

    campfire_name = (data.get("campfire") or "").strip()
    cfg_raw = data.get("campfire_config")
    logs = data.get("logs") or []
    beliefs_block = data.get("beliefs") or {}

    if not campfire_name:
        raise HTTPException(status_code=400, detail="Missing campfire name")
    if not isinstance(cfg_raw, dict):
        raise HTTPException(status_code=400, detail="Missing campfire_config")

    if campfire_name in current_valley.campfires:
        try:
            await current_valley.campfires[campfire_name].stop()
        finally:
            current_valley.campfires.pop(campfire_name, None)

    cfg = CampfireConfig(**cfg_raw)
    cfg.name = campfire_name
    ok = await current_valley.provision_campfire(cfg)
    if not ok:
        raise HTTPException(status_code=502, detail="Failed to provision campfire")

    if isinstance(logs, list):
        _write_logs(campfire_name, [e for e in logs if isinstance(e, dict)])

    beliefs_list = []
    if isinstance(beliefs_block, dict):
        beliefs_list = beliefs_block.get("beliefs") or []
    if isinstance(beliefs_list, list):
        beliefs_list = [b for b in beliefs_list if isinstance(b, str) and b.strip()]
    if beliefs_list:
        embeddings = _embed_texts(beliefs_list)
        collection = _get_beliefs_collection()
        ids = [f"{_slugify(campfire_name)}_{uuid.uuid4().hex}" for _ in beliefs_list]
        metadatas = [{"campfire": campfire_name, "created_at": datetime.utcnow().isoformat(), "imported": True} for _ in beliefs_list]
        collection.add(ids=ids, documents=beliefs_list, embeddings=embeddings, metadatas=metadatas)

        cfg_dir = _get_config_dir()
        cfg_dir.mkdir(parents=True, exist_ok=True)
        out_name = f"camper_{_slugify(campfire_name)}_beliefs.yaml"
        out_path = cfg_dir / out_name
        snapshot = {
            "version": "1",
            "saved_at": datetime.utcnow().isoformat(),
            "campfire": campfire_name,
            "beliefs": beliefs_list,
            "belief_ids": ids,
            "imported": True,
        }
        with out_path.open("w", encoding="utf-8") as f:
            yaml.safe_dump(snapshot, f, sort_keys=False, allow_unicode=True)

    return {"status": "ok", "campfire": campfire_name}


@app.get("/api/valley/snapshots")
async def list_snapshots():
    cfg_dir = _get_config_dir()
    cfg_dir.mkdir(parents=True, exist_ok=True)
    items = []
    for p in cfg_dir.glob("*.yaml"):
        try:
            st = p.stat()
            items.append({
                "name": p.name,
                "size": st.st_size,
                "mtime": datetime.utcfromtimestamp(st.st_mtime).isoformat() + "Z",
            })
        except Exception:
            items.append({"name": p.name, "size": None, "mtime": None})
    items.sort(key=lambda x: (x.get("mtime") or "", x.get("name") or ""), reverse=True)
    return {"status": "ok", "snapshots": items}


@app.post("/api/valley/save")
async def save_valley(payload: dict = Body(...)):
    if not current_valley:
        raise HTTPException(status_code=404, detail="No valley available")
    cfg_dir = _get_config_dir()
    cfg_dir.mkdir(parents=True, exist_ok=True)

    graph = payload.get("graph") or {}
    filename = payload.get("filename")
    if not filename:
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = f"valley_snapshot_{ts}.yaml"
    if not filename.endswith(".yaml"):
        filename = f"{filename}.yaml"
    path = cfg_dir / filename

    campfires = []
    for _, cf in current_valley.campfires.items():
        cfg = getattr(cf, "config", None)
        if isinstance(cfg, CampfireConfig):
            campfires.append(cfg.model_dump(by_alias=True))
        elif isinstance(cfg, dict):
            campfires.append(cfg)

    snapshot = {
        "version": "1",
        "saved_at": datetime.utcnow().isoformat(),
        "valley": {"name": current_valley.name},
        "campfires": campfires,
        "graph": graph,
    }

    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(snapshot, f, sort_keys=False, allow_unicode=True)

    return {"status": "ok", "filename": filename}


@app.post("/api/valley/load")
async def load_valley(payload: dict = Body(...)):
    if not current_valley:
        raise HTTPException(status_code=404, detail="No valley available")
    filename = payload.get("filename")
    if not filename:
        raise HTTPException(status_code=400, detail="Missing filename")
    cfg_dir = _get_config_dir()
    path = cfg_dir / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="Snapshot not found")

    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    campfire_cfgs = data.get("campfires") or []
    graph = data.get("graph") or {}

    existing = list(current_valley.campfires.keys())
    for name in existing:
        try:
            cf = current_valley.campfires.get(name)
            if cf:
                await cf.stop()
        finally:
            current_valley.campfires.pop(name, None)

    restored = []
    for raw in campfire_cfgs:
        try:
            cfg = CampfireConfig(**raw)
        except Exception:
            continue
        ok = await current_valley.provision_campfire(cfg)
        if ok:
            restored.append(cfg.name)

    try:
        campfire_parent.clear()
        _refresh_graph_context_from_snapshot(graph)
    except Exception:
        pass

    try:
        for name in restored:
            try:
                wf = current_valley.get_workflow(name) if getattr(current_valley, "get_workflow", None) else None
            except Exception:
                pass
    except Exception:
        pass

    return {"status": "ok", "restored": restored, "graph": graph}


@app.post("/api/valley/delete_snapshot")
async def delete_snapshot(payload: dict = Body(...)):
    if not current_valley:
        raise HTTPException(status_code=404, detail="No valley available")
    filename = (payload.get("filename") or "").strip()
    if not filename:
        raise HTTPException(status_code=400, detail="Missing filename")
    cfg_dir = _get_config_dir()
    path = cfg_dir / filename
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Snapshot not found")
    try:
        path.unlink()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete: {e}")
    return {"status": "ok", "removed": filename}


@app.post("/api/beliefs/freeze")
async def freeze_beliefs(payload: dict = Body(...)):
    if not current_valley:
        raise HTTPException(status_code=404, detail="No valley available")
    campfire_name = (payload.get("campfire") or "").strip()
    if not campfire_name:
        raise HTTPException(status_code=400, detail="Missing campfire")
    messages = payload.get("messages") or []
    if not isinstance(messages, list):
        raise HTTPException(status_code=400, detail="Invalid messages")

    cf = current_valley.campfires.get(campfire_name)
    cfg = getattr(cf, "config", None) if cf else None
    if not isinstance(cfg, CampfireConfig):
        cfg = None

    beliefs = _extract_beliefs(campfire_name, cfg, messages)
    embeddings = _embed_texts(beliefs)
    collection = _get_beliefs_collection()
    ids = [f"{_slugify(campfire_name)}_{uuid.uuid4().hex}" for _ in beliefs]
    metadatas = [{"campfire": campfire_name, "created_at": datetime.utcnow().isoformat()} for _ in beliefs]
    collection.add(ids=ids, documents=beliefs, embeddings=embeddings, metadatas=metadatas)

    cfg_dir = _get_config_dir()
    cfg_dir.mkdir(parents=True, exist_ok=True)
    out_name = f"camper_{_slugify(campfire_name)}_beliefs.yaml"
    out_path = cfg_dir / out_name
    snapshot = {
        "version": "1",
        "saved_at": datetime.utcnow().isoformat(),
        "campfire": campfire_name,
        "beliefs": beliefs,
        "belief_ids": ids,
    }
    if cfg:
        snapshot["campfire_config"] = cfg.model_dump(by_alias=True)
    with out_path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(snapshot, f, sort_keys=False, allow_unicode=True)

    return {"status": "ok", "campfire": campfire_name, "count": len(beliefs), "filename": out_name, "beliefs": beliefs[:10]}


@app.post("/api/beliefs/clear")
async def clear_beliefs(payload: dict = Body(...)):
    if not current_valley:
        raise HTTPException(status_code=404, detail="No valley available")
    campfire_name = (payload.get("campfire") or "").strip()
    if not campfire_name:
        raise HTTPException(status_code=400, detail="Missing campfire")
    result = _clear_beliefs_for_campfire(campfire_name)
    return {"status": "ok", **result}


@app.post("/api/beliefs/query")
async def query_beliefs(payload: dict = Body(...)):
    campfire_name = (payload.get("campfire") or "").strip()
    query = (payload.get("query") or "").strip()
    k = payload.get("k") or 5
    try:
        k = int(k)
    except Exception:
        k = 5
    if not campfire_name or not query:
        raise HTTPException(status_code=400, detail="Missing campfire or query")
    try:
        beliefs = _query_beliefs(campfire_name, query, k=max(1, min(k, 20)))
        return {"status": "ok", "campfire": campfire_name, "beliefs": beliefs}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Query failed: {e}")

async def _handle_auditor_conversation(text: str) -> str:
    t = text.strip()
    low = t.lower()
    global auditor_dialog
    if "add camper" in low:
        auditor_dialog = {"active": True, "fields": {}, "awaiting": ["name", "persona", "model", "system_prompt"]}
    if auditor_dialog.get("active"):
        f = auditor_dialog["fields"]
        import re
        m = re.search(r"name\s+([A-Za-z0-9_\- ]+)", low)
        if m:
            f["name"] = m.group(1).strip()
        m = re.search(r"persona\s+([A-Za-z0-9_\- ]+)", low)
        if m:
            f["persona"] = m.group(1).strip()
        m = re.search(r"model\s+([A-Za-z0-9_\-:]+)", low)
        if m:
            f["model"] = m.group(1).strip()
        m = re.search(r"(?:prompt|system\s+prompt)\s*[:\-]\s*(.+)", t, re.IGNORECASE)
        if m:
            f["system_prompt"] = m.group(1).strip()
        missing = [k for k in ["name", "persona", "model", "system_prompt"] if not f.get(k)]
        if missing:
            auditor_dialog["awaiting"] = missing
            return "Please provide " + ", ".join(missing) + " for the new camper."
        from ..models import CampfireConfig
        cfg = {
            "llm": {"model": f.get("model", get_default_ollama_model())},
            "prompts": {"system": f.get("system_prompt") or _software_campfire_system_prompt(str(f.get("name") or "Camper"), str(f.get("persona") or ""))},
            "persona": {"name": f.get("name"), "persona": f.get("persona"), "model": f.get("model")},
            "rag": {"documents": _default_rag_documents(f.get("name") or "Camper", f.get("persona"))},
        }
        c = CampfireConfig(name=f["name"], type="LLMCampfire", config=cfg)
        ok = await current_valley.provision_campfire(c)
        auditor_dialog = {"active": False, "fields": {}, "awaiting": []}
        if ok:
            return f"Created camper '{f['name']}' with persona '{f['persona']}' and model '{cfg['llm']['model']}'."
        return "Failed to create the camper."
    return "Auditor is listening. Say 'add camper' to begin, then provide name, persona, model, and system prompt."

@app.post("/api/team/organize")
async def team_organize(request: dict = Body(...)):
    if not current_valley:
        raise HTTPException(status_code=404, detail="No valley available")
    personas = request.get("personas") or []
    base = request.get("base_campfire") or "Development Team"
    created = []
    for p in personas:
        name = p.get("name") or f"{base}-{len(created)+1}"
        cfg = {
            "llm": {
                "model": p.get("model") or get_default_ollama_model()
            },
            "prompts": {
                "system": p.get("system_prompt") or _software_campfire_system_prompt(name, str(p.get("persona", "generic")))
            },
            "persona": p,
            "rag": {"documents": _default_rag_documents(name, p.get("persona"))},
        }
        campfire_cfg = current_valley.__class__.__module__
        from ..models import CampfireConfig
        c = CampfireConfig(name=name, type="LLMCampfire", config=cfg)
        ok = await current_valley.provision_campfire(c)
        if ok:
            created.append(name)
    return {"status": "success", "created": created}

@app.post("/api/team/add")
async def team_add(request: dict = Body(...)):
    if not current_valley:
        raise HTTPException(status_code=404, detail="No valley available")
    p = request.get("persona") or {}
    name = p.get("name") or request.get("name") or f"Persona-{datetime.now().strftime('%H%M%S')}"
    rag_docs = None
    if isinstance(request.get("rag"), dict) and isinstance(request.get("rag").get("documents"), list):
        rag_docs = [d for d in request["rag"]["documents"] if isinstance(d, str) and d.strip()]
    if rag_docs is None:
        rag_template = request.get("rag_template")
        if isinstance(rag_template, str) and rag_template.strip():
            rag_docs = [rag_template.strip()]
    cfg = {
        "llm": {
            "provider": p.get("provider") or "ollama",
            "base_url": p.get("base_url") or os.getenv("OLLAMA_HOST", "http://host.docker.internal:11434"),
            "model": p.get("model") or get_default_ollama_model()
        },
        "prompts": {
            "system": p.get("system_prompt") or _software_campfire_system_prompt(name, str(p.get("persona", "generic")))
        },
        "persona": p,
        "rag": {"documents": rag_docs or _default_rag_documents(name, p.get("persona"))},
    }
    from ..models import CampfireConfig
    c = CampfireConfig(name=name, type="LLMCampfire", config=cfg)
    ok = await current_valley.provision_campfire(c)
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to add camper")
    return {"status": "success", "created": name}

async def update_loop():
    """Background task to broadcast state updates"""
    while True:
        try:
            if visualizer and manager.active_connections:
                # Get fresh state from valley
                state = await visualizer.get_current_state()
                global current_state
                current_state = state
                
                # Add current task info to the state
                global current_task
                state_data = state.dict()
                if current_task:
                    state_data["current_task"] = current_task
                
                message = WebSocketMessage(
                    type="state_update",
                    data=state_data
                )
                await manager.broadcast(message.json())
                
                # Also send task-specific updates if there's an active task
                if current_task:
                    task_message = WebSocketMessage(
                        type="task_update",
                        data=current_task
                    )
                    await manager.broadcast(task_message.json())
                    
        except Exception as e:
            print(f"Error in update loop: {e}")
        
        await asyncio.sleep(2)  # Update every 2 seconds


# Task Processing Endpoints
@app.post("/api/tasks/start")
async def start_task(request: dict):
    """Start a new task for processing by campfires"""
    try:
        task_description = request.get("task", "")
        timestamp = request.get("timestamp", "")
        
        if not task_description:
            raise HTTPException(status_code=400, detail="Task description is required")
        
        # Generate a unique task ID
        import uuid
        task_id = str(uuid.uuid4())[:8]
        
        # Store task info globally for tracking
        global current_task
        current_task = {
            "id": task_id,
            "description": task_description,
            "timestamp": timestamp,
            "status": "processing"
        }
        
        # If we have a valley, we can simulate task processing
        if current_valley:
            # Simulate distributing the task to campfires
            campfires = list(current_valley.campfires.values())
            
            # For demo purposes, we'll simulate activity by updating campfire states
            import asyncio
            asyncio.create_task(simulate_task_processing(task_id, task_description, campfires))
        
        return {
            "status": "success",
            "task_id": task_id,
            "message": f"Task '{task_description}' started",
            "campfires_assigned": len(current_valley.campfires) if current_valley else 0
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error starting task: {str(e)}")


@app.post("/api/tasks/stop")
async def stop_task():
    """Stop the current task processing"""
    try:
        global current_task
        if current_task:
            current_task["status"] = "stopped"
            task_id = current_task["id"]
            current_task = None
            
            return {
                "status": "success",
                "message": f"Task {task_id} stopped",
                "task_id": task_id
            }
        else:
            return {
                "status": "success",
                "message": "No active task to stop"
            }
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error stopping task: {str(e)}")


@app.get("/api/tasks/current")
async def get_current_task():
    """Get information about the current task"""
    global current_task
    if current_task:
        return current_task
    else:
        return {"status": "no_active_task"}


# Task simulation function
async def simulate_task_processing(task_id: str, task_description: str, campfires: list):
    """Simulate task processing across campfires for demo purposes"""
    try:
        import random
        import asyncio
        
        # Simulate processing stages
        stages = [
            "Analyzing task",
            "Distributing to campfires", 
            "Processing in parallel",
            "Gathering results",
            "Finalizing output"
        ]
        
        for i, stage in enumerate(stages):
            # Check if task was stopped
            global current_task
            if not current_task or current_task.get("status") == "stopped":
                break
                
            # Update task status
            if current_task:
                current_task["current_stage"] = stage
                current_task["progress"] = (i + 1) / len(stages) * 100
            
            # Simulate some campfire activity
            if campfires and len(campfires) > 0:
                active_campfire = random.choice(campfires)
                # In a real implementation, we would actually send tasks to campfires
                # For now, we just simulate activity
                
            # Wait between stages
            await asyncio.sleep(2)
        
        # Mark task as completed
        if current_task and current_task.get("status") != "stopped":
            current_task["status"] = "completed"
            current_task["current_stage"] = "Task completed"
            current_task["progress"] = 100
            
            # Auto-clear completed task after a delay
            await asyncio.sleep(5)
            if current_task and current_task.get("status") == "completed":
                current_task = None
                
    except Exception as e:
        print(f"Error in task simulation: {e}")
        if current_task:
            current_task["status"] = "error"
            current_task["error"] = str(e)


# Global task tracking
current_task = None


@app.on_event("startup")
async def startup_event():
    """Start background tasks"""
    asyncio.create_task(update_loop())


def create_web_server(valley: Valley, host: str = "0.0.0.0", port: int = 8000):
    """Create and configure the web server for a valley"""
    set_valley(valley)
    return app


async def run_web_server(valley: Valley, host: str = "0.0.0.0", port: int = 8000):
    """Run the web server for valley visualization"""
    set_valley(valley)
    config = uvicorn.Config(app, host=host, port=port)
    server = uvicorn.Server(config)
    await server.serve()


if __name__ == "__main__":
    # For testing without a valley
    uvicorn.run(app, host="0.0.0.0", port=8000)

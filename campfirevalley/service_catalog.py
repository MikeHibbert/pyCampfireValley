"""
Shared helpers for building service manifests for local and dock discovery.
"""

from __future__ import annotations

import re
from typing import Any, Callable, Dict, List, Optional

from .models import CampfireConfig


def _slugify(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "-", str(value or "").strip().lower()).strip("-")


def get_valley_identity(valley: Any) -> Dict[str, str]:
    name = "valley"
    identifier = ""
    try:
        cfg = valley.get_config() if hasattr(valley, "get_config") else getattr(valley, "config", None)
        name = str(getattr(cfg, "name", None) or getattr(valley, "name", None) or "valley")
        env = getattr(cfg, "env", None) or {}
        if isinstance(env, dict):
            identifier = (env.get("valley_id") or "").strip()
    except Exception:
        name = str(getattr(valley, "name", None) or "valley")
        identifier = ""
    if not identifier:
        identifier = name
    return {"name": name, "identifier": identifier}


def _config_dict_for_service(cf: Any) -> Dict[str, Any]:
    cfg = getattr(cf, "config", None)
    if isinstance(cfg, CampfireConfig):
        return cfg.config or {}
    if isinstance(cfg, dict):
        conf = cfg.get("config")
        return conf if isinstance(conf, dict) else cfg
    return {}


def _dedupe_strings(values: List[Any]) -> List[str]:
    out: List[str] = []
    seen = set()
    for raw in values or []:
        text = str(raw or "").strip()
        key = text.lower()
        if not text or key in seen:
            continue
        out.append(text)
        seen.add(key)
    return out


def _infer_summary(name: str, kind: str, task_types: List[str], role_tags: List[str], prompts: Dict[str, Any]) -> str:
    system_prompt = (prompts.get("system") or "").strip() if isinstance(prompts, dict) else ""
    if system_prompt:
        first_line = system_prompt.splitlines()[0].strip()
        if first_line:
            return first_line[:220]
    if task_types:
        return f"{name} handles {', '.join(task_types[:3])} work."
    if role_tags:
        return f"{name} is a {kind} service for {', '.join(role_tags[:3])}."
    return f"{name} is a {kind} service in CampfireValley."


def _normalize_exposure(explicit: str, visible_names: List[str], service_name: str) -> str:
    value = (explicit or "").strip().lower()
    if value in {"private", "federation", "public"}:
        return value
    if service_name in set(visible_names or []):
        return "public"
    return "private"


def build_service_manifest(
    valley: Any,
    service_name: str,
    cf: Any,
    parent_lookup: Optional[Dict[str, str]] = None,
    include_auditors: bool = False,
    visible_names: Optional[List[str]] = None,
) -> Optional[Dict[str, Any]]:
    name = str(service_name or "").strip()
    if not name:
        return None
    if not include_auditors and name.endswith(" Auditor"):
        return None

    conf = _config_dict_for_service(cf)
    dock_cfg = conf.get("dock") if isinstance(conf.get("dock"), dict) else {}
    service_cfg = conf.get("service") if isinstance(conf.get("service"), dict) else {}
    llm = conf.get("llm") if isinstance(conf.get("llm"), dict) else {}
    prompts = conf.get("prompts") if isinstance(conf.get("prompts"), dict) else {}
    tools_cfg = conf.get("tools") if isinstance(conf.get("tools"), dict) else {}
    zeitgeist_tools = tools_cfg.get("zeitgeist") if isinstance(tools_cfg.get("zeitgeist"), dict) else {}
    identity = get_valley_identity(valley)
    identifier = (dock_cfg.get("identifier") or "").strip() if isinstance(dock_cfg, dict) else ""
    address_key = identifier or name

    parent_name = (parent_lookup or {}).get(name)
    kind = "camper" if (parent_name or name.lower().endswith(" camper")) else "campfire"
    service_kind = "auditor" if name.endswith(" Auditor") else kind

    capabilities: List[str] = [kind]
    role_tags: List[str] = []
    task_types: List[str] = []

    if service_kind == "auditor":
        capabilities.append("auditor")
        role_tags.extend(["auditor", "coordination"])
        task_types.extend(["coordinate", "plan", "review"])
    if kind == "camper":
        role_tags.append("camper")
    if isinstance(zeitgeist_tools, dict) and zeitgeist_tools:
        capabilities.append("tools")
        role_tags.append("tool-use")
        task_types.append("tool-assisted")
    if isinstance(llm, dict) and llm.get("model"):
        capabilities.append("llm")
        role_tags.append("llm")
        task_types.append("respond")
    workflow = None
    if kind == "campfire" and getattr(valley, "get_workflow", None):
        try:
            workflow = valley.get_workflow(name)
        except Exception:
            workflow = None
    if workflow:
        capabilities.append("workflow")
        role_tags.append("workflow")
        task_types.extend(["workflow", "multi-step"])
    schedule = None
    if kind == "campfire" and getattr(valley, "get_schedule", None):
        try:
            schedule = valley.get_schedule(name)
        except Exception:
            schedule = None
    if schedule and isinstance(schedule, dict) and schedule.get("enabled"):
        capabilities.append("schedule")

    role_tags.extend(service_cfg.get("role_tags") or [])
    task_types.extend(service_cfg.get("task_types") or [])
    role_tags = _dedupe_strings(role_tags)
    task_types = _dedupe_strings(task_types)
    capabilities = _dedupe_strings(capabilities + list(service_cfg.get("capabilities") or []))

    summary = (service_cfg.get("summary") or "").strip() or _infer_summary(name, service_kind, task_types, role_tags, prompts)
    description = (service_cfg.get("description") or "").strip()
    exposure = _normalize_exposure(
        str(service_cfg.get("exposure") or dock_cfg.get("exposure") or ""),
        visible_names or [],
        name,
    )
    supports_rounds = bool(service_cfg.get("supports_rounds", kind in {"campfire", "camper"}))

    accepts = service_cfg.get("accepts") if isinstance(service_cfg.get("accepts"), dict) else {}
    returns = service_cfg.get("returns") if isinstance(service_cfg.get("returns"), dict) else {}

    accepts_content_types = _dedupe_strings(list(accepts.get("content_types") or ["text/plain", "text/markdown", "application/json"]))
    returns_content_types = _dedupe_strings(list(returns.get("content_types") or ["text/plain", "text/markdown", "application/json"]))

    manifest = {
        "manifest_version": "1.0",
        "service_id": (service_cfg.get("id") or identifier or _slugify(name) or name),
        "name": name,
        "kind": kind,
        "service_kind": service_kind,
        "type": cf.__class__.__name__,
        "running": bool(getattr(cf, "_running", False)),
        "parent": parent_name,
        "identifier": identifier,
        "summary": summary,
        "description": description,
        "role_tags": role_tags,
        "task_types": task_types,
        "supports_rounds": supports_rounds,
        "exposure": exposure,
        "exposed": exposure in {"public", "federation"},
        "addresses": {
            "valley_id": f"valley:{identity['identifier']}/{address_key}",
            "valley_name": f"valley:{identity['name']}/{address_key}",
        },
        "llm": {
            "provider": (llm.get("provider") or "").strip() if isinstance(llm, dict) else "",
            "model": (llm.get("model") or "").strip() if isinstance(llm, dict) else "",
        },
        "accepts": {
            "content_types": accepts_content_types,
            "task_types": task_types,
            "input_schema": (accepts.get("input_schema") or "").strip() if isinstance(accepts, dict) else "",
        },
        "returns": {
            "content_types": returns_content_types,
            "output_schema": (returns.get("output_schema") or "").strip() if isinstance(returns, dict) else "",
        },
        "capabilities": capabilities,
    }
    return manifest


def build_service_catalog(
    valley: Any,
    include_auditors: bool = False,
    parent_lookup: Optional[Dict[str, str]] = None,
    visible_names: Optional[List[str]] = None,
    exposed_only: bool = False,
) -> Dict[str, Any]:
    identity = get_valley_identity(valley)
    try:
        campfires = valley.get_campfires() if hasattr(valley, "get_campfires") else getattr(valley, "campfires", {})
    except Exception:
        campfires = {}
    services: List[Dict[str, Any]] = []
    for name, cf in (campfires or {}).items():
        manifest = build_service_manifest(
            valley,
            str(name),
            cf,
            parent_lookup=parent_lookup,
            include_auditors=include_auditors,
            visible_names=visible_names,
        )
        if not manifest:
            continue
        if exposed_only and not manifest.get("exposed"):
            continue
        services.append(manifest)
    services.sort(key=lambda s: (s.get("service_kind") or "", s.get("parent") or "", s.get("name") or ""))
    return {"status": "ok", "type": "services", "valley": identity, "services": services}


def build_discovery_service_summaries(
    valley: Any,
    include_auditors: bool = False,
    parent_lookup: Optional[Dict[str, str]] = None,
    visible_names: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    catalog = build_service_catalog(
        valley,
        include_auditors=include_auditors,
        parent_lookup=parent_lookup,
        visible_names=visible_names,
        exposed_only=True,
    )
    out: List[Dict[str, Any]] = []
    for service in catalog.get("services") or []:
        out.append({
            "service_id": service.get("service_id"),
            "name": service.get("name"),
            "kind": service.get("kind"),
            "service_kind": service.get("service_kind"),
            "summary": service.get("summary"),
            "role_tags": service.get("role_tags") or [],
            "task_types": service.get("task_types") or [],
            "supports_rounds": bool(service.get("supports_rounds")),
            "exposure": service.get("exposure"),
            "addresses": service.get("addresses") or {},
            "capabilities": service.get("capabilities") or [],
        })
    return out

"""
Main web server entry point for CampfireValley visualization
"""

import asyncio
import argparse
from pathlib import Path
import sys
from typing import Any
import re
import yaml

# Add the parent directory to the path so we can import campfirevalley
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from campfirevalley.valley import Valley
from campfirevalley.llm_defaults import get_default_ollama_model
from campfirevalley.models import CampfireConfig
import os
from campfirevalley.web.api import run_web_server
from campfirevalley.config import ConfigManager
import uuid





async def create_demo_valley():
    """Create a demo valley for testing the web interface"""
    
    valley_name = os.environ.get("VALLEY_NAME", "Demo Valley")
    enable_dock = os.environ.get("ENABLE_DOCK_ON_START", "true").strip().lower() in {"1", "true", "yes"}
    redis_url = os.environ.get("REDIS_URL", "redis://redis:6379")
    broker = redis_url if enable_dock else None
    valley = Valley(name=valley_name, mcp_broker=broker)
    raw_vid = (os.environ.get("VALLEY_IDENTIFIER") or "").strip()
    vid = ""
    if raw_vid:
        try:
            _ = uuid.UUID(raw_vid)
            vid = raw_vid
        except Exception:
            vid = ""
    if not vid:
        vid = uuid.uuid4().hex
    valley.config.env["valley_id"] = vid
    mode = os.environ.get("DOCK_MODE", "").strip().lower()
    if mode in {"private", "partial", "public"}:
        valley.config.env["dock_mode"] = mode
    valley.config.env["auto_create_dock"] = enable_dock
    
    # Start the valley first
    await valley.start()

    try:
        cfg_dir = Path(os.environ.get("CONFIG_DIR", "/app/data/configs"))
        cfg_dir.mkdir(parents=True, exist_ok=True)
        loaded_any = False
        try:
            snapshots = list(cfg_dir.glob("valley_snapshot_*.yaml"))
        except Exception:
            snapshots = []
        latest = None
        try:
            latest = max(snapshots, key=lambda p: p.stat().st_mtime) if snapshots else None
        except Exception:
            latest = None
        if latest and latest.exists():
            try:
                data = yaml.safe_load(latest.read_text(encoding="utf-8")) or {}
            except Exception:
                data = {}
            for raw in (data.get("campfires") or []):
                if not isinstance(raw, dict):
                    continue
                try:
                    cfg = CampfireConfig(**raw)
                except Exception:
                    continue
                try:
                    ok = await valley.provision_campfire(cfg)
                    loaded_any = loaded_any or bool(ok)
                except Exception:
                    continue
        if not loaded_any:
            for p in sorted(cfg_dir.glob("campfire_*.yaml")):
                try:
                    cfg = ConfigManager.load_campfire_config(str(p))
                except Exception:
                    continue
                try:
                    ok = await valley.provision_campfire(cfg)
                    loaded_any = loaded_any or bool(ok)
                except Exception:
                    continue
    except Exception:
        pass
    
    ollama_base = os.environ.get("OLLAMA_HOST", "http://host.docker.internal:11434")
    main_system_prompt = (
        "You are Main Campfire, a software campfire inside the CampfireValley Python system. "
        "In this context, campfires are AI roles/modules and collaborative workspaces, not literal outdoor fires. "
        "Campers are specialized sub-roles, auditors coordinate work, torches carry requests and results, and rounds chain outputs across campfires. "
        "Help the user with software-oriented CampfireValley tasks, design, orchestration, debugging, and implementation. "
        "If a request is ambiguous, ask a brief clarifying question instead of inventing physical campfire details."
    )
    main_cfg = CampfireConfig(
        name="Main Campfire",
        type="LLMCampfire",
        config={
            "llm": {"provider": "ollama", "base_url": ollama_base, "model": get_default_ollama_model()},
            "prompts": {"system": main_system_prompt},
        },
    )
    try:
        existing_main = valley.campfires.get("Main Campfire")
        existing_cfg = getattr(existing_main, "config", None) if existing_main else None
        if isinstance(existing_cfg, CampfireConfig):
            conf = existing_cfg.config if isinstance(existing_cfg.config, dict) else {}
            prompts = conf.get("prompts") if isinstance(conf.get("prompts"), dict) else {}
            prompts["system"] = main_system_prompt
            conf["prompts"] = prompts
            existing_cfg.config = conf
            if isinstance(existing_cfg.prompts, dict):
                existing_cfg.prompts["system"] = main_system_prompt
    except Exception:
        pass
    persisted_ident = ""
    try:
        cfg_dir = Path(os.environ.get("CONFIG_DIR", "/app/data/configs"))
        safe_name = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(main_cfg.name).strip()).strip("_") or "campfire"
        persisted_path = cfg_dir / f"campfire_{safe_name}.yaml"
        if persisted_path.exists():
            persisted_cfg = ConfigManager.load_campfire_config(str(persisted_path))
            conf = persisted_cfg.config if isinstance(persisted_cfg.config, dict) else {}
            dock_cfg = conf.get("dock") if isinstance(conf.get("dock"), dict) else {}
            persisted_ident = (dock_cfg.get("identifier") or "").strip() if isinstance(dock_cfg, dict) else ""
    except Exception:
        persisted_ident = ""
    dock_ident = (os.environ.get("CAMPFIRE_IDENTIFIER") or "").strip() or persisted_ident
    if dock_ident:
        try:
            main_cfg.config = main_cfg.config or {}
            main_cfg.config.setdefault("dock", {})
            if isinstance(main_cfg.config.get("dock"), dict):
                main_cfg.config["dock"]["identifier"] = dock_ident
        except Exception:
            pass
    ok = await valley.provision_campfire(main_cfg)
    if not ok and dock_ident:
        try:
            existing = valley.campfires.get(main_cfg.name)
            existing_cfg = getattr(existing, "config", None) if existing else None
            if isinstance(existing_cfg, CampfireConfig):
                existing_cfg.config = existing_cfg.config or {}
                dock_cfg = existing_cfg.config.get("dock") if isinstance(existing_cfg.config.get("dock"), dict) else {}
                dock_cfg["identifier"] = dock_ident
                existing_cfg.config["dock"] = dock_cfg
            elif isinstance(existing_cfg, dict):
                existing_cfg.setdefault("config", {})
                conf = existing_cfg.get("config") if isinstance(existing_cfg.get("config"), dict) else {}
                dock_cfg = conf.get("dock") if isinstance(conf.get("dock"), dict) else {}
                dock_cfg["identifier"] = dock_ident
                conf["dock"] = dock_cfg
                existing_cfg["config"] = conf
        except Exception:
            pass
    valley.config.campfires["visible"] = ["Main Campfire"]
    
    return valley


async def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="CampfireValley Web Visualization Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind to")
    parser.add_argument("--demo", action="store_true", help="Run with demo data")
    
    args = parser.parse_args()
    
    if args.demo:
        print("Creating demo valley...")
        valley = await create_demo_valley()
        print(f"Demo valley created with {len(valley.campfires)} campfires")
    else:
        # In a real scenario, you would load your actual valley here
        print("No valley specified, creating empty valley...")
        valley = Valley(name="Empty Valley")
    
    print(f"Starting web server on {args.host}:{args.port}")
    print(f"Open your browser to http://{args.host}:{args.port}")
    
    # Run the web server
    await run_web_server(valley, host=args.host, port=args.port)


if __name__ == "__main__":
    asyncio.run(main())

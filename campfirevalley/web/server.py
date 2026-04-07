"""
Main web server entry point for CampfireValley visualization
"""

import asyncio
import argparse
from pathlib import Path
import sys
from typing import Any

# Add the parent directory to the path so we can import campfirevalley
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from campfirevalley.valley import Valley
from campfirevalley.models import CampfireConfig
import os
from campfirevalley.web.api import run_web_server





async def create_demo_valley():
    """Create a demo valley for testing the web interface"""
    
    valley_name = os.environ.get("VALLEY_NAME", "Demo Valley")
    enable_dock = os.environ.get("ENABLE_DOCK_ON_START", "false").strip().lower() in {"1", "true", "yes"}
    redis_url = os.environ.get("REDIS_URL", "redis://redis:6379")
    broker = redis_url if enable_dock else None
    valley = Valley(name=valley_name, mcp_broker=broker)
    mode = os.environ.get("DOCK_MODE", "").strip().lower()
    if mode in {"private", "partial", "public"}:
        valley.config.env["dock_mode"] = mode
    valley.config.env["auto_create_dock"] = enable_dock
    
    # Start the valley first
    await valley.start()
    
    ollama_base = os.environ.get("OLLAMA_HOST", "http://host.docker.internal:11434")
    main_cfg = CampfireConfig(
        name="Main Campfire",
        type="LLMCampfire",
        config={
            "llm": {"provider": "ollama", "base_url": ollama_base, "model": "gemma3:4b"},
            "prompts": {"system": "You are the main Campfire. Help the user build and refine their campfire setup."},
        },
    )
    await valley.provision_campfire(main_cfg)
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

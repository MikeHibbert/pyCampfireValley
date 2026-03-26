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
from campfirevalley.llm_campfire import create_openrouter_campfire, create_ollama_campfire
import os
from campfirevalley.web.api import run_web_server





async def create_demo_valley():
    """Create a demo valley for testing the web interface"""
    
    # Create demo valley without MCP broker to avoid Redis dependency
    valley = Valley(name="Demo Valley", mcp_broker=None)
    
    # Start the valley first
    await valley.start()
    
    # Create an LLM-enabled Development Team using local Ollama by default
    dev_cfg = CampfireConfig(name="Development Team", type="LLMCampfire")
    ollama_base = os.environ.get("OLLAMA_HOST", "http://host.docker.internal:11434")
    dev_llm = create_ollama_campfire(dev_cfg, valley.mcp_broker, base_url=ollama_base, default_model="gemma3:4b")
    await dev_llm.start()
    valley.campfires["Development Team"] = dev_llm
    
    # Add two plain demo teams
    config2 = CampfireConfig(name="Design Team")
    config3 = CampfireConfig(name="QA Team")
    await valley.provision_campfire(config2)
    await valley.provision_campfire(config3)
    
    # Add an Auditor team for conversational organization
    auditor_cfg = CampfireConfig(name="Auditor", type="LLMCampfire", config={"llm": {"model": "gemma3:4b"}, "prompts": {"system": "You are an auditor and organizer. Ask for missing details and confirm actions."}})
    await valley.provision_campfire(auditor_cfg)
    
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

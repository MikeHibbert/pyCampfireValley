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
from campfirevalley.web.api import run_web_server





async def create_demo_valley():
    """Create a demo valley for testing the web interface"""
    
    # Create a demo valley without MCP broker to avoid Redis dependency
    valley = Valley(name="Demo Valley", mcp_broker=None)
    
    # Start the valley first
    await valley.start()
    
    # Create demo campfire configs
    config1 = CampfireConfig(name="Development Team")
    config2 = CampfireConfig(name="Design Team")
    config3 = CampfireConfig(name="QA Team")
    
    # Provision campfires in valley
    await valley.provision_campfire(config1)
    await valley.provision_campfire(config2)
    await valley.provision_campfire(config3)
    
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
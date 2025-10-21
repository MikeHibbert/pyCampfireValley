#!/usr/bin/env python3
"""
CampfireValley with Web Monitoring Server

This script runs a complete CampfireValley setup with:
1. A valley with multiple campfire processes
2. Web frontend for real-time monitoring
3. REST API for external interactions

Perfect for Docker deployment and demonstration purposes.
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Import CampfireValley components
from campfirevalley.valley import Valley
from campfirevalley.models import CampfireConfig
from campfirevalley.web.api import run_web_server

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/app/logs/valley_web_server.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


async def create_demo_valley():
    """Create a demo valley with multiple campfires for demonstration"""
    logger.info("Creating demo valley...")
    
    # Create a valley without MCP broker to avoid Redis dependency issues
    valley = Valley(name="Demo Valley", mcp_broker=None)
    
    # Start the valley first
    await valley.start()
    
    # Create demo campfire configs
    configs = [
        CampfireConfig(name="Development Team", description="Handles software development tasks"),
        CampfireConfig(name="Design Team", description="Focuses on UI/UX design"),
        CampfireConfig(name="QA Team", description="Quality assurance and testing"),
        CampfireConfig(name="DevOps Team", description="Infrastructure and deployment"),
    ]
    
    # Provision campfires in valley
    for config in configs:
        try:
            await valley.provision_campfire(config)
            logger.info(f"Provisioned campfire: {config.name}")
        except Exception as e:
            logger.warning(f"Failed to provision campfire {config.name}: {e}")
    
    logger.info(f"Demo valley created with {len(valley.campfires)} campfires")
    return valley


async def main():
    """Main function that runs the valley with web monitoring"""
    logger.info("Starting CampfireValley with Web Monitoring...")
    
    try:
        # Create and start the valley
        valley = await create_demo_valley()
        
        # Get configuration from environment
        host = os.getenv("CAMPFIRE_VALLEY_HOST", "0.0.0.0")
        port = int(os.getenv("CAMPFIRE_VALLEY_PORT", "8080"))
        
        logger.info(f"Starting web server on {host}:{port}")
        logger.info(f"Web interface will be available at: http://{host}:{port}")
        
        # Start the web server with the valley
        await run_web_server(valley, host=host, port=port)
        
    except Exception as e:
        logger.error(f"Error starting valley with web server: {e}")
        raise


if __name__ == "__main__":
    # Ensure log directory exists
    os.makedirs("/app/logs", exist_ok=True)
    
    # Run the main function
    asyncio.run(main())
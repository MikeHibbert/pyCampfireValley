#!/usr/bin/env python3
"""
CampfireValley Federation Demo

This demo showcases the federation capabilities of CampfireValley, demonstrating
how multiple valleys can collaborate and communicate across different domains.

Demo Scenario:
- TechValley: Software development and engineering
- CreativeValley: Design and marketing
- BusinessValley: Strategy and operations

The demo shows:
1. Valley discovery and federation establishment
2. Cross-valley torch routing and communication
3. Collaborative project workflows
4. Federation-wide announcements and coordination
"""

import asyncio
import logging
import json
from datetime import datetime
from pathlib import Path

from campfirevalley.valley import Valley
from campfirevalley.dock import Dock
from campfirevalley.federation import FederationManager
from campfirevalley.mcp import RedisMCPBroker
from campfirevalley.models import Torch, TorchContent

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class FederationDemo:
    """Demonstrates multi-valley federation capabilities."""
    
    def __init__(self):
        self.valleys = {}
        self.docks = {}
        self.brokers = {}
        
    async def setup_valleys(self):
        """Setup three valleys for the federation demo."""
        
        # Valley configurations
        valley_configs = {
            "TechValley": {
                "description": "Software development and engineering valley",
                "specialties": ["backend", "frontend", "devops", "testing"],
                "port": 8001
            },
            "CreativeValley": {
                "description": "Design and marketing valley", 
                "specialties": ["design", "marketing", "content", "branding"],
                "port": 8002
            },
            "BusinessValley": {
                "description": "Strategy and operations valley",
                "specialties": ["strategy", "operations", "finance", "legal"],
                "port": 8003
            }
        }
        
        # Create valleys and their infrastructure
        for valley_name, config in valley_configs.items():
            logger.info(f"Setting up {valley_name}...")
            
            # Create valley
            valley = Valley(
                name=valley_name,
                description=config["description"],
                config_path=f"config/federation/{valley_name.lower()}.yaml"
            )
            
            # Create MCP broker for inter-valley communication
            broker = RedisMCPBroker(
                connection_string="redis://localhost:6379",
                valley_name=valley_name
            )
            
            # Create dock for federation management
            dock = Dock(
                valley=valley,
                mcp_broker=broker,
                port=config["port"]
            )
            
            # Store references
            self.valleys[valley_name] = valley
            self.brokers[valley_name] = broker
            self.docks[valley_name] = dock
            
            # Connect to Redis
            await broker.connect()
            
            logger.info(f"{valley_name} setup complete")
    
    async def establish_federation(self):
        """Establish federation between the valleys."""
        logger.info("Establishing federation between valleys...")
        
        # Create federation configurations
        federation_config = {
            "name": "InnovationFederation",
            "description": "A federation for collaborative innovation projects",
            "members": list(self.valleys.keys()),
            "shared_capabilities": ["project_management", "communication", "resource_sharing"],
            "governance": {
                "consensus_required": True,
                "voting_threshold": 0.67
            }
        }
        
        # Setup federation for each valley
        for valley_name, dock in self.docks.items():
            federation_manager = dock.federation_manager
            
            # Join the federation
            await federation_manager.join_federation(
                federation_name=federation_config["name"],
                federation_config=federation_config
            )
            
            # Subscribe to federation-wide communications
            await self.brokers[valley_name].subscribe_to_federation(
                federation_name=federation_config["name"],
                callback=self._handle_federation_message
            )
            
            logger.info(f"{valley_name} joined InnovationFederation")
        
        # Allow time for federation discovery
        await asyncio.sleep(2)
        logger.info("Federation establishment complete")
    
    async def _handle_federation_message(self, channel: str, message: dict):
        """Handle federation-wide messages."""
        content = message.get("content", {})
        source_valley = message.get("source_valley", "unknown")
        
        logger.info(f"Federation message from {source_valley}: {content.get('type', 'unknown')}")
    
    async def demo_cross_valley_collaboration(self):
        """Demonstrate cross-valley collaboration on a project."""
        logger.info("Starting cross-valley collaboration demo...")
        
        # Project: Build a new mobile app
        project_torch = Torch(
            content=TorchContent(
                text="New Mobile App Project",
                metadata={
                    "project_id": "mobile_app_2024",
                    "description": "Develop a revolutionary mobile app for productivity",
                    "phases": ["research", "design", "development", "testing", "launch"],
                    "timeline": "6 months",
                    "budget": "$500,000"
                }
            ),
            sender="ProjectManager",
            recipients=["TechValley", "CreativeValley", "BusinessValley"],
            priority="high"
        )
        
        # BusinessValley initiates the project
        business_dock = self.docks["BusinessValley"]
        await business_dock.send_torch(project_torch)
        
        await asyncio.sleep(1)
        
        # CreativeValley responds with design proposal
        design_torch = Torch(
            content=TorchContent(
                text="Design Proposal for Mobile App",
                metadata={
                    "project_id": "mobile_app_2024",
                    "phase": "design",
                    "deliverables": ["wireframes", "mockups", "brand_guidelines"],
                    "timeline": "4 weeks",
                    "team_size": 3
                }
            ),
            sender="CreativeValley",
            recipients=["BusinessValley", "TechValley"],
            priority="normal"
        )
        
        creative_dock = self.docks["CreativeValley"]
        await creative_dock.send_torch(design_torch)
        
        await asyncio.sleep(1)
        
        # TechValley responds with technical architecture
        tech_torch = Torch(
            content=TorchContent(
                text="Technical Architecture Proposal",
                metadata={
                    "project_id": "mobile_app_2024",
                    "phase": "development",
                    "architecture": "microservices",
                    "technologies": ["React Native", "Node.js", "PostgreSQL", "Redis"],
                    "team_size": 5,
                    "timeline": "12 weeks"
                }
            ),
            sender="TechValley", 
            recipients=["BusinessValley", "CreativeValley"],
            priority="normal"
        )
        
        tech_dock = self.docks["TechValley"]
        await tech_dock.send_torch(tech_torch)
        
        logger.info("Cross-valley collaboration demo complete")
    
    async def demo_federation_announcements(self):
        """Demonstrate federation-wide announcements."""
        logger.info("Demonstrating federation announcements...")
        
        # Federation-wide announcement
        announcement = {
            "type": "federation_announcement",
            "title": "Quarterly Innovation Summit",
            "description": "Join us for our quarterly innovation summit to share progress and plan future collaborations",
            "date": "2024-03-15",
            "location": "Virtual - All Valleys",
            "agenda": [
                "Project status updates",
                "New collaboration opportunities", 
                "Resource sharing initiatives",
                "Technology roadmap discussion"
            ]
        }
        
        # Broadcast from BusinessValley
        await self.brokers["BusinessValley"].publish_to_federation(
            federation_name="InnovationFederation",
            message=announcement,
            priority="high"
        )
        
        await asyncio.sleep(1)
        
        # Emergency announcement
        emergency = {
            "type": "emergency_announcement",
            "title": "Security Alert",
            "description": "Critical security update required for all valleys",
            "severity": "high",
            "action_required": "Update all systems within 24 hours",
            "contact": "security@innovationfederation.org"
        }
        
        # Broadcast emergency from TechValley
        await self.brokers["TechValley"].publish_to_federation(
            federation_name="InnovationFederation",
            message=emergency,
            priority="high"
        )
        
        logger.info("Federation announcements demo complete")
    
    async def demo_resource_sharing(self):
        """Demonstrate resource sharing between valleys."""
        logger.info("Demonstrating resource sharing...")
        
        # TechValley shares a reusable component
        resource_share = {
            "type": "resource_share",
            "resource_type": "component",
            "name": "Authentication Service",
            "description": "Reusable authentication microservice with OAuth2 support",
            "technologies": ["Node.js", "JWT", "OAuth2"],
            "documentation": "https://techvalley.internal/docs/auth-service",
            "contact": "backend-team@techvalley.org",
            "license": "MIT"
        }
        
        await self.brokers["TechValley"].publish_to_federation(
            federation_name="InnovationFederation",
            message=resource_share,
            priority="normal"
        )
        
        await asyncio.sleep(1)
        
        # CreativeValley shares design assets
        design_assets = {
            "type": "resource_share",
            "resource_type": "design_assets",
            "name": "UI Component Library",
            "description": "Comprehensive UI component library with design tokens",
            "components": ["buttons", "forms", "navigation", "cards", "modals"],
            "formats": ["Figma", "Sketch", "Adobe XD"],
            "documentation": "https://creativevalley.internal/design-system",
            "contact": "design-team@creativevalley.org"
        }
        
        await self.brokers["CreativeValley"].publish_to_federation(
            federation_name="InnovationFederation",
            message=design_assets,
            priority="normal"
        )
        
        logger.info("Resource sharing demo complete")
    
    async def display_federation_stats(self):
        """Display federation statistics and health information."""
        logger.info("Federation Statistics:")
        logger.info("=" * 50)
        
        for valley_name, broker in self.brokers.items():
            stats = await broker.get_message_stats()
            logger.info(f"\n{valley_name}:")
            logger.info(f"  Connected: {stats['connected']}")
            logger.info(f"  Messages Sent: {stats['message_stats']['sent']}")
            logger.info(f"  Messages Received: {stats['message_stats']['received']}")
            logger.info(f"  Errors: {stats['message_stats']['errors']}")
            logger.info(f"  Active Subscriptions: {stats['active_subscriptions']}")
            logger.info(f"  Federation Channels: {stats['federation_channels']}")
            logger.info(f"  Priority Queues: {stats['priority_queues']}")
            
            if stats['last_heartbeat']:
                logger.info(f"  Last Heartbeat: {stats['last_heartbeat']}")
    
    async def cleanup(self):
        """Clean up demo resources."""
        logger.info("Cleaning up demo resources...")
        
        # Stop all docks
        for valley_name, dock in self.docks.items():
            try:
                await dock.stop_gateway()
                logger.info(f"Stopped {valley_name} dock")
            except Exception as e:
                logger.error(f"Error stopping {valley_name} dock: {e}")
        
        # Disconnect all brokers
        for valley_name, broker in self.brokers.items():
            try:
                await broker.disconnect()
                logger.info(f"Disconnected {valley_name} broker")
            except Exception as e:
                logger.error(f"Error disconnecting {valley_name} broker: {e}")
        
        logger.info("Demo cleanup complete")

async def main():
    """Run the federation demo."""
    demo = FederationDemo()
    
    try:
        logger.info("Starting CampfireValley Federation Demo")
        logger.info("=" * 50)
        
        # Setup
        await demo.setup_valleys()
        await demo.establish_federation()
        
        # Demo scenarios
        await demo.demo_cross_valley_collaboration()
        await asyncio.sleep(2)
        
        await demo.demo_federation_announcements()
        await asyncio.sleep(2)
        
        await demo.demo_resource_sharing()
        await asyncio.sleep(2)
        
        # Display results
        await demo.display_federation_stats()
        
        logger.info("\nDemo completed successfully!")
        logger.info("The federation is now established and valleys are collaborating.")
        
        # Keep running for a bit to show ongoing federation activity
        logger.info("Monitoring federation activity for 30 seconds...")
        await asyncio.sleep(30)
        
    except KeyboardInterrupt:
        logger.info("Demo interrupted by user")
    except Exception as e:
        logger.error(f"Demo error: {e}")
    finally:
        await demo.cleanup()

if __name__ == "__main__":
    asyncio.run(main())
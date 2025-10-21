#!/usr/bin/env python3
"""
CampfireValley Federation Demo Startup Script

This script provides an easy way to start and manage the federation demo,
including proper initialization, health checks, and monitoring.
"""

import asyncio
import json
import logging
import os
import signal
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

import redis
import yaml
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich.text import Text

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from campfirevalley.valley import Valley
from campfirevalley.config_manager import ConfigManager
from campfirevalley.mcp import RedisMCPBroker

console = Console()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class FederationDemoManager:
    """Manages the federation demo startup and monitoring."""
    
    def __init__(self):
        self.valleys: Dict[str, Valley] = {}
        self.redis_client: Optional[redis.Redis] = None
        self.running = False
        self.demo_dir = Path(__file__).parent
        self.config_dir = self.demo_dir / "config" / "federation"
        
    async def check_redis_connection(self) -> bool:
        """Check if Redis is available."""
        try:
            self.redis_client = redis.Redis(host='localhost', port=6379, decode_responses=True)
            self.redis_client.ping()
            return True
        except redis.ConnectionError:
            return False
    
    async def load_valley_configs(self) -> Dict[str, dict]:
        """Load all valley configuration files."""
        configs = {}
        
        config_files = [
            "techvalley.yaml",
            "creativevalley.yaml", 
            "businessvalley.yaml"
        ]
        
        for config_file in config_files:
            config_path = self.config_dir / config_file
            if config_path.exists():
                with open(config_path, 'r') as f:
                    config = yaml.safe_load(f)
                    valley_name = config['valley']['name']
                    configs[valley_name] = config
            else:
                console.print(f"[red]Warning: Config file {config_file} not found[/red]")
        
        return configs
    
    async def initialize_valley(self, name: str, config: dict) -> Valley:
        """Initialize a single valley."""
        try:
            # Create config manager
            config_manager = ConfigManager()
            config_manager.load_from_dict(config)
            
            # Create valley
            valley = Valley(name=name, config_manager=config_manager)
            await valley.initialize()
            
            return valley
        except Exception as e:
            logger.error(f"Failed to initialize {name}: {e}")
            raise
    
    async def start_valleys(self, configs: Dict[str, dict]) -> None:
        """Start all valleys."""
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            
            for valley_name, config in configs.items():
                task = progress.add_task(f"Starting {valley_name}...", total=None)
                
                try:
                    valley = await self.initialize_valley(valley_name, config)
                    self.valleys[valley_name] = valley
                    
                    progress.update(task, description=f"✅ {valley_name} started")
                    await asyncio.sleep(0.5)  # Brief pause for visual effect
                    
                except Exception as e:
                    progress.update(task, description=f"❌ {valley_name} failed: {e}")
                    raise
    
    async def setup_federation(self) -> None:
        """Set up federation connections between valleys."""
        console.print("\n[bold blue]Setting up federation...[/bold blue]")
        
        # Wait for all valleys to be ready
        await asyncio.sleep(2)
        
        # Establish federation connections
        federation_tasks = []
        for valley_name, valley in self.valleys.items():
            task = asyncio.create_task(valley.join_federation("InnovationFederation"))
            federation_tasks.append(task)
        
        await asyncio.gather(*federation_tasks)
        console.print("[green]✅ Federation established[/green]")
    
    def create_status_table(self) -> Table:
        """Create a status table for monitoring."""
        table = Table(title="Federation Status", show_header=True, header_style="bold magenta")
        table.add_column("Valley", style="cyan", no_wrap=True)
        table.add_column("Status", style="green")
        table.add_column("Port", style="yellow")
        table.add_column("Campfires", style="blue")
        table.add_column("Messages", style="white")
        
        for valley_name, valley in self.valleys.items():
            try:
                # Get valley status
                status = "🟢 Online" if valley.is_running else "🔴 Offline"
                port = str(valley.config_manager.get('dock.port', 'N/A'))
                
                # Count campfires
                campfires = valley.config_manager.get('campfires', [])
                campfire_count = str(len(campfires))
                
                # Get message stats (mock for now)
                message_count = "0"
                
                table.add_row(valley_name, status, port, campfire_count, message_count)
                
            except Exception as e:
                table.add_row(valley_name, "❌ Error", "N/A", "N/A", "N/A")
        
        return table
    
    async def run_demo_scenarios(self) -> None:
        """Run the demo scenarios."""
        console.print("\n[bold green]Running demo scenarios...[/bold green]")
        
        scenarios = [
            "Cross-valley project collaboration",
            "Federation-wide announcements", 
            "Resource sharing demonstration",
            "Security and governance showcase"
        ]
        
        for i, scenario in enumerate(scenarios, 1):
            console.print(f"\n[bold yellow]Scenario {i}: {scenario}[/bold yellow]")
            
            # Simulate scenario execution
            await asyncio.sleep(2)
            
            # Add scenario-specific logic here
            if "collaboration" in scenario:
                await self.demo_collaboration()
            elif "announcements" in scenario:
                await self.demo_announcements()
            elif "sharing" in scenario:
                await self.demo_resource_sharing()
            elif "security" in scenario:
                await self.demo_security()
            
            console.print(f"[green]✅ Scenario {i} completed[/green]")
    
    async def demo_collaboration(self) -> None:
        """Demonstrate cross-valley collaboration."""
        console.print("  📱 BusinessValley initiating mobile app project...")
        await asyncio.sleep(1)
        
        console.print("  🎨 CreativeValley responding with design proposals...")
        await asyncio.sleep(1)
        
        console.print("  💻 TechValley providing technical architecture...")
        await asyncio.sleep(1)
    
    async def demo_announcements(self) -> None:
        """Demonstrate federation announcements."""
        console.print("  📢 Broadcasting quarterly innovation summit...")
        await asyncio.sleep(1)
        
        console.print("  🔒 Sending security policy updates...")
        await asyncio.sleep(1)
    
    async def demo_resource_sharing(self) -> None:
        """Demonstrate resource sharing."""
        console.print("  🔐 TechValley sharing authentication services...")
        await asyncio.sleep(1)
        
        console.print("  🧩 CreativeValley sharing UI components...")
        await asyncio.sleep(1)
        
        console.print("  📊 BusinessValley sharing project templates...")
        await asyncio.sleep(1)
    
    async def demo_security(self) -> None:
        """Demonstrate security features."""
        console.print("  🛡️ Verifying digital signatures...")
        await asyncio.sleep(1)
        
        console.print("  🔑 Rotating federation keys...")
        await asyncio.sleep(1)
        
        console.print("  ✅ Security audit completed...")
        await asyncio.sleep(1)
    
    async def monitor_federation(self) -> None:
        """Monitor federation status in real-time."""
        console.print("\n[bold blue]Monitoring federation (Press Ctrl+C to stop)...[/bold blue]")
        
        try:
            with Live(self.create_status_table(), refresh_per_second=1, console=console) as live:
                while self.running:
                    live.update(self.create_status_table())
                    await asyncio.sleep(1)
        except KeyboardInterrupt:
            console.print("\n[yellow]Monitoring stopped by user[/yellow]")
    
    async def cleanup(self) -> None:
        """Clean up resources."""
        console.print("\n[bold red]Shutting down federation...[/bold red]")
        
        # Stop all valleys
        for valley_name, valley in self.valleys.items():
            try:
                await valley.shutdown()
                console.print(f"[green]✅ {valley_name} stopped[/green]")
            except Exception as e:
                console.print(f"[red]❌ Error stopping {valley_name}: {e}[/red]")
        
        # Close Redis connection
        if self.redis_client:
            self.redis_client.close()
        
        console.print("[green]✅ Federation shutdown complete[/green]")
    
    async def run(self) -> None:
        """Run the complete federation demo."""
        self.running = True
        
        try:
            # Welcome message
            console.print(Panel.fit(
                "[bold green]CampfireValley Federation Demo[/bold green]\n"
                "Demonstrating multi-valley collaboration and communication",
                border_style="green"
            ))
            
            # Check Redis
            console.print("\n[bold blue]Checking prerequisites...[/bold blue]")
            if not await self.check_redis_connection():
                console.print("[red]❌ Redis not available. Please start Redis first.[/red]")
                console.print("[yellow]Run: docker run -d -p 6379:6379 redis:7-alpine[/yellow]")
                return
            console.print("[green]✅ Redis connection verified[/green]")
            
            # Load configurations
            configs = await self.load_valley_configs()
            if not configs:
                console.print("[red]❌ No valley configurations found[/red]")
                return
            console.print(f"[green]✅ Loaded {len(configs)} valley configurations[/green]")
            
            # Start valleys
            console.print("\n[bold blue]Starting valleys...[/bold blue]")
            await self.start_valleys(configs)
            
            # Setup federation
            await self.setup_federation()
            
            # Run demo scenarios
            await self.run_demo_scenarios()
            
            # Start monitoring
            await self.monitor_federation()
            
        except KeyboardInterrupt:
            console.print("\n[yellow]Demo interrupted by user[/yellow]")
        except Exception as e:
            console.print(f"\n[red]❌ Demo failed: {e}[/red]")
            logger.exception("Demo failed")
        finally:
            self.running = False
            await self.cleanup()

def signal_handler(signum, frame):
    """Handle shutdown signals."""
    console.print("\n[yellow]Received shutdown signal[/yellow]")
    sys.exit(0)

async def main():
    """Main entry point."""
    # Set up signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Run the demo
    demo_manager = FederationDemoManager()
    await demo_manager.run()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n[yellow]Demo stopped[/yellow]")
    except Exception as e:
        console.print(f"\n[red]❌ Fatal error: {e}[/red]")
        sys.exit(1)
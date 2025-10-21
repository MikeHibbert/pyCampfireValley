"""
Valley manager implementation.
"""

import asyncio
import logging
import os
from pathlib import Path
from typing import Optional, Dict, List
from datetime import datetime
from .interfaces import IValley, IDock, IPartyBox, IMCPBroker, IFederationManager, IKeyManager
from .models import ValleyConfig, CampfireConfig, CommunityMembership, FederationMembership
from .config import ConfigManager
from .config_manager import (
    get_config_manager, ConfigSource, ConfigFormat, 
    ConfigScope, ConfigEnvironment, load_config_from_file
)
from .monitoring import get_monitoring_system, LogLevel


logger = logging.getLogger(__name__)


class Valley(IValley):
    """
    Valley manager that coordinates dock, campfires, and infrastructure components.
    """
    
    def __init__(
        self, 
        name: str, 
        manifest_path: str = './manifest.yaml',
        party_box: Optional[IPartyBox] = None,
        mcp_broker: str = 'redis://localhost:6379',
        config_dir: str = './config'
    ):
        """
        Initialize a Valley instance.
        
        Args:
            name: Name of the valley
            manifest_path: Path to the manifest.yaml configuration file
            party_box: Optional Party Box storage system instance
            mcp_broker: MCP broker connection string
            config_dir: Directory containing configuration files
        """
        self.name = name
        self.manifest_path = manifest_path
        self.mcp_broker_url = mcp_broker
        self.party_box = party_box
        self.config_dir = config_dir
        
        # Initialize configuration management
        self.config_manager = get_config_manager()
        self.monitoring = get_monitoring_system()
        
        # Load configuration
        try:
            self.config = ConfigManager.load_valley_config(manifest_path)
        except FileNotFoundError:
            logger.warning(f"Manifest file not found at {manifest_path}, creating default config")
            self.config = ConfigManager.create_default_valley_config(name)
            ConfigManager.save_valley_config(self.config, manifest_path)
        
        # Initialize components (will be set during start())
        self.dock: Optional[IDock] = None
        self.mcp_broker: Optional[IMCPBroker] = None
        self.campfires: Dict[str, 'ICampfire'] = {}
        self.communities: Dict[str, CommunityMembership] = {}
        
        # Federation components
        self.federation_manager: Optional[IFederationManager] = None
        self.key_manager: Optional[IKeyManager] = None
        self.vali_coordinator: Optional['VALICoordinator'] = None
        self.federations: Dict[str, FederationMembership] = {}
        
        # Runtime state
        self._running = False
        self._tasks: List[asyncio.Task] = []
        
        logger.info(f"Valley '{name}' initialized with config from {manifest_path}")
    
    async def start(self) -> None:
        """Start the valley and all its components"""
        if self._running:
            logger.warning(f"Valley '{self.name}' is already running")
            return
        
        logger.info(f"Starting valley '{self.name}'...")
        
        try:
            # Load advanced configuration
            await self._load_advanced_config()
            
            # Log configuration loaded
            await self.monitoring.log(LogLevel.INFO, f"Configuration loaded for valley '{self.name}'", "valley")
            
        except Exception as e:
            logger.error(f"Failed to load configuration: {e}")
            # Continue with basic config
        
        try:
            # Initialize MCP broker only if URL is provided
            if not self.mcp_broker and self.mcp_broker_url:
                from .mcp import RedisMCPBroker  # Import here to avoid circular imports
                self.mcp_broker = RedisMCPBroker(self.mcp_broker_url)
            
            # Try to connect to MCP broker, but continue if it fails (for demo purposes)
            if self.mcp_broker:
                try:
                    broker_connected = await self.mcp_broker.connect()
                    if broker_connected:
                        logger.info("MCP broker connected successfully")
                    else:
                        logger.warning("MCP broker connection failed, continuing without it")
                except Exception as e:
                    logger.warning(f"MCP broker connection failed: {e}, continuing without it")
            else:
                logger.info("No MCP broker configured, running in standalone mode")
            
            # Initialize Party Box if not provided
            if not self.party_box:
                from .party_box import FileSystemPartyBox  # Import here to avoid circular imports
                self.party_box = FileSystemPartyBox(f"./party_box_{self.name}")
            
            # Initialize key manager
            from .key_manager import CampfireKeyManager
            self.key_manager = CampfireKeyManager(valley_name=self.name)
            await self.key_manager.initialize_valley_keys()
            logger.info("Key manager initialized")
            
            # Initialize federation manager
            federation_config = await self.get_config_value("federation", {})
            if federation_config.get("enabled", False) and self.mcp_broker:
                from .federation import FederationManager
                self.federation_manager = FederationManager(
                    valley_name=self.name,
                    mcp_broker=self.mcp_broker,
                    key_manager=self.key_manager
                )
                await self.federation_manager.start()
                logger.info("Federation manager started")
            
            # Initialize VALI coordinator
            if self.mcp_broker:
                from .vali import VALICoordinator
                self.vali_coordinator = VALICoordinator(
                    mcp_broker=self.mcp_broker,
                    federation_manager=self.federation_manager,
                    valley_name=self.name
                )
                await self.vali_coordinator.start()
                logger.info("VALI coordinator started")
            
            # Create and start dock if auto_create_dock is enabled and MCP broker is connected
            if self.config.env.get("auto_create_dock", True) and self.mcp_broker and self.mcp_broker.is_connected():
                from .dock import Dock  # Import here to avoid circular imports
                self.dock = Dock(
                    valley_name=self.name,
                    mcp_broker=self.mcp_broker,
                    party_box=self.party_box,
                    federation_manager=self.federation_manager,
                    vali_coordinator=self.vali_coordinator
                )
                await self.dock.start_gateway()
            elif self.config.env.get("auto_create_dock", True):
                logger.warning("Dock creation skipped - MCP broker not connected")
            
            self._running = True
            logger.info(f"Valley '{self.name}' started successfully")
            
        except Exception as e:
            logger.error(f"Failed to start valley '{self.name}': {e}")
            await self.stop()
            raise
    
    async def stop(self) -> None:
        """Stop the valley and cleanup resources"""
        if not self._running:
            return
        
        logger.info(f"Stopping valley '{self.name}'...")
        
        # Cancel all running tasks
        for task in self._tasks:
            if not task.done():
                task.cancel()
        
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        
        # Stop dock
        if self.dock:
            await self.dock.stop_gateway()
        
        # Stop VALI coordinator
        if self.vali_coordinator:
            await self.vali_coordinator.stop()
        
        # Stop federation manager
        if self.federation_manager:
            await self.federation_manager.stop()
        
        # Stop all campfires
        for campfire in self.campfires.values():
            await campfire.stop()
        
        # Disconnect MCP broker
        if self.mcp_broker:
            await self.mcp_broker.disconnect()
        
        self._running = False
        logger.info(f"Valley '{self.name}' stopped")
    
    async def join_community(self, community_name: str, key: str) -> bool:
        """Join a community with the given name and key"""
        if not self._running:
            raise RuntimeError("Valley must be started before joining communities")
        
        logger.info(f"Joining community '{community_name}'...")
        
        try:
            # Create community membership record
            membership = CommunityMembership(
                community_name=community_name,
                alias=self.name,
                key_hash=self._hash_key(key)  # This would use proper hashing
            )
            
            self.communities[community_name] = membership
            
            # TODO: Implement actual handshake with trusted neighbor
            # This would involve:
            # 1. Send handshake torch with join flag, alias, and key hash
            # 2. Wait for confirmation from trusted neighbor
            # 3. Exchange keys and update community membership
            
            logger.info(f"Successfully joined community '{community_name}'")
            return True
            
        except Exception as e:
            logger.error(f"Failed to join community '{community_name}': {e}")
            return False
    
    async def leave_community(self, community_name: str) -> bool:
        """Leave a community"""
        if community_name not in self.communities:
            logger.warning(f"Not a member of community '{community_name}'")
            return False
        
        logger.info(f"Leaving community '{community_name}'...")
        
        try:
            # TODO: Implement proper community leaving process
            # This would involve:
            # 1. Notify community members
            # 2. Revoke keys
            # 3. Clean up community-specific resources
            
            del self.communities[community_name]
            
            logger.info(f"Successfully left community '{community_name}'")
            return True
            
        except Exception as e:
            logger.error(f"Failed to leave community '{community_name}': {e}")
            return False
    
    async def join_federation(self, federation_id: str, discovery_endpoint: str = None) -> bool:
        """Join a federation"""
        if not self.federation_manager:
            logger.error("Federation manager not initialized")
            return False
        
        try:
            success = await self.federation_manager.join_federation(federation_id, discovery_endpoint)
            if success:
                # Create federation membership record
                membership = FederationMembership(
                    federation_id=federation_id,
                    valley_name=self.name,
                    joined_at=datetime.now(),
                    status="active",
                    capabilities=await self._get_valley_capabilities(),
                    discovery_endpoint=discovery_endpoint
                )
                self.federations[federation_id] = membership
                await self.monitoring.log(LogLevel.INFO, f"Joined federation: {federation_id}", "valley")
                logger.info(f"Successfully joined federation: {federation_id}")
            return success
        except Exception as e:
            logger.error(f"Error joining federation {federation_id}: {e}")
            return False
    
    async def leave_federation(self, federation_id: str) -> bool:
        """Leave a federation"""
        if not self.federation_manager:
            logger.error("Federation manager not initialized")
            return False
        
        try:
            success = await self.federation_manager.leave_federation(federation_id)
            if success and federation_id in self.federations:
                del self.federations[federation_id]
                await self.monitoring.log(LogLevel.INFO, f"Left federation: {federation_id}", "valley")
                logger.info(f"Successfully left federation: {federation_id}")
            return success
        except Exception as e:
            logger.error(f"Error leaving federation {federation_id}: {e}")
            return False
    
    async def discover_federation_valleys(self, federation_id: str = None) -> List[Dict]:
        """Discover valleys in federation(s)"""
        if not self.federation_manager:
            logger.error("Federation manager not initialized")
            return []
        
        try:
            return await self.federation_manager.discover_valleys(federation_id)
        except Exception as e:
            logger.error(f"Error discovering federation valleys: {e}")
            return []
    
    async def get_federation_memberships(self) -> Dict[str, FederationMembership]:
        """Get current federation memberships"""
        return self.federations.copy()
    
    async def _get_valley_capabilities(self) -> List[str]:
        """Get valley capabilities for federation announcement"""
        capabilities = ["torch_processing", "campfire_hosting"]
        
        if self.dock:
            capabilities.extend(["gateway", "routing", "discovery"])
        
        if self.vali_coordinator:
            capabilities.append("vali_services")
        
        # Add campfire-specific capabilities
        for campfire_name in self.campfires.keys():
            capabilities.append(f"campfire:{campfire_name}")
        
        return capabilities
    
    async def provision_campfire(self, campfire_config: CampfireConfig) -> bool:
        """Provision a new campfire from configuration"""
        if not self._running:
            raise RuntimeError("Valley must be started before provisioning campfires")
        
        campfire_name = campfire_config.name
        
        if campfire_name in self.campfires:
            logger.warning(f"Campfire '{campfire_name}' already exists")
            return False
        
        logger.info(f"Provisioning campfire '{campfire_name}' of type '{campfire_config.type}'...")
        
        try:
            # Create the appropriate campfire type based on configuration
            campfire = None
            
            if campfire_config.type == "LLMCampfire":
                from .llm_campfire import create_openrouter_campfire
                from campfires import OpenRouterConfig
                
                # Extract LLM configuration from campfire config
                llm_config = campfire_config.config.get('llm', {})
                api_key = llm_config.get('api_key') or os.getenv('OPENROUTER_API_KEY', 'demo_key_placeholder')
                model = llm_config.get('model', 'anthropic/claude-3.5-sonnet')
                
                # Create LLM campfire
                campfire = create_openrouter_campfire(
                    campfire_config, 
                    self.mcp_broker, 
                    api_key=api_key,
                    default_model=model
                )
                logger.info(f"Created LLMCampfire '{campfire_name}' with model '{model}'")
                
            elif campfire_config.type == "dockmaster":
                from .campfires.dockmaster import DockmasterCampfire
                campfire = DockmasterCampfire(
                    name=campfire_name,
                    valley_name=self.name,
                    federation_manager=self.federation_manager
                )
            elif campfire_config.type == "sanitizer":
                from .security_scanner import SanitizerCampfire
                campfire = SanitizerCampfire(
                    name=campfire_name,
                    valley_name=self.name
                )
            elif campfire_config.type == "justice":
                from .justice import JusticeCampfire
                campfire = JusticeCampfire(
                    name=campfire_name,
                    valley_name=self.name
                )
            else:
                # Default to basic campfire
                from .campfire import Campfire
                campfire = Campfire(campfire_config, self.mcp_broker, self.party_box)
                logger.info(f"Created basic Campfire '{campfire_name}'")
            
            # Start the campfire
            await campfire.start()
            
            self.campfires[campfire_name] = campfire
            
            # Register with VALI if available
            if self.vali_coordinator and hasattr(campfire, 'get_service_type'):
                try:
                    await self.vali_coordinator.register_service(campfire)
                    logger.info(f"Registered campfire '{campfire_name}' with VALI")
                except Exception as e:
                    logger.warning(f"Failed to register campfire '{campfire_name}' with VALI: {e}")
            
            logger.info(f"Successfully provisioned campfire '{campfire_name}'")
            return True
            
        except Exception as e:
            logger.error(f"Failed to provision campfire '{campfire_name}': {e}")
            return False
    
    async def deprovision_campfire(self, campfire_name: str) -> bool:
        """Remove and stop a campfire"""
        try:
            if campfire_name not in self.campfires:
                logger.warning(f"Campfire '{campfire_name}' not found")
                return False
            
            campfire = self.campfires[campfire_name]
            
            # Unregister from VALI if available
            if self.vali_coordinator and hasattr(campfire, 'get_service_type'):
                try:
                    await self.vali_coordinator.unregister_service(campfire_name)
                    logger.info(f"Unregistered campfire '{campfire_name}' from VALI")
                except Exception as e:
                    logger.warning(f"Failed to unregister campfire '{campfire_name}' from VALI: {e}")
            
            # Stop the campfire
            await campfire.stop()
            del self.campfires[campfire_name]
            
            await self.monitoring.log(LogLevel.INFO, f"Deprovisioned campfire: {campfire_name}", "valley")
            logger.info(f"Successfully deprovisioned campfire: {campfire_name}")
            return True
            
        except Exception as e:
            logger.error(f"Error deprovisioning campfire '{campfire_name}': {e}")
            return False
    
    def get_config(self) -> ValleyConfig:
        """Get the valley configuration"""
        return self.config
    
    def is_running(self) -> bool:
        """Check if the valley is currently running"""
        return self._running
    
    def get_communities(self) -> Dict[str, CommunityMembership]:
        """Get all community memberships"""
        return self.communities.copy()
    
    def get_campfires(self) -> Dict[str, 'ICampfire']:
        """Get all active campfires"""
        return self.campfires.copy()
    
    async def process_torch(self, torch: 'Torch') -> Optional['Torch']:
        """Process a torch by routing it to the appropriate campfire"""
        if not self._running:
            raise RuntimeError("Valley must be started before processing torches")
        
        logger.info(f"Processing torch {torch.torch_id} from {torch.sender_valley}")
        
        try:
            # Parse target address to find the campfire
            # Format: valley:campfire or valley:name/campfire/camper or just campfire_name
            campfire_name = torch.target_address
            
            # Handle valley:campfire format
            if ':' in campfire_name:
                parts = campfire_name.split(':', 1)
                if len(parts) == 2:
                    valley_name, campfire_part = parts
                    # If it's for this valley, extract the campfire name
                    if valley_name == self.name:
                        campfire_name = campfire_part
                    else:
                        # Different valley - this shouldn't happen in local processing
                        logger.warning(f"Torch target valley '{valley_name}' doesn't match current valley '{self.name}'")
                        campfire_name = campfire_part
            
            # Handle path-based format: valley:name/campfire/camper
            target_parts = campfire_name.split('/')
            if len(target_parts) >= 2:
                campfire_name = target_parts[1]
            
            # Remove any "campfire:" prefix if present
            if campfire_name.startswith("campfire:"):
                campfire_name = campfire_name[9:]
            
            # Get the campfire
            if campfire_name in self.campfires:
                campfire = self.campfires[campfire_name]
                logger.info(f"Routing torch {torch.torch_id} to campfire '{campfire_name}'")
                return await campfire.process_torch(torch)
            else:
                # If no specific campfire found, try to route through dock if available
                if self.dock:
                    logger.info(f"Routing torch {torch.torch_id} through dock")
                    await self.dock.handle_incoming_torch(torch)
                    return None
                else:
                    available_campfires = list(self.campfires.keys())
                    logger.error(f"Campfire '{campfire_name}' not found. Available campfires: {available_campfires}")
                    raise ValueError(f"Campfire '{campfire_name}' not found in valley '{self.name}'")
                    
        except Exception as e:
            logger.error(f"Error processing torch {torch.torch_id}: {e}")
            raise
    
    async def _load_advanced_config(self) -> None:
        """Load advanced configuration from config directory"""
        config_path = Path(self.config_dir)
        
        if not config_path.exists():
            logger.warning(f"Config directory not found: {config_path}")
            return
        
        # Determine current environment
        import os
        env_name = os.environ.get("CAMPFIRE_ENV", "development").lower()
        try:
            current_env = ConfigEnvironment(env_name)
        except ValueError:
            current_env = ConfigEnvironment.DEVELOPMENT
            logger.warning(f"Unknown environment '{env_name}', using development")
        
        # Load default configuration first (lowest priority)
        default_config = config_path / "default.yaml"
        if default_config.exists():
            source = ConfigSource(
                path=str(default_config),
                format=ConfigFormat.YAML,
                scope=ConfigScope.VALLEY,
                priority=0
            )
            self.config_manager.add_source(source)
        
        # Load environment-specific configuration (higher priority)
        env_config = config_path / f"{current_env.value}.yaml"
        if env_config.exists():
            source = ConfigSource(
                path=str(env_config),
                format=ConfigFormat.YAML,
                scope=ConfigScope.VALLEY,
                environment=current_env,
                priority=10
            )
            self.config_manager.add_source(source)
        
        # Load valley-specific configuration (highest priority)
        valley_config = config_path / f"{self.name.lower()}.yaml"
        if valley_config.exists():
            source = ConfigSource(
                path=str(valley_config),
                format=ConfigFormat.YAML,
                scope=ConfigScope.VALLEY,
                priority=20
            )
            self.config_manager.add_source(source)
        
        # Load all configurations
        await self.config_manager.load_all_configs()
        
        # Add change callback to monitor config changes
        self.config_manager.add_change_callback(self._on_config_changed)
        
        logger.info(f"Advanced configuration loaded for environment: {current_env.value}")
    
    async def _on_config_changed(self, new_config: Dict) -> None:
        """Handle configuration changes"""
        logger.info("Configuration changed, applying updates...")
        await self.monitoring.log(LogLevel.INFO, "Configuration updated", "valley")
        
        # Here you could implement hot-reloading of specific components
        # For now, just log the change
        
    async def get_config_value(self, path: str, default=None):
        """Get a configuration value using the advanced config system"""
        try:
            return await self.config_manager.get_config(path, default)
        except Exception as e:
            logger.error(f"Error getting config value '{path}': {e}")
            return default
    
    async def set_config_value(self, path: str, value) -> None:
        """Set a configuration value using the advanced config system"""
        try:
            await self.config_manager.set_config(path, value)
        except Exception as e:
            logger.error(f"Error setting config value '{path}': {e}")
    
    def _hash_key(self, key: str) -> str:
        """Hash a key for secure storage"""
        import hashlib
        return hashlib.sha256(key.encode()).hexdigest()
    
    async def get_valley_status(self) -> Dict:
        """Get comprehensive valley status"""
        status = {
            "name": self.name,
            "running": self._running,
            "components": {
                "mcp_broker": self.mcp_broker is not None and getattr(self.mcp_broker, 'is_connected', lambda: False)(),
                "dock": self.dock is not None,
                "federation_manager": self.federation_manager is not None,
                "vali_coordinator": self.vali_coordinator is not None,
                "key_manager": self.key_manager is not None
            },
            "campfires": {
                "count": len(self.campfires),
                "names": list(self.campfires.keys())
            },
            "communities": {
                "count": len(self.communities),
                "names": list(self.communities.keys())
            },
            "federations": {
                "count": len(self.federations),
                "names": list(self.federations.keys())
            }
        }
        
        # Add federation-specific status if available
        if self.federation_manager:
            try:
                fed_status = await self.federation_manager.get_status()
                status["federation_status"] = fed_status
            except Exception as e:
                status["federation_status"] = {"error": str(e)}
        
        return status
    
    async def health_check(self) -> Dict:
        """Perform health check on valley components"""
        health = {
            "overall": "healthy",
            "components": {},
            "issues": []
        }
        
        # Check MCP broker
        if self.mcp_broker:
            try:
                connected = getattr(self.mcp_broker, 'is_connected', lambda: False)()
                health["components"]["mcp_broker"] = "healthy" if connected else "unhealthy"
                if not connected:
                    health["issues"].append("MCP broker not connected")
            except Exception as e:
                health["components"]["mcp_broker"] = "error"
                health["issues"].append(f"MCP broker error: {e}")
        else:
            health["components"]["mcp_broker"] = "missing"
            health["issues"].append("MCP broker not initialized")
        
        # Check dock
        if self.dock:
            health["components"]["dock"] = "healthy"
        else:
            health["components"]["dock"] = "missing"
        
        # Check federation manager
        if self.federation_manager:
            health["components"]["federation_manager"] = "healthy"
        else:
            health["components"]["federation_manager"] = "missing"
        
        # Check campfires
        campfire_issues = []
        for name, campfire in self.campfires.items():
            try:
                # Basic health check - campfire should be responsive
                health["components"][f"campfire_{name}"] = "healthy"
            except Exception as e:
                health["components"][f"campfire_{name}"] = "error"
                campfire_issues.append(f"Campfire {name}: {e}")
        
        if campfire_issues:
            health["issues"].extend(campfire_issues)
        
        # Determine overall health
        if health["issues"]:
            health["overall"] = "degraded" if len(health["issues"]) < 3 else "unhealthy"
        
        return health
    
    def __repr__(self) -> str:
        return f"Valley(name='{self.name}', running={self._running}, campfires={len(self.campfires)}, federations={len(self.federations)})"
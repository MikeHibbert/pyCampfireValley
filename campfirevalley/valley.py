"""
Valley manager implementation.
"""

import asyncio
import logging
import os
from pathlib import Path
from typing import Optional, Dict, List
from .interfaces import IValley, IDock, IPartyBox, IMCPBroker
from .models import ValleyConfig, CampfireConfig, CommunityMembership
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
            # Initialize MCP broker
            if not self.mcp_broker:
                from .mcp import RedisMCPBroker  # Import here to avoid circular imports
                self.mcp_broker = RedisMCPBroker(self.mcp_broker_url)
            
            # Try to connect to MCP broker, but continue if it fails (for demo purposes)
            try:
                broker_connected = await self.mcp_broker.connect()
                if broker_connected:
                    logger.info("MCP broker connected successfully")
                else:
                    logger.warning("MCP broker connection failed, continuing without it")
            except Exception as e:
                logger.warning(f"MCP broker connection failed: {e}, continuing without it")
            
            # Initialize Party Box if not provided
            if not self.party_box:
                from .party_box import FileSystemPartyBox  # Import here to avoid circular imports
                self.party_box = FileSystemPartyBox(f"./party_box_{self.name}")
            
            # Create and start dock if auto_create_dock is enabled and MCP broker is connected
            if self.config.env.get("auto_create_dock", True) and self.mcp_broker.is_connected():
                from .dock import Dock  # Import here to avoid circular imports
                self.dock = Dock(self, self.mcp_broker, self.party_box)
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
                
            else:
                # Default to basic campfire
                from .campfire import Campfire
                campfire = Campfire(campfire_config, self.mcp_broker, self.party_box)
                logger.info(f"Created basic Campfire '{campfire_name}'")
            
            # Start the campfire
            await campfire.start()
            
            self.campfires[campfire_name] = campfire
            
            logger.info(f"Successfully provisioned campfire '{campfire_name}'")
            return True
            
        except Exception as e:
            logger.error(f"Failed to provision campfire '{campfire_name}': {e}")
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
    
    def __repr__(self) -> str:
        return f"Valley(name='{self.name}', running={self._running}, campfires={len(self.campfires)})"
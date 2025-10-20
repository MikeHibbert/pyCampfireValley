"""
Valley manager implementation.
"""

import asyncio
import logging
from pathlib import Path
from typing import Optional, Dict, List
from .interfaces import IValley, IDock, IPartyBox, IMCPBroker
from .models import ValleyConfig, CampfireConfig, CommunityMembership
from .config import ConfigManager


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
        mcp_broker: str = 'redis://localhost:6379'
    ):
        """
        Initialize a Valley instance.
        
        Args:
            name: Name of the valley
            manifest_path: Path to the manifest.yaml configuration file
            party_box: Optional Party Box storage system instance
            mcp_broker: MCP broker connection string
        """
        self.name = name
        self.manifest_path = manifest_path
        self.mcp_broker_url = mcp_broker
        self.party_box = party_box
        
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
            # Initialize MCP broker
            if not self.mcp_broker:
                from .mcp import RedisMCPBroker  # Import here to avoid circular imports
                self.mcp_broker = RedisMCPBroker(self.mcp_broker_url)
            
            await self.mcp_broker.connect()
            
            # Initialize Party Box if not provided
            if not self.party_box:
                from .party_box import FileSystemPartyBox  # Import here to avoid circular imports
                self.party_box = FileSystemPartyBox(f"./party_box_{self.name}")
            
            # Create and start dock if auto_create_dock is enabled
            if self.config.env.get("auto_create_dock", True):
                from .dock import Dock  # Import here to avoid circular imports
                self.dock = Dock(self, self.mcp_broker, self.party_box)
                await self.dock.start_gateway()
            
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
        
        logger.info(f"Provisioning campfire '{campfire_name}'...")
        
        try:
            # TODO: Implement campfire provisioning
            # This would involve:
            # 1. Validate configuration through Sanitizer
            # 2. Check permissions through Justice
            # 3. Create Campfire instance
            # 4. Wire MCP channels
            # 5. Start the campfire
            
            from .campfire import Campfire  # Import here to avoid circular imports
            campfire = Campfire(campfire_config, self.mcp_broker)
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
    
    def _hash_key(self, key: str) -> str:
        """Hash a key for storage (placeholder implementation)"""
        import hashlib
        return hashlib.sha256(key.encode()).hexdigest()
    
    def __repr__(self) -> str:
        return f"Valley(name='{self.name}', running={self._running}, campfires={len(self.campfires)})"
"""
Dock gateway implementation for inter-valley communication.
"""

import asyncio
import logging
from typing import Optional, Dict, Any
from .interfaces import IDock, IValley, IMCPBroker, IPartyBox
from .models import Torch, DockMode


logger = logging.getLogger(__name__)


class Dock(IDock):
    """
    Dock gateway that manages inter-valley communication through MCP channels.
    """
    
    def __init__(self, valley: IValley, mcp_broker: IMCPBroker, party_box: IPartyBox):
        """
        Initialize a Dock instance.
        
        Args:
            valley: The valley this dock belongs to
            mcp_broker: MCP broker for communication
            party_box: Party Box for attachment storage
        """
        self.valley = valley
        self.mcp_broker = mcp_broker
        self.party_box = party_box
        
        # Runtime state
        self._running = False
        self._subscriptions: Dict[str, Any] = {}
        
        # Get dock configuration from valley config
        valley_config = valley.get_config()
        self.dock_mode = DockMode(valley_config.env.get("dock_mode", "private"))
        
        logger.info(f"Dock initialized for valley '{valley_config.name}' in {self.dock_mode} mode")
    
    async def start_gateway(self) -> None:
        """Start the dock gateway"""
        if self._running:
            logger.warning("Dock gateway is already running")
            return
        
        logger.info("Starting dock gateway...")
        
        try:
            # Subscribe to dock channels
            await self._subscribe_to_channels()
            
            # Start discovery broadcasts if in public mode
            if self.dock_mode == DockMode.PUBLIC:
                asyncio.create_task(self._discovery_loop())
            
            self._running = True
            logger.info("Dock gateway started successfully")
            
        except Exception as e:
            logger.error(f"Failed to start dock gateway: {e}")
            raise
    
    async def stop_gateway(self) -> None:
        """Stop the dock gateway"""
        if not self._running:
            return
        
        logger.info("Stopping dock gateway...")
        
        # Unsubscribe from all channels
        for channel in list(self._subscriptions.keys()):
            await self.mcp_broker.unsubscribe(channel)
        
        self._subscriptions.clear()
        self._running = False
        
        logger.info("Dock gateway stopped")
    
    async def handle_incoming_torch(self, torch: Torch) -> None:
        """Handle an incoming torch from another valley"""
        logger.debug(f"Handling incoming torch {torch.id} from {torch.sender_valley}")
        
        try:
            # Validate sender
            if not await self.validate_sender(torch):
                logger.warning(f"Invalid sender for torch {torch.id}")
                return
            
            # Store torch payload in Party Box if it has attachments
            if torch.attachments:
                for attachment_id in torch.attachments:
                    # TODO: Retrieve attachment content from sender
                    # This is a placeholder - actual implementation would fetch from sender
                    pass
            
            # Route torch to appropriate campfire based on target address
            await self._route_torch(torch)
            
        except Exception as e:
            logger.error(f"Error handling incoming torch {torch.id}: {e}")
    
    async def send_torch(self, target_address: str, torch: Torch) -> bool:
        """Send a torch to the specified target address"""
        if not self._running:
            raise RuntimeError("Dock gateway must be started before sending torches")
        
        logger.debug(f"Sending torch {torch.id} to {target_address}")
        
        try:
            # Parse target address to get valley name
            valley_name = self._parse_valley_from_address(target_address)
            
            # Package torch with Party Box attachments if needed
            packaged_torch = await self._package_torch(torch)
            
            # Send via MCP broker to target valley's dock/incoming channel
            channel = f"valley:{valley_name}/dock/incoming"
            message = packaged_torch.dict()
            
            success = await self.mcp_broker.publish(channel, message)
            
            if success:
                logger.debug(f"Successfully sent torch {torch.id} to {target_address}")
            else:
                logger.error(f"Failed to send torch {torch.id} to {target_address}")
            
            return success
            
        except Exception as e:
            logger.error(f"Error sending torch {torch.id}: {e}")
            return False
    
    async def broadcast_discovery(self) -> None:
        """Broadcast discovery information to the community"""
        if self.dock_mode == DockMode.PRIVATE:
            return  # No discovery in private mode
        
        valley_config = self.valley.get_config()
        
        discovery_info = {
            "valley_name": valley_config.name,
            "dock_mode": self.dock_mode.value,
            "status": "active" if self._running else "inactive",
            "alias": valley_config.name,  # Could be different from name
            "public_address": f"valley:{valley_config.name}",
            "timestamp": asyncio.get_event_loop().time()
        }
        
        # Include exposed campfires based on dock mode
        if self.dock_mode == DockMode.PUBLIC:
            discovery_info["exposed_campfires"] = valley_config.campfires.get("visible", [])
        elif self.dock_mode == DockMode.PARTIAL:
            discovery_info["exposed_campfires"] = []  # Limited exposure
        
        # Broadcast to dock:invite channel
        await self.mcp_broker.publish("dock:invite", discovery_info)
        logger.debug(f"Broadcasted discovery info for valley '{valley_config.name}'")
    
    async def validate_sender(self, torch: Torch) -> bool:
        """Validate the sender of a torch"""
        # TODO: Implement proper sender validation
        # This would involve:
        # 1. Check if sender valley is in trusted list
        # 2. Verify digital signature
        # 3. Check community membership
        # 4. Validate key authentication
        
        # Placeholder implementation
        if not torch.sender_valley:
            return False
        
        if not torch.signature:
            return False
        
        # For now, accept all torches (this should be properly implemented)
        return True
    
    async def _subscribe_to_channels(self) -> None:
        """Subscribe to dock-related MCP channels"""
        valley_config = self.valley.get_config()
        valley_name = valley_config.name
        
        # Subscribe to incoming torch channel
        incoming_channel = f"valley:{valley_name}/dock/incoming"
        await self.mcp_broker.subscribe(incoming_channel, self._handle_incoming_message)
        self._subscriptions[incoming_channel] = True
        
        # Subscribe to discovery channel if not in private mode
        if self.dock_mode != DockMode.PRIVATE:
            await self.mcp_broker.subscribe("dock:invite", self._handle_discovery_message)
            self._subscriptions["dock:invite"] = True
        
        logger.debug(f"Subscribed to {len(self._subscriptions)} channels")
    
    async def _handle_incoming_message(self, channel: str, message: Dict[str, Any]) -> None:
        """Handle incoming MCP messages"""
        try:
            # Convert message to Torch object
            torch = Torch(**message)
            await self.handle_incoming_torch(torch)
        except Exception as e:
            logger.error(f"Error processing incoming message on {channel}: {e}")
    
    async def _handle_discovery_message(self, channel: str, message: Dict[str, Any]) -> None:
        """Handle discovery messages from other valleys"""
        try:
            valley_name = message.get("valley_name")
            if valley_name:
                logger.debug(f"Discovered valley: {valley_name}")
                # TODO: Process discovery information
                # This could update known valleys, establish connections, etc.
        except Exception as e:
            logger.error(f"Error processing discovery message: {e}")
    
    async def _route_torch(self, torch: Torch) -> None:
        """Route torch to appropriate campfire based on target address"""
        try:
            # Parse target address: valley:name/campfire/camper
            parts = torch.target_address.split('/')
            if len(parts) < 2:
                logger.error(f"Invalid target address format: {torch.target_address}")
                return
            
            campfire_name = parts[1]
            
            # Get campfire from valley
            campfires = self.valley.get_campfires()
            if campfire_name in campfires:
                campfire = campfires[campfire_name]
                await campfire.process_torch(torch)
            else:
                logger.warning(f"Campfire '{campfire_name}' not found for torch {torch.id}")
                
        except Exception as e:
            logger.error(f"Error routing torch {torch.id}: {e}")
    
    async def _package_torch(self, torch: Torch) -> Torch:
        """Package torch with Party Box attachments"""
        # TODO: Implement attachment packaging
        # This would involve:
        # 1. Check if payload is over size limit (1KB)
        # 2. Store large items in Party Box
        # 3. Replace with attachment references
        # 4. Sign the torch
        
        # For now, return torch as-is
        return torch
    
    async def _discovery_loop(self) -> None:
        """Periodic discovery broadcast loop"""
        while self._running:
            try:
                await self.broadcast_discovery()
                await asyncio.sleep(30)  # Broadcast every 30 seconds
            except Exception as e:
                logger.error(f"Error in discovery loop: {e}")
                await asyncio.sleep(5)  # Short delay before retry
    
    def _parse_valley_from_address(self, address: str) -> str:
        """Parse valley name from hierarchical address"""
        # Format: valley:name/campfire/camper
        if ':' not in address:
            raise ValueError(f"Invalid address format: {address}")
        
        valley_part = address.split(':')[1]
        return valley_part.split('/')[0]
    
    def is_running(self) -> bool:
        """Check if the dock gateway is running"""
        return self._running
    
    def __repr__(self) -> str:
        valley_name = self.valley.get_config().name
        return f"Dock(valley='{valley_name}', mode={self.dock_mode}, running={self._running})"
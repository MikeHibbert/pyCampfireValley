"""
Federation management for CampfireValley.
Handles valley-to-valley communication, membership, and discovery.
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding

from .interfaces import IFederationManager, IMCPBroker, IKeyManager
from .models import FederationMembership, Torch, VALIServiceRequest, VALIServiceResponse


logger = logging.getLogger(__name__)


class FederationManager(IFederationManager):
    """
    Manages federation membership and inter-valley communication.
    Implements the distributed valley network with discovery and heartbeat mechanisms.
    """
    
    def __init__(self, valley_name: str, mcp_broker: IMCPBroker, key_manager: IKeyManager):
        self.valley_name = valley_name
        self.mcp_broker = mcp_broker
        self.key_manager = key_manager
        
        # Federation state
        self.federations: Dict[str, FederationMembership] = {}
        self.discovered_valleys: Dict[str, Dict[str, FederationMembership]] = {}
        self.capabilities: Set[str] = set()
        
        # Heartbeat and discovery
        self.heartbeat_interval = 30  # seconds
        self.discovery_interval = 60  # seconds
        self.heartbeat_tasks: Dict[str, asyncio.Task] = {}
        
        # Event handlers
        self.service_handlers: Dict[str, callable] = {}
        
    async def start(self) -> None:
        """Start the federation manager"""
        logger.info(f"Starting federation manager for valley: {self.valley_name}")
        
        # Subscribe to federation channels
        await self.mcp_broker.subscribe("federation.discovery", self._handle_discovery_message)
        await self.mcp_broker.subscribe("federation.heartbeat", self._handle_heartbeat_message)
        await self.mcp_broker.subscribe(f"federation.valley.{self.valley_name}", self._handle_direct_message)
        
        logger.info("Federation manager started successfully")
    
    async def stop(self) -> None:
        """Stop the federation manager"""
        logger.info("Stopping federation manager")
        
        # Cancel heartbeat tasks
        for task in self.heartbeat_tasks.values():
            task.cancel()
        
        # Leave all federations
        for federation_name in list(self.federations.keys()):
            await self.leave_federation(federation_name)
        
        logger.info("Federation manager stopped")
    
    async def join_federation(self, federation_name: str, invitation_key: str) -> bool:
        """
        Join a federation with an invitation key.
        
        Args:
            federation_name: Name of the federation to join
            invitation_key: Invitation key for authentication
            
        Returns:
            True if successfully joined, False otherwise
        """
        try:
            logger.info(f"Attempting to join federation: {federation_name}")
            
            # Generate key pair for this federation
            public_key, private_key = await self.key_manager.generate_key_pair()
            
            # Store the private key
            await self.key_manager.store_key(f"federation.{federation_name}.private", private_key, "private")
            
            # Create membership record
            membership = FederationMembership(
                valley_id=self.valley_name,
                federation_name=federation_name,
                public_key=public_key,
                capabilities=list(self.capabilities)
            )
            
            # Store membership
            self.federations[federation_name] = membership
            
            # Announce joining to the federation
            await self._announce_federation_join(federation_name, membership)
            
            # Start heartbeat for this federation
            self.heartbeat_tasks[federation_name] = asyncio.create_task(
                self._heartbeat_loop(federation_name)
            )
            
            logger.info(f"Successfully joined federation: {federation_name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to join federation {federation_name}: {e}")
            return False
    
    async def leave_federation(self, federation_name: str) -> bool:
        """
        Leave a federation.
        
        Args:
            federation_name: Name of the federation to leave
            
        Returns:
            True if successfully left, False otherwise
        """
        try:
            if federation_name not in self.federations:
                logger.warning(f"Not a member of federation: {federation_name}")
                return False
            
            logger.info(f"Leaving federation: {federation_name}")
            
            # Cancel heartbeat
            if federation_name in self.heartbeat_tasks:
                self.heartbeat_tasks[federation_name].cancel()
                del self.heartbeat_tasks[federation_name]
            
            # Announce leaving
            await self._announce_federation_leave(federation_name)
            
            # Clean up membership
            del self.federations[federation_name]
            if federation_name in self.discovered_valleys:
                del self.discovered_valleys[federation_name]
            
            # Remove keys
            await self.key_manager.delete_key(f"federation.{federation_name}.private")
            
            logger.info(f"Successfully left federation: {federation_name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to leave federation {federation_name}: {e}")
            return False
    
    async def discover_valleys(self, federation_name: str) -> List[FederationMembership]:
        """
        Discover other valleys in the federation.
        
        Args:
            federation_name: Name of the federation
            
        Returns:
            List of discovered valley memberships
        """
        if federation_name not in self.federations:
            logger.warning(f"Not a member of federation: {federation_name}")
            return []
        
        # Send discovery request
        discovery_message = {
            "type": "discovery_request",
            "federation": federation_name,
            "sender": self.valley_name,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        await self.mcp_broker.publish("federation.discovery", discovery_message)
        
        # Return currently discovered valleys
        return list(self.discovered_valleys.get(federation_name, {}).values())
    
    async def announce_capabilities(self, capabilities: List[str]) -> bool:
        """
        Announce this valley's capabilities to all federations.
        
        Args:
            capabilities: List of service capabilities
            
        Returns:
            True if successfully announced
        """
        try:
            self.capabilities.update(capabilities)
            
            # Update all federation memberships
            for federation_name, membership in self.federations.items():
                membership.capabilities = list(self.capabilities)
                
                # Announce updated capabilities
                capability_message = {
                    "type": "capability_update",
                    "federation": federation_name,
                    "sender": self.valley_name,
                    "capabilities": list(self.capabilities),
                    "timestamp": datetime.utcnow().isoformat()
                }
                
                await self.mcp_broker.publish("federation.discovery", capability_message)
            
            logger.info(f"Announced capabilities: {capabilities}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to announce capabilities: {e}")
            return False
    
    async def get_federation_status(self, federation_name: str) -> Optional[FederationMembership]:
        """
        Get this valley's status in a federation.
        
        Args:
            federation_name: Name of the federation
            
        Returns:
            Federation membership or None if not a member
        """
        return self.federations.get(federation_name)
    
    async def heartbeat(self, federation_name: str) -> bool:
        """
        Send heartbeat to maintain federation membership.
        
        Args:
            federation_name: Name of the federation
            
        Returns:
            True if heartbeat sent successfully
        """
        if federation_name not in self.federations:
            return False
        
        try:
            membership = self.federations[federation_name]
            membership.last_seen = datetime.utcnow()
            
            heartbeat_message = {
                "type": "heartbeat",
                "federation": federation_name,
                "sender": self.valley_name,
                "capabilities": list(self.capabilities),
                "timestamp": membership.last_seen.isoformat()
            }
            
            await self.mcp_broker.publish("federation.heartbeat", heartbeat_message)
            return True
            
        except Exception as e:
            logger.error(f"Failed to send heartbeat for {federation_name}: {e}")
            return False
    
    async def send_torch_to_valley(self, target_valley: str, torch: Torch) -> bool:
        """
        Send a torch directly to another valley in any federation.
        
        Args:
            target_valley: Name of the target valley
            torch: Torch to send
            
        Returns:
            True if sent successfully
        """
        try:
            # Find the target valley in discovered valleys
            target_membership = None
            for federation_valleys in self.discovered_valleys.values():
                if target_valley in federation_valleys:
                    target_membership = federation_valleys[target_valley]
                    break
            
            if not target_membership:
                logger.error(f"Target valley not found: {target_valley}")
                return False
            
            # Send torch to target valley's channel
            torch_message = torch.to_redis_message()
            await self.mcp_broker.publish(f"federation.valley.{target_valley}", torch_message)
            
            logger.info(f"Sent torch to valley: {target_valley}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send torch to {target_valley}: {e}")
            return False
    
    # Private methods
    
    async def _heartbeat_loop(self, federation_name: str) -> None:
        """Continuous heartbeat loop for a federation"""
        while federation_name in self.federations:
            try:
                await self.heartbeat(federation_name)
                await asyncio.sleep(self.heartbeat_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Heartbeat error for {federation_name}: {e}")
                await asyncio.sleep(self.heartbeat_interval)
    
    async def _announce_federation_join(self, federation_name: str, membership: FederationMembership) -> None:
        """Announce joining a federation"""
        join_message = {
            "type": "valley_joined",
            "federation": federation_name,
            "valley": {
                "valley_id": membership.valley_id,
                "public_key": membership.public_key,
                "capabilities": membership.capabilities,
                "joined_at": membership.joined_at.isoformat()
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        
        await self.mcp_broker.publish("federation.discovery", join_message)
    
    async def _announce_federation_leave(self, federation_name: str) -> None:
        """Announce leaving a federation"""
        leave_message = {
            "type": "valley_left",
            "federation": federation_name,
            "sender": self.valley_name,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        await self.mcp_broker.publish("federation.discovery", leave_message)
    
    async def _handle_discovery_message(self, message: Dict) -> None:
        """Handle discovery messages from other valleys"""
        try:
            msg_type = message.get("type")
            federation = message.get("federation")
            sender = message.get("sender")
            
            if not all([msg_type, federation, sender]) or sender == self.valley_name:
                return
            
            if federation not in self.federations:
                return  # Not a member of this federation
            
            if federation not in self.discovered_valleys:
                self.discovered_valleys[federation] = {}
            
            if msg_type == "discovery_request":
                # Respond with our information
                response = {
                    "type": "discovery_response",
                    "federation": federation,
                    "sender": self.valley_name,
                    "valley_info": {
                        "valley_id": self.valley_name,
                        "public_key": self.federations[federation].public_key,
                        "capabilities": list(self.capabilities),
                        "joined_at": self.federations[federation].joined_at.isoformat()
                    },
                    "timestamp": datetime.utcnow().isoformat()
                }
                await self.mcp_broker.publish("federation.discovery", response)
            
            elif msg_type in ["discovery_response", "valley_joined", "capability_update"]:
                # Update discovered valleys
                valley_info = message.get("valley_info", message.get("valley", {}))
                if valley_info:
                    membership = FederationMembership(
                        valley_id=valley_info["valley_id"],
                        federation_name=federation,
                        public_key=valley_info["public_key"],
                        capabilities=valley_info.get("capabilities", []),
                        joined_at=datetime.fromisoformat(valley_info["joined_at"])
                    )
                    self.discovered_valleys[federation][sender] = membership
            
            elif msg_type == "valley_left":
                # Remove valley from discovered list
                if sender in self.discovered_valleys[federation]:
                    del self.discovered_valleys[federation][sender]
            
        except Exception as e:
            logger.error(f"Error handling discovery message: {e}")
    
    async def _handle_heartbeat_message(self, message: Dict) -> None:
        """Handle heartbeat messages from other valleys"""
        try:
            federation = message.get("federation")
            sender = message.get("sender")
            
            if not all([federation, sender]) or sender == self.valley_name:
                return
            
            if federation not in self.federations:
                return  # Not a member of this federation
            
            if federation not in self.discovered_valleys:
                self.discovered_valleys[federation] = {}
            
            # Update last seen time
            if sender in self.discovered_valleys[federation]:
                self.discovered_valleys[federation][sender].last_seen = datetime.utcnow()
                self.discovered_valleys[federation][sender].capabilities = message.get("capabilities", [])
            
        except Exception as e:
            logger.error(f"Error handling heartbeat message: {e}")
    
    async def _handle_direct_message(self, message: Dict) -> None:
        """Handle direct messages sent to this valley"""
        try:
            if message.get("type") == "torch":
                # Convert to Torch object and process
                torch = Torch.from_redis_message(message)
                
                # Handle VALI service requests
                if torch.data.get("vali_request"):
                    await self._handle_vali_request(torch)
                else:
                    # Route to appropriate handler
                    logger.info(f"Received torch from {torch.sender_valley}: {torch.id}")
            
        except Exception as e:
            logger.error(f"Error handling direct message: {e}")
    
    async def _handle_vali_request(self, torch: Torch) -> None:
        """Handle VALI service requests"""
        try:
            request_data = torch.data.get("vali_request")
            if not request_data:
                return
            
            request = VALIServiceRequest(**request_data)
            
            # Find appropriate service handler
            if request.service_type in self.service_handlers:
                handler = self.service_handlers[request.service_type]
                response = await handler(request)
                
                # Send response back
                response_torch = Torch(
                    sender_valley=self.valley_name,
                    target_address=f"{torch.sender_valley}:response",
                    data={"vali_response": response.dict()},
                    signature="",  # Will be signed by key manager
                    source="vali_service",
                    destination=torch.source
                )
                
                await self.send_torch_to_valley(torch.sender_valley, response_torch)
            
        except Exception as e:
            logger.error(f"Error handling VALI request: {e}")
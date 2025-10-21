"""
Dock gateway implementation for inter-valley communication.
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List
import time
import random
from .interfaces import IDock, IValley, IMCPBroker, IPartyBox, IFederationManager, IVALICoordinator
from .models import Torch, DockMode, FederationMembership


logger = logging.getLogger(__name__)


class Dock(IDock):
    """
    Dock gateway that manages inter-valley communication through MCP channels.
    Enhanced with federation support and VALI coordination.
    """
    
    def __init__(self, valley: IValley, mcp_broker: IMCPBroker, party_box: IPartyBox, 
                 federation_manager: Optional[IFederationManager] = None,
                 vali_coordinator: Optional[IVALICoordinator] = None):
        """
        Initialize a Dock instance.
        
        Args:
            valley: The valley this dock belongs to
            mcp_broker: MCP broker for communication
            party_box: Party Box for attachment storage
            federation_manager: Federation manager for inter-valley coordination
            vali_coordinator: VALI coordinator for service management
        """
        self.valley = valley
        self.mcp_broker = mcp_broker
        self.party_box = party_box
        self.federation_manager = federation_manager
        self.vali_coordinator = vali_coordinator
        
        # Runtime state
        self._running = False
        self._subscriptions: Dict[str, Any] = {}
        self._known_valleys: Dict[str, FederationMembership] = {}
        self._routing_cache: Dict[str, str] = {}  # Cache for valley routing
        
        # Get dock configuration from valley config
        valley_config = valley.get_config()
        self.dock_mode = DockMode(valley_config.env.get("dock_mode", "private"))
        
        logger.info(f"Dock initialized for valley '{valley_config.name}' in {self.dock_mode} mode")
        if federation_manager:
            logger.info("Federation support enabled")
        if vali_coordinator:
            logger.info("VALI coordination enabled")
    
    async def start_gateway(self) -> None:
        """Start the dock gateway"""
        if self._running:
            logger.warning("Dock gateway is already running")
            return
        
        logger.info("Starting dock gateway...")
        
        try:
            # Subscribe to dock channels
            await self._subscribe_to_channels()
            
            # Initialize federation discovery if federation manager is available
            if self.federation_manager:
                await self._initialize_federation_discovery()
            
            # Start discovery broadcasts if in public mode
            if self.dock_mode == DockMode.PUBLIC:
                asyncio.create_task(self._discovery_loop())
            
            # Start federation valley discovery if enabled
            if self.federation_manager and self.dock_mode != DockMode.PRIVATE:
                asyncio.create_task(self._federation_discovery_loop())
            
            # Start periodic cleanup task
            asyncio.create_task(self._cleanup_loop())
            
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
        
        # Cancel all background tasks
        tasks_to_cancel = []
        
        if hasattr(self, '_federation_discovery_task') and self._federation_discovery_task:
            tasks_to_cancel.append(self._federation_discovery_task)
        
        if hasattr(self, '_cleanup_task') and self._cleanup_task:
            tasks_to_cancel.append(self._cleanup_task)
        
        if hasattr(self, '_discovery_task') and self._discovery_task:
            tasks_to_cancel.append(self._discovery_task)
        
        # Cancel all tasks
        for task in tasks_to_cancel:
            task.cancel()
        
        # Wait for tasks to complete cancellation
        if tasks_to_cancel:
            await asyncio.gather(*tasks_to_cancel, return_exceptions=True)
        
        self._running = False
        
        logger.info("Dock gateway stopped")
    
    async def handle_incoming_torch(self, torch: Torch) -> bool:
        """Handle incoming torch from another valley with federation validation and error handling"""
        if not self._running:
            logger.warning("Received torch while dock gateway is not running")
            return False
        
        logger.debug(f"Handling incoming torch {torch.id} from {torch.sender_valley}")
        
        async def _handle_operation():
            # Validate torch integrity first
            if not await self._validate_torch_integrity(torch):
                raise ValueError(f"Torch {torch.id} failed integrity validation")
            
            # Validate sender using federation membership and digital signatures
            if not await self.validate_sender(torch):
                raise PermissionError(f"Invalid sender {torch.sender_valley} for torch {torch.id}")
            
            # Retrieve attachment content from PartyBox if needed
            if torch.metadata and torch.metadata.get("party_box_refs"):
                await self._retrieve_party_box_attachments(torch)
            
            # Route torch to appropriate campfire
            await self._route_torch(torch)
            logger.info(f"Successfully processed incoming torch {torch.id} from {torch.sender_valley}")
            return True
        
        try:
            # Use retry mechanism for handling
            result = await self._retry_with_backoff(
                _handle_operation,
                max_retries=2,  # Fewer retries for incoming torches
                base_delay=0.5,
                max_delay=5.0
            )
            return result
            
        except Exception as e:
            sender_valley = torch.sender_valley or "unknown"
            await self._handle_communication_error(e, f"handle_incoming_torch {torch.id}", sender_valley)
            return False
    
    async def send_torch(self, target_address: str, torch: Torch) -> bool:
        """Send a torch to the specified target address using federation-aware routing with retry logic"""
        if not self._running:
            raise RuntimeError("Dock gateway must be started before sending torches")
        
        logger.debug(f"Sending torch {torch.id} to {target_address}")
        
        # Parse target address to get valley name
        valley_name = self._parse_valley_from_address(target_address)
        
        async def _send_operation():
            # Validate torch integrity first
            if not await self._validate_torch_integrity(torch):
                raise ValueError(f"Torch {torch.id} failed integrity validation")
            
            # Check if target valley is reachable
            if not await self._is_valley_reachable(valley_name):
                raise ConnectionError(f"Target valley {valley_name} is not reachable")
            
            # Package torch with Party Box attachments if needed
            packaged_torch = await self._package_torch(torch)
            
            # Sign the torch if we have federation capabilities
            if self.federation_manager:
                packaged_torch = await self._sign_torch(packaged_torch)
            
            # Determine routing method
            routing_method = await self._determine_routing_method(valley_name)
            
            if routing_method == "federation":
                # Use federation manager for direct valley communication
                success = await self.federation_manager.send_torch_to_valley(valley_name, packaged_torch)
                if not success:
                    raise RuntimeError(f"Federation routing failed for valley {valley_name}")
            elif routing_method == "vali":
                # Use VALI coordinator for service-based routing
                success = await self.vali_coordinator.route_torch(target_address, packaged_torch)
                if not success:
                    raise RuntimeError(f"VALI routing failed for valley {valley_name}")
            else:
                # Use direct MCP broker communication
                channel = f"valley:{valley_name}/dock/incoming"
                message = packaged_torch.dict()
                success = await self.mcp_broker.publish(channel, message)
                if not success:
                    raise RuntimeError(f"Direct MCP routing failed for valley {valley_name}")
            
            logger.debug(f"Successfully sent torch {torch.id} to {target_address} via {routing_method}")
            # Update routing cache
            self._routing_cache[valley_name] = routing_method
            return True
        
        try:
            # Use retry mechanism for sending
            result = await self._retry_with_backoff(
                _send_operation,
                max_retries=3,
                base_delay=1.0,
                max_delay=10.0
            )
            return result
            
        except Exception as e:
            await self._handle_communication_error(e, f"send_torch to {valley_name}", valley_name)
            return False
    
    async def broadcast_discovery(self) -> None:
        """Broadcast discovery information to the community with federation capabilities"""
        if self.dock_mode == DockMode.PRIVATE:
            return  # No discovery in private mode
        
        valley_config = self.valley.get_config()
        
        discovery_info = {
            "valley_name": valley_config.name,
            "dock_mode": self.dock_mode.value,
            "status": "active" if self._running else "inactive",
            "alias": valley_config.name,  # Could be different from name
            "public_address": f"valley:{valley_config.name}",
            "timestamp": asyncio.get_event_loop().time(),
            "protocol_version": "1.0"
        }
        
        # Include federation information if available
        if self.federation_manager:
            try:
                # Get federation memberships
                federations = await self.federation_manager.get_all_federations()
                discovery_info["federations"] = [f.federation_name for f in federations]
                
                # Get valley capabilities
                capabilities = await self._get_valley_capabilities()
                discovery_info["capabilities"] = capabilities
                
                # Include public key for federation verification
                if federations:
                    # Use the first federation's public key as our identity
                    discovery_info["public_key"] = federations[0].public_key
                    
            except Exception as e:
                logger.warning(f"Error including federation info in discovery: {e}")
        
        # Include VALI services if coordinator is available
        if self.vali_coordinator:
            try:
                services = await self.vali_coordinator.get_available_services()
                discovery_info["vali_services"] = [service.service_type for service in services]
            except Exception as e:
                logger.warning(f"Error including VALI services in discovery: {e}")
        
        # Include exposed campfires based on dock mode
        if self.dock_mode == DockMode.PUBLIC:
            discovery_info["exposed_campfires"] = valley_config.campfires.get("visible", [])
        elif self.dock_mode == DockMode.PARTIAL:
            discovery_info["exposed_campfires"] = []  # Limited exposure
        
        # Broadcast to dock:invite channel
        await self.mcp_broker.publish("dock:invite", discovery_info)
        logger.debug(f"Broadcasted enhanced discovery info for valley '{valley_config.name}'")
    
    async def validate_sender(self, torch: Torch) -> bool:
        """Validate the sender of a torch using federation membership and digital signatures"""
        try:
            # Basic validation
            if not torch.sender_valley:
                logger.warning(f"Torch {torch.id} missing sender valley")
                return False
            
            if not torch.signature:
                logger.warning(f"Torch {torch.id} missing signature")
                return False
            
            # Check if sender valley is known through federation
            if self.federation_manager:
                # Check if sender is in any of our federations
                sender_membership = await self._get_valley_federation_membership(torch.sender_valley)
                if sender_membership:
                    # Verify digital signature using sender's public key
                    if await self._verify_torch_signature(torch, sender_membership.public_key):
                        logger.debug(f"Validated torch {torch.id} from federated valley {torch.sender_valley}")
                        return True
                    else:
                        logger.warning(f"Invalid signature for torch {torch.id} from {torch.sender_valley}")
                        return False
            
            # Check if sender is in our known valleys (discovery cache)
            if torch.sender_valley in self._known_valleys:
                valley_info = self._known_valleys[torch.sender_valley]
                if await self._verify_torch_signature(torch, valley_info.public_key):
                    logger.debug(f"Validated torch {torch.id} from known valley {torch.sender_valley}")
                    return True
                else:
                    logger.warning(f"Invalid signature for torch {torch.id} from known valley {torch.sender_valley}")
                    return False
            
            # If in private mode, reject unknown senders
            if self.dock_mode == DockMode.PRIVATE:
                logger.warning(f"Rejecting torch {torch.id} from unknown valley {torch.sender_valley} (private mode)")
                return False
            
            # In public/partial mode, allow but log unknown senders
            logger.info(f"Accepting torch {torch.id} from unknown valley {torch.sender_valley} (public mode)")
            return True
            
        except Exception as e:
            logger.error(f"Error validating sender for torch {torch.id}: {e}")
            return False
    
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
        """Handle discovery messages from other valleys with federation processing"""
        try:
            valley_name = message.get("valley_name")
            if not valley_name or valley_name == self.valley.get_config().name:
                return  # Ignore our own messages or invalid ones
            
            logger.debug(f"Discovered valley: {valley_name}")
            
            # Create or update valley information
            if valley_name not in self._known_valleys:
                # Create a basic federation membership record for discovered valley
                membership = FederationMembership(
                    valley_id=valley_name,
                    federation_name="discovery",  # Special federation for discovered valleys
                    public_key=message.get("public_key", ""),
                    capabilities=message.get("capabilities", []),
                    status="discovered",
                    last_seen=datetime.now()
                )
                
                # Add additional metadata from discovery
                membership.metadata = {
                    "dock_mode": message.get("dock_mode", "unknown"),
                    "public_address": message.get("public_address", f"valley:{valley_name}"),
                    "protocol_version": message.get("protocol_version", "unknown"),
                    "exposed_campfires": message.get("exposed_campfires", []),
                    "vali_services": message.get("vali_services", []),
                    "federations": message.get("federations", [])
                }
                
                self._known_valleys[valley_name] = membership
                logger.info(f"Added discovered valley {valley_name} to known valleys")
            else:
                # Update existing valley information
                existing = self._known_valleys[valley_name]
                existing.last_seen = datetime.now()
                existing.capabilities = message.get("capabilities", existing.capabilities)
                
                # Update metadata
                if hasattr(existing, 'metadata'):
                    existing.metadata.update({
                        "dock_mode": message.get("dock_mode", existing.metadata.get("dock_mode")),
                        "protocol_version": message.get("protocol_version", existing.metadata.get("protocol_version")),
                        "exposed_campfires": message.get("exposed_campfires", existing.metadata.get("exposed_campfires", [])),
                        "vali_services": message.get("vali_services", existing.metadata.get("vali_services", [])),
                        "federations": message.get("federations", existing.metadata.get("federations", []))
                    })
                
                logger.debug(f"Updated information for valley {valley_name}")
            
            # Check if we share any federations with this valley
            if self.federation_manager and message.get("federations"):
                our_federations = await self.federation_manager.get_all_federations()
                our_federation_names = {f.federation_name for f in our_federations}
                their_federations = set(message.get("federations", []))
                
                shared_federations = our_federation_names.intersection(their_federations)
                if shared_federations:
                    logger.info(f"Valley {valley_name} shares federations with us: {shared_federations}")
                    # Update routing cache to prefer federation routing
                    self._routing_cache[valley_name] = "federation"
            
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
        try:
            # Handle attachments through PartyBox if available
            if self.party_box and hasattr(torch, 'attachments') and torch.attachments:
                party_box_refs = []
                remaining_attachments = []
                
                for attachment in torch.attachments:
                    # Check if attachment is large enough to warrant PartyBox storage
                    attachment_size = len(str(attachment)) if attachment else 0
                    
                    if attachment_size > 1024 * 1024:  # 1MB threshold
                        # Store large attachment in PartyBox
                        try:
                            party_box_id = await self.party_box.store_attachment(
                                attachment_data=attachment,
                                torch_id=torch.id,
                                metadata={
                                    "size": attachment_size,
                                    "type": getattr(attachment, 'type', 'unknown'),
                                    "created_at": asyncio.get_event_loop().time()
                                }
                            )
                            
                            party_box_refs.append({
                                "id": party_box_id,
                                "size": attachment_size,
                                "type": getattr(attachment, 'type', 'unknown'),
                                "retrieval_url": f"partybox://{party_box_id}"
                            })
                            
                            logger.debug(f"Stored large attachment {party_box_id} in PartyBox")
                            
                        except Exception as e:
                            logger.error(f"Failed to store attachment in PartyBox: {e}")
                            # Fall back to direct attachment
                            remaining_attachments.append(attachment)
                    else:
                        # Small attachment, include directly
                        remaining_attachments.append(attachment)
                
                # Update torch with processed attachments
                torch.attachments = remaining_attachments
                
                # Add PartyBox references to torch metadata
                if party_box_refs:
                    if not torch.metadata:
                        torch.metadata = {}
                    torch.metadata["party_box_refs"] = party_box_refs
                    torch.metadata["packaging"] = {
                        "packaged_at": asyncio.get_event_loop().time(),
                        "party_box_enabled": True,
                        "total_attachments": len(remaining_attachments),
                        "party_box_refs": len(party_box_refs),
                        "package_version": "1.0"
                    }
            
            return torch
            
        except Exception as e:
            logger.error(f"Error packaging torch {torch.id}: {e}")
            # Return torch as-is on error
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
    
    async def _initialize_federation_discovery(self) -> None:
        """Initialize federation discovery and populate known valleys"""
        try:
            if not self.federation_manager:
                return
            
            # Get all federation memberships
            federations = await self.federation_manager.get_all_federations()
            
            for federation in federations:
                # Discover valleys in each federation
                valleys = await self.federation_manager.discover_valleys(federation.federation_name)
                for valley in valleys:
                    if valley.valley_id != self.valley.get_config().name:  # Don't include ourselves
                        self._known_valleys[valley.valley_id] = valley
            
            logger.info(f"Discovered {len(self._known_valleys)} valleys through federation")
            
        except Exception as e:
            logger.error(f"Error initializing federation discovery: {e}")
    
    async def _federation_discovery_loop(self) -> None:
        """Periodic federation valley discovery loop"""
        while self._running:
            try:
                await self._initialize_federation_discovery()
                await asyncio.sleep(120)  # Discover every 2 minutes
            except Exception as e:
                logger.error(f"Error in federation discovery loop: {e}")
                await asyncio.sleep(30)  # Short delay before retry
    
    async def _is_valley_reachable(self, valley_name: str) -> bool:
        """Check if a valley is reachable through any available method"""
        # Check if it's our own valley
        if valley_name == self.valley.get_config().name:
            return True
        
        # Check federation membership
        if self.federation_manager:
            membership = await self._get_valley_federation_membership(valley_name)
            if membership:
                return True
        
        # Check known valleys from discovery
        if valley_name in self._known_valleys:
            return True
        
        # In public mode, assume reachable
        if self.dock_mode == DockMode.PUBLIC:
            return True
        
        return False
    
    async def _determine_routing_method(self, valley_name: str) -> str:
        """Determine the best routing method for reaching a valley"""
        # Check cache first
        if valley_name in self._routing_cache:
            return self._routing_cache[valley_name]
        
        # Check if valley is in federation
        if self.federation_manager:
            membership = await self._get_valley_federation_membership(valley_name)
            if membership:
                return "federation"
        
        # Check if VALI coordinator can handle routing
        if self.vali_coordinator:
            services = await self.vali_coordinator.get_available_services()
            for service in services:
                if service.service_type == "routing" and valley_name in service.metadata.get("supported_valleys", []):
                    return "vali"
        
        # Default to direct MCP broker communication
        return "direct"
    
    async def _get_valley_federation_membership(self, valley_name: str) -> Optional[FederationMembership]:
        """Get federation membership for a specific valley"""
        if not self.federation_manager:
            return None
        
        try:
            federations = await self.federation_manager.get_all_federations()
            for federation in federations:
                valleys = await self.federation_manager.discover_valleys(federation.federation_name)
                for valley in valleys:
                    if valley.valley_id == valley_name:
                        return valley
        except Exception as e:
            logger.error(f"Error getting federation membership for {valley_name}: {e}")
        
        return None
    
    async def _verify_torch_signature(self, torch: Torch, public_key: str) -> bool:
        """Verify the digital signature of a torch"""
        try:
            # TODO: Implement actual signature verification
            # This would use the public key to verify the torch signature
            # For now, return True if both signature and public key exist
            return bool(torch.signature and public_key)
        except Exception as e:
            logger.error(f"Error verifying torch signature: {e}")
            return False
    
    async def _sign_torch(self, torch: Torch) -> Torch:
        """Sign a torch using our federation private key"""
        try:
            if not self.federation_manager:
                return torch
            
            # TODO: Implement actual torch signing
            # This would use our private key to sign the torch
            # For now, just add a placeholder signature
            torch.signature = "signed_by_dock"
            torch.sender_valley = self.valley.get_config().name
            
            return torch
        except Exception as e:
            logger.error(f"Error signing torch: {e}")
            return torch
    
    async def _get_valley_capabilities(self) -> List[str]:
        """Get the capabilities of this valley for federation announcement"""
        capabilities = []
        
        # Add basic dock capabilities
        capabilities.append("dock_gateway")
        capabilities.append(f"dock_mode_{self.dock_mode.value}")
        
        # Add federation capabilities
        if self.federation_manager:
            capabilities.append("federation_support")
        
        # Add VALI capabilities
        if self.vali_coordinator:
            capabilities.append("vali_coordination")
            try:
                services = await self.vali_coordinator.get_available_services()
                for service in services:
                    capabilities.append(f"vali_service_{service.service_type}")
            except Exception:
                pass
        
        # Add campfire capabilities
        try:
            campfires = self.valley.get_campfires()
            for campfire_name in campfires.keys():
                capabilities.append(f"campfire_{campfire_name}")
        except Exception:
            pass
        
        return capabilities
    
    def is_running(self) -> bool:
        """Check if the dock gateway is running"""
        return self._running
    
    def get_known_valleys(self) -> Dict[str, FederationMembership]:
        """Get all known valleys from federation discovery"""
        return self._known_valleys.copy()
    
    def get_routing_cache(self) -> Dict[str, str]:
        """Get the current routing cache"""
        return self._routing_cache.copy()
    
    async def _retry_with_backoff(self, operation, max_retries: int = 3, base_delay: float = 1.0, max_delay: float = 30.0, *args, **kwargs):
        """Execute an operation with exponential backoff retry logic"""
        last_exception = None
        
        for attempt in range(max_retries + 1):
            try:
                return await operation(*args, **kwargs)
            except Exception as e:
                last_exception = e
                
                if attempt == max_retries:
                    logger.error(f"Operation failed after {max_retries + 1} attempts: {e}")
                    raise e
                
                # Calculate delay with exponential backoff and jitter
                delay = min(base_delay * (2 ** attempt), max_delay)
                jitter = random.uniform(0, delay * 0.1)  # Add up to 10% jitter
                total_delay = delay + jitter
                
                logger.warning(f"Operation failed (attempt {attempt + 1}/{max_retries + 1}), retrying in {total_delay:.2f}s: {e}")
                await asyncio.sleep(total_delay)
        
        # This should never be reached, but just in case
        raise last_exception
    
    async def _handle_communication_error(self, error: Exception, context: str, valley_name: str = None) -> None:
        """Handle communication errors with appropriate logging and recovery actions"""
        error_info = {
            "error_type": type(error).__name__,
            "error_message": str(error),
            "context": context,
            "timestamp": time.time(),
            "valley_name": valley_name
        }
        
        logger.error(f"Communication error in {context}: {error_info}")
        
        # Update routing cache to mark valley as potentially unreachable
        if valley_name and valley_name in self._routing_cache:
            self._routing_cache[valley_name] = "error"
            logger.debug(f"Marked valley {valley_name} as having routing errors")
        
        # If it's a federation-related error, try to refresh federation discovery
        if "federation" in context.lower() and self.federation_manager:
            try:
                logger.info("Attempting to refresh federation discovery due to communication error")
                await self._initialize_federation_discovery()
            except Exception as refresh_error:
                logger.error(f"Failed to refresh federation discovery: {refresh_error}")
        
        # For critical errors, consider notifying the valley's error handler
        if hasattr(self.valley, 'handle_dock_error'):
            try:
                await self.valley.handle_dock_error(error_info)
            except Exception as handler_error:
                logger.error(f"Error in valley error handler: {handler_error}")
    
    async def _validate_torch_integrity(self, torch: Torch) -> bool:
        """Validate torch integrity before processing"""
        try:
            # Basic validation
            if not torch or not torch.id:
                logger.warning("Torch missing ID")
                return False
            
            if not torch.content and not (hasattr(torch, 'attachments') and torch.attachments):
                logger.warning(f"Torch {torch.id} has no content or attachments")
                return False
            
            # Check for required metadata
            if not torch.metadata:
                logger.debug(f"Torch {torch.id} missing metadata")
                torch.metadata = {}
            
            # Validate signature if present
            if torch.metadata.get("signature") and torch.metadata.get("sender_valley"):
                sender_valley = torch.metadata["sender_valley"]
                if sender_valley in self._known_valleys:
                    valley_info = self._known_valleys[sender_valley]
                    if valley_info.public_key:
                        is_valid = await self._verify_torch_signature(torch, valley_info.public_key)
                        if not is_valid:
                            logger.warning(f"Invalid signature for torch {torch.id} from {sender_valley}")
                            return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error validating torch integrity: {e}")
            return False
    
    async def _retrieve_party_box_attachments(self, torch: Torch) -> None:
        """Retrieve large attachments from PartyBox references"""
        try:
            if not self.party_box or not torch.metadata:
                return
            
            party_box_refs = torch.metadata.get("party_box_refs", [])
            if not party_box_refs:
                return
            
            retrieved_attachments = []
            for ref in party_box_refs:
                try:
                    attachment_data = await self.party_box.retrieve_attachment(ref["id"])
                    if attachment_data:
                        retrieved_attachments.append(attachment_data)
                        logger.debug(f"Retrieved attachment {ref['id']} from PartyBox")
                except Exception as e:
                    logger.error(f"Failed to retrieve attachment {ref['id']} from PartyBox: {e}")
            
            # Add retrieved attachments to torch
            if retrieved_attachments:
                if not torch.attachments:
                    torch.attachments = []
                torch.attachments.extend(retrieved_attachments)
                
        except Exception as e:
            logger.error(f"Error retrieving PartyBox attachments for torch {torch.id}: {e}")
    
    async def _cleanup_loop(self) -> None:
        """Periodic cleanup loop for stale data"""
        while self._running:
            try:
                await self._cleanup_stale_data()
                await asyncio.sleep(300)  # Clean up every 5 minutes
            except Exception as e:
                logger.error(f"Error in cleanup loop: {e}")
                await asyncio.sleep(60)  # Short delay before retry
    
    async def _cleanup_stale_data(self) -> None:
        """Clean up stale routing cache and valley information"""
        try:
            current_time = time.time()
            stale_threshold = 3600  # 1 hour
            
            # Clean up stale routing cache entries
            stale_routes = []
            for valley_name, route_method in self._routing_cache.items():
                if route_method == "error":
                    # Keep error entries for a shorter time
                    stale_routes.append(valley_name)
            
            for valley_name in stale_routes:
                if random.random() < 0.1:  # 10% chance to clean up error entries
                    del self._routing_cache[valley_name]
                    logger.debug(f"Cleaned up stale routing cache entry for {valley_name}")
            
            # Clean up old valley information
            stale_valleys = []
            for valley_name, valley_info in self._known_valleys.items():
                if hasattr(valley_info, 'last_seen'):
                    time_since_seen = current_time - valley_info.last_seen.timestamp()
                    if time_since_seen > stale_threshold * 24:  # 24 hours for valley info
                        stale_valleys.append(valley_name)
            
            for valley_name in stale_valleys:
                del self._known_valleys[valley_name]
                logger.info(f"Removed stale valley information for {valley_name}")
            
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
    
    def __repr__(self) -> str:
        valley_name = self.valley.get_config().name
        federation_count = len(self._known_valleys)
        return f"Dock(valley='{valley_name}', mode={self.dock_mode}, running={self._running}, known_valleys={federation_count})"
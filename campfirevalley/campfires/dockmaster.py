"""
Dockmaster Campfire - Core torch handling and routing functionality.

The Dockmaster campfire provides three essential campers:
- LoaderCamper: Loads and validates incoming torches
- RouterCamper: Routes torches to appropriate destinations
- PackerCamper: Packages outgoing torches for transport
"""

import asyncio
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime

from ..interfaces import ICampfire, IMCPBroker
from ..models import Torch, CampfireConfig
from ..campfire import Campfire, ICamper


logger = logging.getLogger(__name__)


class LoaderCamper(ICamper):
    """
    Loader camper handles incoming torch validation and unpacking.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the Loader camper.
        
        Args:
            config: Camper configuration from campfire steps
        """
        self.config = config
        self.max_torch_size = config.get('max_torch_size', 10 * 1024 * 1024)  # 10MB default
        self.allowed_valleys = config.get('allowed_valleys', [])  # Empty = allow all
        self._running = False
        
        logger.debug("LoaderCamper initialized")
    
    async def start(self) -> None:
        """Start the loader camper"""
        self._running = True
        logger.info("LoaderCamper started")
    
    async def stop(self) -> None:
        """Stop the loader camper"""
        self._running = False
        logger.info("LoaderCamper stopped")
    
    async def process(self, torch: Torch) -> Dict[str, Any]:
        """
        Process and validate an incoming torch.
        
        Args:
            torch: Incoming torch to validate
            
        Returns:
            Processing result with validation status
            
        Raises:
            ValueError: If torch validation fails
        """
        if not self._running:
            raise RuntimeError("LoaderCamper is not running")
        
        logger.debug(f"Loading torch {torch.id} from {torch.sender_valley}")
        
        # Validate torch size
        torch_size = torch.get_size_estimate()
        if torch_size > self.max_torch_size:
            raise ValueError(f"Torch size {torch_size} exceeds maximum {self.max_torch_size}")
        
        # Validate sender valley if restrictions are configured
        if self.allowed_valleys and torch.sender_valley not in self.allowed_valleys:
            raise ValueError(f"Valley {torch.sender_valley} not in allowed list")
        
        # Validate torch structure
        if not torch.id or not torch.sender_valley or not torch.target_address:
            raise ValueError("Torch missing required fields")
        
        # Check if torch is encrypted and handle accordingly
        is_encrypted = torch.is_encrypted()
        
        # Extract routing information
        target_parts = torch.target_address.split(':')
        if len(target_parts) != 2:
            raise ValueError(f"Invalid target address format: {torch.target_address}")
        
        target_valley, target_path = target_parts
        path_parts = target_path.split('/')
        
        result = {
            'status': 'loaded',
            'torch_id': torch.id,
            'sender_valley': torch.sender_valley,
            'target_valley': target_valley,
            'target_path': path_parts,
            'size_bytes': torch_size,
            'is_encrypted': is_encrypted,
            'loaded_at': datetime.utcnow().isoformat(),
            'validation_passed': True
        }
        
        logger.debug(f"Successfully loaded torch {torch.id}")
        return result


class RouterCamper(ICamper):
    """
    Router camper handles torch routing decisions and path resolution.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the Router camper.
        
        Args:
            config: Camper configuration from campfire steps
        """
        self.config = config
        self.routing_table = config.get('routing_table', {})
        self.default_route = config.get('default_route', 'local')
        self._running = False
        
        logger.debug("RouterCamper initialized")
    
    async def start(self) -> None:
        """Start the router camper"""
        self._running = True
        logger.info("RouterCamper started")
    
    async def stop(self) -> None:
        """Stop the router camper"""
        self._running = False
        logger.info("RouterCamper stopped")
    
    async def process(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process routing decisions for a torch.
        
        Args:
            data: Torch loading result from LoaderCamper
            
        Returns:
            Routing decision with next hop information
        """
        if not self._running:
            raise RuntimeError("RouterCamper is not running")
        
        torch_id = data.get('torch_id')
        target_valley = data.get('target_valley')
        target_path = data.get('target_path', [])
        
        logger.debug(f"Routing torch {torch_id} to valley {target_valley}")
        
        # Determine routing strategy
        if target_valley in self.routing_table:
            route_info = self.routing_table[target_valley]
            routing_strategy = route_info.get('strategy', 'direct')
            next_hop = route_info.get('next_hop', target_valley)
        else:
            routing_strategy = self.default_route
            next_hop = target_valley
        
        # Determine if this is a local or remote delivery
        is_local = routing_strategy == 'local'
        
        # Extract campfire and camper from path
        campfire_name = target_path[0] if target_path else 'default'
        camper_name = target_path[1] if len(target_path) > 1 else None
        
        result = {
            'status': 'routed',
            'torch_id': torch_id,
            'routing_strategy': routing_strategy,
            'next_hop': next_hop,
            'is_local': is_local,
            'target_campfire': campfire_name,
            'target_camper': camper_name,
            'routed_at': datetime.utcnow().isoformat(),
            'route_metadata': {
                'hops': 1,
                'estimated_delivery_time': '< 1s' if is_local else '< 5s'
            }
        }
        
        logger.debug(f"Routed torch {torch_id} via {routing_strategy} to {next_hop}")
        return result


class PackerCamper(ICamper):
    """
    Packer camper handles outgoing torch packaging and transport preparation.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the Packer camper.
        
        Args:
            config: Camper configuration from campfire steps
        """
        self.config = config
        self.compression_enabled = config.get('compression', True)
        self.encryption_required = config.get('encryption_required', False)
        self._running = False
        
        logger.debug("PackerCamper initialized")
    
    async def start(self) -> None:
        """Start the packer camper"""
        self._running = True
        logger.info("PackerCamper started")
    
    async def stop(self) -> None:
        """Stop the packer camper"""
        self._running = False
        logger.info("PackerCamper stopped")
    
    async def process(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process torch packaging for transport.
        
        Args:
            data: Routing result from RouterCamper
            
        Returns:
            Packaging result with transport information
        """
        if not self._running:
            raise RuntimeError("PackerCamper is not running")
        
        torch_id = data.get('torch_id')
        is_local = data.get('is_local', True)
        next_hop = data.get('next_hop')
        
        logger.debug(f"Packing torch {torch_id} for delivery to {next_hop}")
        
        # Determine transport method
        if is_local:
            transport_method = 'local_delivery'
            channel = f"campfire:{data.get('target_campfire', 'default')}"
        else:
            transport_method = 'mcp_relay'
            channel = f"valley:{next_hop}"
        
        # Prepare packaging options
        packaging_options = {
            'compression': self.compression_enabled,
            'encryption': self.encryption_required or not is_local,
            'priority': 'normal',
            'delivery_confirmation': True
        }
        
        result = {
            'status': 'packed',
            'torch_id': torch_id,
            'transport_method': transport_method,
            'delivery_channel': channel,
            'packaging_options': packaging_options,
            'packed_at': datetime.utcnow().isoformat(),
            'ready_for_delivery': True
        }
        
        logger.debug(f"Packed torch {torch_id} for {transport_method} delivery")
        return result


class DockmasterCampfire(Campfire):
    """
    Dockmaster campfire that orchestrates torch loading, routing, and packing.
    
    This campfire provides the core functionality for handling torch operations
    in a valley, acting as the primary entry and exit point for torch traffic.
    """
    
    def __init__(self, mcp_broker: IMCPBroker, config: Optional[CampfireConfig] = None):
        """
        Initialize the Dockmaster campfire.
        
        Args:
            mcp_broker: MCP broker for communication
            config: Optional campfire configuration (will create default if not provided)
        """
        if config is None:
            config = self._create_default_config()
        
        super().__init__(config, mcp_broker)
        
        # Initialize campers
        self.loader = LoaderCamper(self._get_camper_config('loader'))
        self.router = RouterCamper(self._get_camper_config('router'))
        self.packer = PackerCamper(self._get_camper_config('packer'))
        
        self._campers = {
            'loader': self.loader,
            'router': self.router,
            'packer': self.packer
        }
        
        logger.info("DockmasterCampfire initialized")
    
    async def start(self) -> None:
        """Start the Dockmaster campfire and all campers"""
        await super().start()
        
        # Start all campers
        for camper_name, camper in self._campers.items():
            await camper.start()
            logger.debug(f"Started {camper_name} camper")
        
        logger.info("DockmasterCampfire started with all campers")
    
    async def stop(self) -> None:
        """Stop the Dockmaster campfire and all campers"""
        # Stop all campers
        for camper_name, camper in self._campers.items():
            await camper.stop()
            logger.debug(f"Stopped {camper_name} camper")
        
        await super().stop()
        logger.info("DockmasterCampfire stopped")
    
    async def process_torch(self, torch: Torch) -> Optional[Torch]:
        """
        Process a torch through the complete Dockmaster pipeline.
        
        Args:
            torch: Incoming torch to process
            
        Returns:
            Optional response torch or None
        """
        if not self._running:
            logger.warning("DockmasterCampfire is not running, cannot process torch")
            return None
        
        logger.info(f"Processing torch {torch.id} through Dockmaster pipeline")
        
        try:
            # Step 1: Load and validate torch
            load_result = await self.loader.process(torch)
            logger.debug(f"Torch {torch.id} loaded: {load_result['status']}")
            
            # Step 2: Route the torch
            route_result = await self.router.process(load_result)
            logger.debug(f"Torch {torch.id} routed: {route_result['routing_strategy']}")
            
            # Step 3: Pack for delivery
            pack_result = await self.packer.process(route_result)
            logger.debug(f"Torch {torch.id} packed: {pack_result['transport_method']}")
            
            # If local delivery, create response with processing results
            if route_result.get('is_local'):
                response_payload = {
                    'dockmaster_processing': {
                        'load_result': load_result,
                        'route_result': route_result,
                        'pack_result': pack_result,
                        'processed_at': datetime.utcnow().isoformat()
                    },
                    'delivery_status': 'local_processed'
                }
                
                response_torch = Torch(
                    id=f"dockmaster_response_{torch.id}",
                    sender_valley=torch.target_address.split(':')[0],
                    target_address=f"{torch.sender_valley}:response",
                    payload=response_payload,
                    signature="dockmaster_signature"  # TODO: Implement proper signing
                )
                
                logger.info(f"Torch {torch.id} processed locally, returning response")
                return response_torch
            
            else:
                # For remote delivery, publish to MCP broker
                delivery_channel = pack_result['delivery_channel']
                torch_message = torch.to_redis_message()
                
                await self.mcp_broker.publish(delivery_channel, torch_message)
                logger.info(f"Torch {torch.id} published to {delivery_channel} for remote delivery")
                
                return None
        
        except Exception as e:
            logger.error(f"Error processing torch {torch.id} in Dockmaster: {e}")
            
            # Create error response
            error_response = Torch(
                id=f"dockmaster_error_{torch.id}",
                sender_valley=torch.target_address.split(':')[0],
                target_address=f"{torch.sender_valley}:error",
                payload={
                    'error': str(e),
                    'error_type': type(e).__name__,
                    'torch_id': torch.id,
                    'timestamp': datetime.utcnow().isoformat()
                },
                signature="dockmaster_error_signature"
            )
            
            return error_response
    
    def _create_default_config(self) -> CampfireConfig:
        """Create default configuration for Dockmaster campfire"""
        return CampfireConfig(
            name="dockmaster",
            runs_on="valley",
            env={
                "DOCKMASTER_MODE": "standard",
                "MAX_TORCH_SIZE": "10485760"  # 10MB
            },
            steps=[
                {
                    "name": "Load and validate torch",
                    "uses": "camper/loader@v1",
                    "with": {
                        "max_torch_size": 10485760,
                        "allowed_valleys": []
                    }
                },
                {
                    "name": "Route torch to destination",
                    "uses": "camper/router@v1", 
                    "with": {
                        "routing_table": {},
                        "default_route": "local"
                    }
                },
                {
                    "name": "Pack torch for delivery",
                    "uses": "camper/packer@v1",
                    "with": {
                        "compression": True,
                        "encryption_required": False
                    }
                }
            ],
            channels=["torch-delivery", "dockmaster-control"],
            auditor_enabled=True
        )
    
    def _get_camper_config(self, camper_name: str) -> Dict[str, Any]:
        """Extract configuration for a specific camper from campfire steps"""
        for step in self.config.steps:
            uses = step.get('uses', '')
            if f'camper/{camper_name}@' in uses:
                return step.get('with', {})
        
        # Return default config if not found
        defaults = {
            'loader': {'max_torch_size': 10485760, 'allowed_valleys': []},
            'router': {'routing_table': {}, 'default_route': 'local'},
            'packer': {'compression': True, 'encryption_required': False}
        }
        
        return defaults.get(camper_name, {})
    
    def get_campers(self) -> Dict[str, ICamper]:
        """Get all active campers"""
        return self._campers.copy()
    
    def __repr__(self) -> str:
        return f"DockmasterCampfire(running={self._running}, campers={len(self._campers)})"
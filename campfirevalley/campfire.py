"""
Base Campfire implementation.
"""

import asyncio
import logging
from typing import Optional, List, Dict, Any
from .interfaces import ICampfire, IMCPBroker
from .models import Torch, CampfireConfig


logger = logging.getLogger(__name__)


class Campfire(ICampfire):
    """
    Base Campfire implementation that can be extended for specific functionality.
    """
    
    def __init__(self, config: CampfireConfig, mcp_broker: IMCPBroker):
        """
        Initialize a Campfire instance.
        
        Args:
            config: Campfire configuration
            mcp_broker: MCP broker for communication
        """
        self.config = config
        self.mcp_broker = mcp_broker
        
        # Runtime state
        self._running = False
        self._subscriptions: Dict[str, Any] = {}
        self._campers: Dict[str, 'ICamper'] = {}
        
        logger.info(f"Campfire '{config.name}' initialized")
    
    async def start(self) -> None:
        """Start the campfire"""
        if self._running:
            logger.warning(f"Campfire '{self.config.name}' is already running")
            return
        
        logger.info(f"Starting campfire '{self.config.name}'...")
        
        try:
            # Subscribe to configured channels
            await self._subscribe_to_channels()
            
            # Initialize campers based on configuration steps
            await self._initialize_campers()
            
            self._running = True
            logger.info(f"Campfire '{self.config.name}' started successfully")
            
        except Exception as e:
            logger.error(f"Failed to start campfire '{self.config.name}': {e}")
            raise
    
    async def stop(self) -> None:
        """Stop the campfire"""
        if not self._running:
            return
        
        logger.info(f"Stopping campfire '{self.config.name}'...")
        
        # Stop all campers
        for camper in self._campers.values():
            await camper.stop()
        
        # Unsubscribe from all channels
        for channel in list(self._subscriptions.keys()):
            await self.mcp_broker.unsubscribe(channel)
        
        self._subscriptions.clear()
        self._campers.clear()
        self._running = False
        
        logger.info(f"Campfire '{self.config.name}' stopped")
    
    async def process_torch(self, torch: Torch) -> Optional[Torch]:
        """Process an incoming torch and optionally return a response"""
        if not self._running:
            logger.warning(f"Campfire '{self.config.name}' is not running, cannot process torch")
            return None
        
        logger.debug(f"Processing torch {torch.id} in campfire '{self.config.name}'")
        
        try:
            # Execute campfire steps in order
            result = await self._execute_steps(torch)
            
            # If there's a result, create response torch
            if result:
                response_torch = Torch(
                    id=f"response_{torch.id}",
                    sender_valley=torch.target_address.split(':')[1].split('/')[0],  # Extract valley name
                    target_address=f"valley:{torch.sender_valley}",
                    payload=result,
                    signature="placeholder_signature"  # TODO: Implement proper signing
                )
                return response_torch
            
            return None
            
        except Exception as e:
            logger.error(f"Error processing torch {torch.id} in campfire '{self.config.name}': {e}")
            return None
    
    def get_config(self) -> CampfireConfig:
        """Get the campfire configuration"""
        return self.config
    
    def get_channels(self) -> List[str]:
        """Get the list of channels this campfire listens to"""
        return self.config.channels.copy()
    
    async def _subscribe_to_channels(self) -> None:
        """Subscribe to configured MCP channels"""
        for channel in self.config.channels:
            await self.mcp_broker.subscribe(channel, self._handle_channel_message)
            self._subscriptions[channel] = True
        
        # Also subscribe to direct campfire channel
        campfire_channel = f"campfire:{self.config.name}"
        await self.mcp_broker.subscribe(campfire_channel, self._handle_torch_message)
        self._subscriptions[campfire_channel] = True
        
        logger.debug(f"Subscribed to {len(self._subscriptions)} channels")
    
    async def _handle_channel_message(self, channel: str, message: Dict[str, Any]) -> None:
        """Handle messages from subscribed channels"""
        try:
            # Convert message to appropriate format and process
            logger.debug(f"Received message on channel {channel}")
            # TODO: Implement channel-specific message handling
        except Exception as e:
            logger.error(f"Error handling channel message on {channel}: {e}")
    
    async def _handle_torch_message(self, channel: str, message: Dict[str, Any]) -> None:
        """Handle torch messages directed at this campfire"""
        try:
            torch = Torch(**message)
            await self.process_torch(torch)
        except Exception as e:
            logger.error(f"Error handling torch message: {e}")
    
    async def _initialize_campers(self) -> None:
        """Initialize campers based on configuration steps"""
        for step in self.config.steps:
            step_name = step.get("name", "unnamed_step")
            uses = step.get("uses", "")
            
            # TODO: Implement camper creation based on 'uses' field
            # This would involve:
            # 1. Parse the 'uses' field (e.g., "camper/loader@v1")
            # 2. Create appropriate camper instance
            # 3. Configure camper with step parameters
            # 4. Start the camper
            
            logger.debug(f"Initialized step '{step_name}' using '{uses}'")
    
    async def _execute_steps(self, torch: Torch) -> Optional[Dict[str, Any]]:
        """Execute campfire steps in sequence"""
        context = {"torch": torch, "outputs": {}}
        
        for step in self.config.steps:
            step_name = step.get("name", "unnamed_step")
            
            # Check if step should be executed (if condition)
            if not self._should_execute_step(step, context):
                logger.debug(f"Skipping step '{step_name}' due to condition")
                continue
            
            try:
                # Execute step
                step_result = await self._execute_step(step, context)
                
                # Store step outputs
                if step_result:
                    context["outputs"][step_name] = step_result
                
                logger.debug(f"Executed step '{step_name}' successfully")
                
            except Exception as e:
                logger.error(f"Error executing step '{step_name}': {e}")
                # Depending on configuration, might want to continue or stop
                break
        
        return context.get("outputs")
    
    def _should_execute_step(self, step: Dict[str, Any], context: Dict[str, Any]) -> bool:
        """Check if a step should be executed based on its condition"""
        condition = step.get("if")
        if not condition:
            return True
        
        # TODO: Implement condition evaluation
        # This would parse GitHub Actions-style conditions like:
        # - "${{ env.security_level == 'high' }}"
        # - "${{ matrix.tech_stack == 'fastapi' }}"
        
        # For now, always execute
        return True
    
    async def _execute_step(self, step: Dict[str, Any], context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Execute a single campfire step"""
        uses = step.get("uses", "")
        step_with = step.get("with", {})
        
        # TODO: Implement actual step execution
        # This would involve:
        # 1. Parse the 'uses' field to determine action type
        # 2. Execute the appropriate camper or action
        # 3. Pass parameters from 'with' section
        # 4. Return results for use in subsequent steps
        
        # Placeholder implementation
        return {"status": "completed", "step": step.get("name")}
    
    def is_running(self) -> bool:
        """Check if the campfire is running"""
        return self._running
    
    def get_campers(self) -> Dict[str, 'ICamper']:
        """Get all active campers"""
        return self._campers.copy()
    
    def __repr__(self) -> str:
        return f"Campfire(name='{self.config.name}', running={self._running}, campers={len(self._campers)})"


class ICamper:
    """Base interface for campers (workers within campfires)"""
    
    async def start(self) -> None:
        """Start the camper"""
        pass
    
    async def stop(self) -> None:
        """Stop the camper"""
        pass
    
    async def process(self, data: Any) -> Any:
        """Process data and return result"""
        pass
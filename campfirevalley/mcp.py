"""
MCP (Message Communication Protocol) broker implementation using Redis.
"""

import asyncio
import logging
from typing import Dict, List, Any, Callable, Optional, Set
import json
import time
from datetime import datetime, timedelta
from .interfaces import IMCPBroker

try:
    import redis.asyncio as redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

logger = logging.getLogger(__name__)


class RedisMCPBroker(IMCPBroker):
    """
    Redis-based MCP broker implementation for inter-valley communication.
    
    Enhanced with federation support:
    - Priority message queues
    - Federation channel management
    - Message routing and filtering
    - Connection pooling and failover
    """
    
    def __init__(self, connection_string: str = 'redis://localhost:6379', valley_name: str = None):
        """
        Initialize Redis MCP broker.
        
        Args:
            connection_string: Redis connection string
            valley_name: Name of this valley for federation routing
        """
        self.connection_string = connection_string
        self.valley_name = valley_name or "unknown_valley"
        self._redis_client = None
        self._pubsub = None
        self._connected = False
        self._subscriptions: Dict[str, Callable] = {}
        self._listener_task: Optional[asyncio.Task] = None
        
        # Federation-specific attributes
        self._federation_channels: Set[str] = set()
        self._priority_queues: Dict[str, str] = {}  # channel -> priority queue name
        self._message_stats: Dict[str, int] = {"sent": 0, "received": 0, "errors": 0}
        self._last_heartbeat: Optional[datetime] = None
        self._heartbeat_task: Optional[asyncio.Task] = None
        
        logger.info(f"Redis MCP broker initialized for valley '{self.valley_name}' with connection: {connection_string}")
    
    async def connect(self) -> bool:
        """Connect to the MCP broker"""
        if self._connected:
            logger.warning("Already connected to Redis MCP broker")
            return True
        
        if not REDIS_AVAILABLE:
            logger.error("Redis library not available. Install with: pip install redis")
            return False
        
        try:
            # Initialize Redis client with connection pooling
            self._redis_client = redis.from_url(
                self.connection_string,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True,
                health_check_interval=30
            )
            
            # Test connection
            await self._redis_client.ping()
            
            # Initialize pub/sub
            self._pubsub = self._redis_client.pubsub()
            
            self._connected = True
            
            # Start message listener
            self._listener_task = asyncio.create_task(self._message_listener())
            
            # Start heartbeat for federation health monitoring
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
            
            # Initialize federation channels
            await self._setup_federation_channels()
            
            logger.info("Connected to Redis MCP broker with federation support")
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect to Redis MCP broker: {e}")
            self._connected = False
            return False
    
    async def disconnect(self) -> bool:
        """Disconnect from the MCP broker"""
        if not self._connected:
            logger.warning("Not connected to Redis MCP broker")
            return True
        
        try:
            # Mark as disconnected first to stop listener
            self._connected = False
            
            # Cancel background tasks
            tasks_to_cancel = [self._listener_task, self._heartbeat_task]
            for task in tasks_to_cancel:
                if task:
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
            
            self._listener_task = None
            self._heartbeat_task = None
            
            # Close Redis connections
            if self._pubsub:
                await self._pubsub.close()
                self._pubsub = None
                
            if self._redis_client:
                await self._redis_client.close()
                self._redis_client = None
            
            # Clear subscriptions and federation data
            self._subscriptions.clear()
            self._federation_channels.clear()
            self._priority_queues.clear()
            
            logger.info("Disconnected from Redis MCP broker")
            return True
            
        except Exception as e:
            logger.error(f"Error disconnecting from Redis MCP broker: {e}")
            return False
    
    async def subscribe(self, channel: str, callback: Callable) -> bool:
        """Subscribe to a channel with a callback function"""
        if not self._connected:
            raise RuntimeError("Must connect to broker before subscribing")
        
        try:
            # Subscribe to Redis channel
            await self._pubsub.subscribe(channel)
            
            # Store callback for message dispatching
            self._subscriptions[channel] = callback
            
            logger.debug(f"Subscribed to channel: {channel}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to subscribe to channel {channel}: {e}")
            return False
    
    async def unsubscribe(self, channel: str) -> bool:
        """Unsubscribe from a channel"""
        if channel not in self._subscriptions:
            logger.warning(f"Not subscribed to channel: {channel}")
            return False
        
        try:
            # Unsubscribe from Redis channel
            await self._pubsub.unsubscribe(channel)
            
            # Remove callback
            del self._subscriptions[channel]
            
            logger.debug(f"Unsubscribed from channel: {channel}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to unsubscribe from channel {channel}: {e}")
            return False
    
    async def publish(self, channel: str, message: Any, priority: str = "normal", 
                     target_valley: str = None) -> bool:
        """
        Publish a message to a channel with federation support.
        
        Args:
            channel: Channel name
            message: Message to publish
            priority: Message priority ("high", "normal", "low")
            target_valley: Specific valley to route to (optional)
            
        Returns:
            True if published successfully
        """
        if not self._connected or not self._redis_client:
            logger.error("Not connected to Redis")
            self._message_stats["errors"] += 1
            return False
            
        try:
            # Enhance message with federation metadata
            enhanced_message = {
                "content": message,
                "source_valley": self.valley_name,
                "target_valley": target_valley,
                "priority": priority,
                "timestamp": datetime.utcnow().isoformat(),
                "message_id": f"{self.valley_name}_{int(time.time() * 1000)}"
            }
            
            # Serialize message to JSON
            serialized_message = json.dumps(enhanced_message)
            
            # Handle priority routing
            if priority == "high" and channel in self._priority_queues:
                # Use priority queue for high-priority messages
                priority_queue = self._priority_queues[channel]
                await self._redis_client.lpush(priority_queue, serialized_message)
                logger.debug(f"Published high-priority message to queue '{priority_queue}'")
            else:
                # Standard pub/sub for normal messages
                await self._redis_client.publish(channel, serialized_message)
                logger.debug(f"Published message to channel '{channel}'")
            
            # Update statistics
            self._message_stats["sent"] += 1
            return True
            
        except Exception as e:
            logger.error(f"Failed to publish message to channel '{channel}': {e}")
            self._message_stats["errors"] += 1
            return False
    
    async def get_subscribers(self, channel: str) -> List[str]:
        """Get list of subscribers for a channel"""
        if not self._connected:
            raise RuntimeError("Must connect to broker before getting subscribers")
        
        try:
            # Get channel info from Redis
            # Note: Redis doesn't provide subscriber identities for security,
            # but we can get the subscriber count
            info = await self._redis_client.pubsub_numsub(channel)
            subscriber_count = info.get(channel, 0) if isinstance(info, dict) else 0
            
            # Return list of anonymous subscriber identifiers
            return [f"subscriber_{i}" for i in range(subscriber_count)]
            
        except Exception as e:
            logger.error(f"Failed to get subscribers for channel {channel}: {e}")
            return []
    
    def is_connected(self) -> bool:
        """Check if connected to the broker"""
        return self._connected
    
    async def _message_listener(self):
        """Background task to listen for messages and dispatch to callbacks"""
        logger.debug("Starting message listener")
        
        try:
            while self._connected:
                try:
                    # Listen for Redis messages
                    async for message in self._pubsub.listen():
                        if message['type'] == 'message':
                            channel = message['channel']
                            
                            try:
                                # Parse JSON message data
                                data = json.loads(message['data'])
                                
                                # Dispatch to registered callback
                                if channel in self._subscriptions:
                                    callback = self._subscriptions[channel]
                                    # Run callback in background to avoid blocking listener
                                    asyncio.create_task(callback(channel, data))
                                    
                                # Update statistics
                                self._message_stats["received"] += 1
                                    
                            except json.JSONDecodeError as e:
                                logger.error(f"Failed to decode message from {channel}: {e}")
                                self._message_stats["errors"] += 1
                            except Exception as e:
                                logger.error(f"Error in callback for {channel}: {e}")
                                self._message_stats["errors"] += 1
                                
                except Exception as e:
                    if self._connected:  # Only log if we're still supposed to be connected
                        logger.error(f"Error in message listener: {e}")
                        self._message_stats["errors"] += 1
                        await asyncio.sleep(1)  # Brief pause before retrying
                
        except asyncio.CancelledError:
            logger.debug("Message listener cancelled")
        except Exception as e:
            logger.error(f"Fatal error in message listener: {e}")
            self._message_stats["errors"] += 1
        finally:
            logger.debug("Message listener stopped")
    
    async def _setup_federation_channels(self):
        """Setup federation-specific channels and queues."""
        try:
            # Create federation discovery channel
            federation_channel = f"federation.{self.valley_name}"
            self._federation_channels.add(federation_channel)
            
            # Setup priority queues for critical channels
            critical_channels = ["torch.routing", "federation.discovery", "valley.emergency"]
            for channel in critical_channels:
                priority_queue = f"{channel}.priority"
                self._priority_queues[channel] = priority_queue
                
            logger.info(f"Federation channels setup complete for valley '{self.valley_name}'")
            
        except Exception as e:
            logger.error(f"Failed to setup federation channels: {e}")
    
    async def _heartbeat_loop(self):
        """Periodic heartbeat for federation health monitoring."""
        try:
            while self._connected:
                try:
                    # Send heartbeat
                    heartbeat_data = {
                        "valley_name": self.valley_name,
                        "timestamp": datetime.utcnow().isoformat(),
                        "stats": self._message_stats.copy()
                    }
                    
                    await self.publish("federation.heartbeat", heartbeat_data, priority="low")
                    self._last_heartbeat = datetime.utcnow()
                    
                    # Wait for next heartbeat (30 seconds)
                    await asyncio.sleep(30)
                    
                except Exception as e:
                    logger.error(f"Heartbeat error: {e}")
                    await asyncio.sleep(5)  # Shorter retry interval on error
                    
        except asyncio.CancelledError:
            logger.info("Heartbeat loop cancelled")
        except Exception as e:
            logger.error(f"Heartbeat loop error: {e}")
    
    async def create_priority_queue(self, channel: str) -> bool:
        """
        Create a priority queue for a specific channel.
        
        Args:
            channel: Channel name to create priority queue for
            
        Returns:
            True if created successfully
        """
        try:
            priority_queue = f"{channel}.priority"
            self._priority_queues[channel] = priority_queue
            
            logger.info(f"Created priority queue '{priority_queue}' for channel '{channel}'")
            return True
            
        except Exception as e:
            logger.error(f"Failed to create priority queue for channel '{channel}': {e}")
            return False
    
    async def get_message_stats(self) -> Dict[str, Any]:
        """
        Get message statistics and broker health information.
        
        Returns:
            Dictionary containing statistics and health info
        """
        return {
            "valley_name": self.valley_name,
            "connected": self._connected,
            "last_heartbeat": self._last_heartbeat.isoformat() if self._last_heartbeat else None,
            "message_stats": self._message_stats.copy(),
            "active_subscriptions": len(self._subscriptions),
            "federation_channels": len(self._federation_channels),
            "priority_queues": len(self._priority_queues)
        }
    
    async def subscribe_to_federation(self, federation_name: str, callback: Callable) -> bool:
        """
        Subscribe to federation-wide communications.
        
        Args:
            federation_name: Name of the federation
            callback: Function to call when messages are received
            
        Returns:
            True if subscribed successfully
        """
        federation_channel = f"federation.{federation_name}"
        return await self.subscribe(federation_channel, callback)
    
    async def publish_to_federation(self, federation_name: str, message: Any, 
                                  priority: str = "normal") -> bool:
        """
        Publish a message to all valleys in a federation.
        
        Args:
            federation_name: Name of the federation
            message: Message to publish
            priority: Message priority
            
        Returns:
            True if published successfully
        """
        federation_channel = f"federation.{federation_name}"
        return await self.publish(federation_channel, message, priority=priority)
    
    def __repr__(self) -> str:
        return f"RedisMCPBroker(connected={self._connected}, subscriptions={len(self._subscriptions)})"
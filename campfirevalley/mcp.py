"""
MCP (Message Communication Protocol) broker implementation using Redis.
"""

import asyncio
import logging
from typing import Dict, List, Any, Callable, Optional
import json
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
    """
    
    def __init__(self, connection_string: str = 'redis://localhost:6379'):
        """
        Initialize Redis MCP broker.
        
        Args:
            connection_string: Redis connection string
        """
        self.connection_string = connection_string
        self._redis_client = None
        self._pubsub = None
        self._connected = False
        self._subscriptions: Dict[str, Callable] = {}
        self._listener_task: Optional[asyncio.Task] = None
        
        logger.info(f"Redis MCP broker initialized with connection: {connection_string}")
    
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
            
            logger.info("Connected to Redis MCP broker")
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
            
            # Cancel message listener
            if self._listener_task:
                self._listener_task.cancel()
                try:
                    await self._listener_task
                except asyncio.CancelledError:
                    pass
                self._listener_task = None
            
            # Close Redis connections
            if self._pubsub:
                await self._pubsub.close()
                self._pubsub = None
                
            if self._redis_client:
                await self._redis_client.close()
                self._redis_client = None
            
            # Clear subscriptions
            self._subscriptions.clear()
            
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
    
    async def publish(self, channel: str, message: Dict[str, Any]) -> bool:
        """Publish a message to a channel"""
        if not self._connected:
            raise RuntimeError("Must connect to broker before publishing")
        
        try:
            # Serialize message to JSON
            message_json = json.dumps(message, default=str)
            
            # Publish to Redis channel
            await self._redis_client.publish(channel, message_json)
            
            logger.debug(f"Published message to channel: {channel}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to publish to channel {channel}: {e}")
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
                                    
                            except json.JSONDecodeError as e:
                                logger.error(f"Failed to decode message from {channel}: {e}")
                            except Exception as e:
                                logger.error(f"Error in callback for {channel}: {e}")
                                
                except Exception as e:
                    if self._connected:  # Only log if we're still supposed to be connected
                        logger.error(f"Error in message listener: {e}")
                        await asyncio.sleep(1)  # Brief pause before retrying
                
        except asyncio.CancelledError:
            logger.debug("Message listener cancelled")
        except Exception as e:
            logger.error(f"Fatal error in message listener: {e}")
        finally:
            logger.debug("Message listener stopped")
    
    def __repr__(self) -> str:
        return f"RedisMCPBroker(connected={self._connected}, subscriptions={len(self._subscriptions)})"
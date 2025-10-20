"""
Base interfaces for CampfireValley components.
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, List, Any
from .models import Torch, ValleyConfig, CampfireConfig, CommunityMembership


class IValley(ABC):
    """Interface for Valley manager component"""
    
    @abstractmethod
    async def start(self) -> None:
        """Start the valley and all its components"""
        pass
    
    @abstractmethod
    async def stop(self) -> None:
        """Stop the valley and cleanup resources"""
        pass
    
    @abstractmethod
    async def join_community(self, community_name: str, key: str) -> bool:
        """Join a community with the given name and key"""
        pass
    
    @abstractmethod
    async def leave_community(self, community_name: str) -> bool:
        """Leave a community"""
        pass
    
    @abstractmethod
    async def provision_campfire(self, campfire_config: CampfireConfig) -> bool:
        """Provision a new campfire from configuration"""
        pass
    
    @abstractmethod
    def get_config(self) -> ValleyConfig:
        """Get the valley configuration"""
        pass


class IDock(ABC):
    """Interface for Dock gateway component"""
    
    @abstractmethod
    async def start_gateway(self) -> None:
        """Start the dock gateway"""
        pass
    
    @abstractmethod
    async def stop_gateway(self) -> None:
        """Stop the dock gateway"""
        pass
    
    @abstractmethod
    async def handle_incoming_torch(self, torch: Torch) -> None:
        """Handle an incoming torch from another valley"""
        pass
    
    @abstractmethod
    async def send_torch(self, target_address: str, torch: Torch) -> bool:
        """Send a torch to the specified target address"""
        pass
    
    @abstractmethod
    async def broadcast_discovery(self) -> None:
        """Broadcast discovery information to the community"""
        pass
    
    @abstractmethod
    async def validate_sender(self, torch: Torch) -> bool:
        """Validate the sender of a torch"""
        pass


class ICampfire(ABC):
    """Interface for Campfire component"""
    
    @abstractmethod
    async def start(self) -> None:
        """Start the campfire"""
        pass
    
    @abstractmethod
    async def stop(self) -> None:
        """Stop the campfire"""
        pass
    
    @abstractmethod
    async def process_torch(self, torch: Torch) -> Optional[Torch]:
        """Process an incoming torch and optionally return a response"""
        pass
    
    @abstractmethod
    def get_config(self) -> CampfireConfig:
        """Get the campfire configuration"""
        pass
    
    @abstractmethod
    def get_channels(self) -> List[str]:
        """Get the list of channels this campfire listens to"""
        pass


class IPartyBox(ABC):
    """Interface for Party Box storage system"""
    
    @abstractmethod
    async def store_attachment(self, attachment_id: str, content: bytes) -> str:
        """Store an attachment and return its storage path"""
        pass
    
    @abstractmethod
    async def retrieve_attachment(self, attachment_id: str) -> Optional[bytes]:
        """Retrieve an attachment by its ID"""
        pass
    
    @abstractmethod
    async def delete_attachment(self, attachment_id: str) -> bool:
        """Delete an attachment"""
        pass
    
    @abstractmethod
    async def list_attachments(self, category: str = "all") -> List[str]:
        """List attachments in a category (incoming, outgoing, quarantine, attachments)"""
        pass
    
    @abstractmethod
    async def move_to_quarantine(self, attachment_id: str) -> bool:
        """Move an attachment to quarantine"""
        pass
    
    @abstractmethod
    async def cleanup_old_attachments(self, max_age_days: int = 30) -> int:
        """Clean up old attachments and return count of deleted items"""
        pass


class IMCPBroker(ABC):
    """Interface for MCP (Message Communication Protocol) broker"""
    
    @abstractmethod
    async def connect(self) -> bool:
        """Connect to the MCP broker"""
        pass
    
    @abstractmethod
    async def disconnect(self) -> None:
        """Disconnect from the MCP broker"""
        pass
    
    @abstractmethod
    async def subscribe(self, channel: str, callback) -> bool:
        """Subscribe to a channel with a callback function"""
        pass
    
    @abstractmethod
    async def unsubscribe(self, channel: str) -> bool:
        """Unsubscribe from a channel"""
        pass
    
    @abstractmethod
    async def publish(self, channel: str, message: Dict[str, Any]) -> bool:
        """Publish a message to a channel"""
        pass
    
    @abstractmethod
    async def get_subscribers(self, channel: str) -> List[str]:
        """Get list of subscribers for a channel"""
        pass
    
    @abstractmethod
    def is_connected(self) -> bool:
        """Check if connected to the broker"""
        pass


class IKeyManager(ABC):
    """Interface for cryptographic key management"""
    
    @abstractmethod
    async def generate_key_pair(self) -> tuple[str, str]:
        """Generate a new public/private key pair"""
        pass
    
    @abstractmethod
    async def store_key(self, key_id: str, key_data: str, key_type: str = "shared") -> bool:
        """Store a key securely"""
        pass
    
    @abstractmethod
    async def retrieve_key(self, key_id: str) -> Optional[str]:
        """Retrieve a stored key"""
        pass
    
    @abstractmethod
    async def delete_key(self, key_id: str) -> bool:
        """Delete a stored key"""
        pass
    
    @abstractmethod
    async def rotate_keys(self, community_name: str) -> bool:
        """Rotate keys for a community"""
        pass
    
    @abstractmethod
    async def sign_torch(self, torch: Torch, private_key: str) -> str:
        """Sign a torch with a private key"""
        pass
    
    @abstractmethod
    async def verify_signature(self, torch: Torch, public_key: str) -> bool:
        """Verify a torch signature with a public key"""
        pass


class ISanitizer(ABC):
    """Interface for content sanitization and security scanning"""
    
    @abstractmethod
    async def scan_content(self, content: Dict[str, Any]) -> 'ScanResult':
        """Scan content for security issues"""
        pass
    
    @abstractmethod
    async def filter_content(self, content: Dict[str, Any]) -> Dict[str, Any]:
        """Filter and clean content"""
        pass
    
    @abstractmethod
    async def is_content_safe(self, content: Dict[str, Any]) -> bool:
        """Quick check if content is safe"""
        pass


class IJustice(ABC):
    """Interface for justice and access control operations"""
    
    @abstractmethod
    async def handle_violation(self, violation: 'Violation') -> 'Action':
        """Handle a security or policy violation"""
        pass
    
    @abstractmethod
    async def review_quarantine_item(self, item_id: str) -> 'Decision':
        """Review an item in quarantine"""
        pass
    
    @abstractmethod
    async def manage_community_access(self, valley_id: str, action: str) -> bool:
        """Manage access for a valley in the community"""
        pass
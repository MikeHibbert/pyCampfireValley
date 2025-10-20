"""CampfireValley - A distributed torch processing framework

CampfireValley provides a secure, scalable platform for processing and routing
"torches" (data packets) across a network of valleys (nodes) using campfires
(processing units) and campers (workers).
"""

from .models import *
from .interfaces import *
from .config import ValleyConfig, CampfireConfig
from .valley import Valley
from .campfire import Campfire
from .mcp import RedisMCPBroker
from .key_manager import CampfireKeyManager, IKeyManager
from . import campfires

__version__ = "0.1.0"

__all__ = [
    # Core classes
    "Valley",
    "Campfire", 
    "RedisMCPBroker",
    "CampfireKeyManager",
    
    # Default campfires
    "campfires",
    
    # Interfaces
    "ICampfire",
    "IValley", 
    "IDock",
    "IPartyBox",
    "IMCPBroker",
    "IKeyManager",
    "ISanitizer",
    "IJustice",
    
    # Models
    "Torch",
    "ValleyConfig",
    "CampfireConfig",
    "CommunityMembership",
    "VALIServiceRequest", 
    "VALIServiceResponse",
    "ScanResult",
    "Violation",
    "Action",
    "Decision",
    "DockMode",
    "SecurityLevel",
    "TrustLevel",
]
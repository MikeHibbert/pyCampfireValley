"""
Web interface data models for node-based visualization
"""

from enum import Enum
from typing import Dict, List, Optional, Any
from pydantic import BaseModel
from datetime import datetime


class NodeType(str, Enum):
    """Types of nodes in the visualization"""
    VALLEY = "valley"
    DOCK = "dock"
    CAMPFIRE = "campfire"
    CAMPER = "camper"
    TORCH = "torch"


class NodeStatus(str, Enum):
    """Status states for nodes"""
    ACTIVE = "active"
    IDLE = "idle"
    BUSY = "busy"
    ERROR = "error"
    OFFLINE = "offline"
    STARTING = "starting"
    STOPPING = "stopping"


class ConnectionType(str, Enum):
    """Types of connections between nodes"""
    TORCH_FLOW = "torch_flow"
    MANAGEMENT = "management"
    FEDERATION = "federation"
    HEALTH_CHECK = "health_check"


class Position(BaseModel):
    """2D position for node placement"""
    x: float
    y: float


class NodeData(BaseModel):
    """Base data structure for visualization nodes"""
    id: str
    type: NodeType
    status: NodeStatus
    position: Position
    label: str
    metadata: Dict[str, Any] = {}
    
    # Visual properties
    color: Optional[str] = None
    size: Optional[float] = None
    icon: Optional[str] = None
    
    # Hierarchy
    parent_id: Optional[str] = None
    children_ids: List[str] = []


class ValleyNode(NodeData):
    """Valley node with specific properties"""
    type: NodeType = NodeType.VALLEY
    total_campfires: int = 0
    active_campfires: int = 0
    total_torches: int = 0
    health_score: float = 1.0
    federation_status: str = "disconnected"


class CampfireNode(NodeData):
    """Campfire node with specific properties"""
    type: NodeType = NodeType.CAMPFIRE
    campfire_type: str  # "dockmaster", "sanitizer", "justice", etc.
    camper_count: int = 0
    active_campers: int = 0
    torch_queue_size: int = 0
    processing_time_avg: float = 0.0
    last_activity: Optional[datetime] = None
    
    # Enhanced details
    current_jobs: List[Dict[str, Any]] = []  # Current tasks being processed
    party_box_data: Dict[str, Any] = {}  # Party box contents
    input_queue: List[Dict[str, Any]] = []  # Input data queue
    output_queue: List[Dict[str, Any]] = []  # Output data queue
    active_camper_details: List[Dict[str, Any]] = []  # Detailed camper information
    torch_processing_status: Dict[str, Any] = {}  # Current torch processing status
    performance_metrics: Dict[str, float] = {}  # Performance metrics
    error_count: int = 0  # Recent error count
    success_rate: float = 1.0  # Success rate percentage


class CamperNode(NodeData):
    """Camper node with specific properties"""
    type: NodeType = NodeType.CAMPER
    camper_type: str  # "loader", "router", "scanner", etc.
    current_task: Optional[str] = None
    tasks_completed: int = 0
    cpu_usage: float = 0.0
    memory_usage: float = 0.0


class TorchNode(NodeData):
    """Torch node for message visualization"""
    type: NodeType = NodeType.TORCH
    torch_id: str
    sender: str
    recipient: str
    content_type: str
    priority: int = 0
    created_at: datetime
    size_bytes: int = 0


class Connection(BaseModel):
    """Connection between nodes"""
    id: str
    source_id: str
    target_id: str
    type: ConnectionType
    
    # Visual properties
    color: Optional[str] = None
    width: Optional[float] = None
    animated: bool = False
    
    # Data properties
    message_count: int = 0
    last_message: Optional[datetime] = None
    bandwidth_usage: float = 0.0


class TorchFlow(Connection):
    """Specific connection for torch movement"""
    type: ConnectionType = ConnectionType.TORCH_FLOW
    torch_ids: List[str] = []
    flow_rate: float = 0.0  # messages per second
    avg_latency: float = 0.0  # milliseconds


class VisualizationState(BaseModel):
    """Complete state of the visualization"""
    nodes: List[NodeData] = []
    connections: List[Connection] = []
    viewport: Dict[str, float] = {"x": 0, "y": 0, "zoom": 1.0}
    selected_node_id: Optional[str] = None
    timestamp: datetime = datetime.now()


class NodeUpdate(BaseModel):
    """Update message for real-time node changes"""
    node_id: str
    updates: Dict[str, Any]
    timestamp: datetime = datetime.now()


class ConnectionUpdate(BaseModel):
    """Update message for real-time connection changes"""
    connection_id: str
    updates: Dict[str, Any]
    timestamp: datetime = datetime.now()


class WebSocketMessage(BaseModel):
    """WebSocket message structure"""
    type: str  # "node_update", "connection_update", "full_state", etc.
    data: Dict[str, Any]
    timestamp: datetime = datetime.now()
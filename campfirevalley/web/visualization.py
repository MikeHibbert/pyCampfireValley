"""
Valley visualization engine for converting CampfireValley components to node-based representation
"""

import asyncio
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime
import math

from ..valley import Valley
from ..campfire import Campfire
from .models import (
    VisualizationState, NodeData, Connection, ValleyNode, CampfireNode, 
    CamperNode, TorchFlow, Position, NodeType, NodeStatus, ConnectionType
)


class ValleyVisualizer:
    """Converts CampfireValley components into visual node representation"""
    
    def __init__(self, valley: Valley):
        self.valley = valley
        self.last_update = datetime.now()
        self.node_positions: Dict[str, Position] = {}
        
    async def get_current_state(self) -> VisualizationState:
        """Generate current visualization state from valley"""
        nodes = []
        connections = []
        
        # Create valley node
        valley_node = await self._create_valley_node()
        nodes.append(valley_node)
        
        # Create campfire nodes
        campfire_nodes = await self._create_campfire_nodes()
        nodes.extend(campfire_nodes)
        
        # Create camper nodes (when zoomed in)
        camper_nodes = await self._create_camper_nodes()
        nodes.extend(camper_nodes)
        
        # Create connections
        torch_connections = await self._create_torch_connections()
        connections.extend(torch_connections)
        
        management_connections = await self._create_management_connections()
        connections.extend(management_connections)
        
        return VisualizationState(
            nodes=nodes,
            connections=connections,
            timestamp=datetime.now()
        )
    
    async def _create_valley_node(self) -> ValleyNode:
        """Create the main valley node"""
        valley_id = f"valley_{self.valley.name}"
        
        # Calculate valley metrics
        total_campfires = len(self.valley.campfires)
        active_campfires = sum(1 for cf in self.valley.campfires.values() if hasattr(cf, '_running') and cf._running)
        
        # Position valley node at center
        position = self._get_or_create_position(valley_id, Position(x=0, y=0))
        
        return ValleyNode(
            id=valley_id,
            label=self.valley.name,
            position=position,
            status=NodeStatus.ACTIVE if self.valley._running else NodeStatus.OFFLINE,
            total_campfires=total_campfires,
            active_campfires=active_campfires,
            health_score=await self._calculate_valley_health(),
            federation_status="connected" if self.valley.dock else "disconnected",
            color="#4A90E2",  # Blue for valley
            size=100.0,
            icon="🏔️"
        )
    
    async def _create_campfire_nodes(self) -> List[CampfireNode]:
        """Create nodes for all campfires"""
        nodes = []
        valley_id = f"valley_{self.valley.name}"
        
        # Arrange campfires in a circle around the valley
        campfire_count = len(self.valley.campfires)
        radius = 200.0
        
        for i, (campfire_name, campfire) in enumerate(self.valley.campfires.items()):
            # Calculate position in circle
            angle = (2 * math.pi * i) / campfire_count if campfire_count > 0 else 0
            x = radius * math.cos(angle)
            y = radius * math.sin(angle)
            
            campfire_id = f"campfire_{campfire_name}"
            position = self._get_or_create_position(campfire_id, Position(x=x, y=y))
            
            # Determine campfire type and color
            campfire_type = self._get_campfire_type(campfire)
            color = self._get_campfire_color(campfire_type)
            
            # Get campfire metrics
            camper_count = len(getattr(campfire, 'campers', []))
            active_campers = await self._count_active_campers(campfire)
            
            node = CampfireNode(
                id=campfire_id,
                label=campfire.name,
                position=position,
                status=await self._get_campfire_status(campfire),
                parent_id=valley_id,
                campfire_type=campfire_type,
                camper_count=camper_count,
                active_campers=active_campers,
                torch_queue_size=await self._get_torch_queue_size(campfire),
                processing_time_avg=await self._get_avg_processing_time(campfire),
                last_activity=await self._get_last_activity(campfire),
                color=color,
                size=60.0,
                icon=self._get_campfire_icon(campfire_type),
                
                # Enhanced details
                current_jobs=await self._get_current_jobs(campfire),
                party_box_data=await self._get_party_box_data(campfire),
                input_queue=await self._get_input_queue(campfire),
                output_queue=await self._get_output_queue(campfire),
                active_camper_details=await self._get_active_camper_details(campfire),
                torch_processing_status=await self._get_torch_processing_status(campfire),
                performance_metrics=await self._get_performance_metrics(campfire),
                error_count=await self._get_error_count(campfire),
                success_rate=await self._get_success_rate(campfire)
            )
            
            nodes.append(node)
        
        return nodes
    
    async def _create_camper_nodes(self) -> List[CamperNode]:
        """Create nodes for campers (shown when zoomed into a campfire)"""
        nodes = []
        
        for campfire_name, campfire in self.valley.campfires.items():
            campfire_id = f"campfire_{campfire_name}"
            campers = getattr(campfire, 'campers', [])
            
            # Arrange campers around their campfire
            camper_count = len(campers)
            radius = 80.0
            
            # Get campfire position
            campfire_pos = self.node_positions.get(campfire_id, Position(x=0, y=0))
            
            for i, camper in enumerate(campers):
                # Calculate position around campfire
                angle = (2 * math.pi * i) / camper_count if camper_count > 0 else 0
                x = campfire_pos.x + radius * math.cos(angle)
                y = campfire_pos.y + radius * math.sin(angle)
                
                camper_id = f"camper_{camper.id}"
                position = self._get_or_create_position(camper_id, Position(x=x, y=y))
                
                # Get camper type and status
                camper_type = self._get_camper_type(camper)
                
                node = CamperNode(
                    id=camper_id,
                    label=camper.id,
                    position=position,
                    status=await self._get_camper_status(camper),
                    parent_id=campfire_id,
                    camper_type=camper_type,
                    current_task=await self._get_current_task(camper),
                    tasks_completed=await self._get_tasks_completed(camper),
                    cpu_usage=await self._get_cpu_usage(camper),
                    memory_usage=await self._get_memory_usage(camper),
                    color=self._get_camper_color(camper_type),
                    size=30.0,
                    icon=self._get_camper_icon(camper_type)
                )
                
                nodes.append(node)
        
        return nodes
    
    async def _create_torch_connections(self) -> List[TorchFlow]:
        """Create connections showing torch flow between campfires"""
        connections = []
        
        # For now, create sample connections
        # In a real implementation, this would track actual torch routing
        campfires = list(self.valley.campfires.items())
        
        for i, (source_name, source_campfire) in enumerate(campfires):
            for j, (target_name, target_campfire) in enumerate(campfires):
                if i != j:  # Don't connect to self
                    connection_id = f"torch_flow_{source_name}_{target_name}"
                    
                    connection = TorchFlow(
                        id=connection_id,
                        source_id=f"campfire_{source_name}",
                        target_id=f"campfire_{target_name}",
                        color="#FF6B6B",  # Red for torch flow
                        width=2.0,
                        animated=True,
                        flow_rate=await self._get_flow_rate(source_campfire, target_campfire),
                        avg_latency=await self._get_avg_latency(source_campfire, target_campfire)
                    )
                    
                    connections.append(connection)
        
        return connections
    
    async def _create_management_connections(self) -> List[Connection]:
        """Create connections for management/control relationships"""
        connections = []
        valley_id = f"valley_{self.valley.name}"
        
        # Connect valley to all campfires
        for campfire_name, campfire in self.valley.campfires.items():
            campfire_id = f"campfire_{campfire_name}"
            
            connection = Connection(
                id=f"mgmt_{valley_id}_{campfire_id}",
                source_id=valley_id,
                target_id=campfire_id,
                type=ConnectionType.MANAGEMENT,
                color="#888888",  # Gray for management
                width=1.0,
                animated=False
            )
            
            connections.append(connection)
        
        return connections
    
    def _get_or_create_position(self, node_id: str, default: Position) -> Position:
        """Get existing position or create new one"""
        if node_id not in self.node_positions:
            self.node_positions[node_id] = default
        return self.node_positions[node_id]
    
    def _get_campfire_type(self, campfire: Campfire) -> str:
        """Determine campfire type from class name or configuration"""
        class_name = campfire.__class__.__name__.lower()
        if "dockmaster" in class_name:
            return "dockmaster"
        elif "sanitizer" in class_name:
            return "sanitizer"
        elif "justice" in class_name:
            return "justice"
        elif "validator" in class_name:
            return "validator"
        elif "router" in class_name:
            return "router"
        else:
            return "generic"
    
    def _get_campfire_color(self, campfire_type: str) -> str:
        """Get color for campfire type"""
        colors = {
            "dockmaster": "#4A90E2",  # Blue
            "sanitizer": "#7ED321",  # Green
            "justice": "#D0021B",     # Red
            "validator": "#F5A623",   # Orange
            "router": "#9013FE",      # Purple
            "generic": "#50E3C2"      # Teal
        }
        return colors.get(campfire_type, "#50E3C2")
    
    def _get_campfire_icon(self, campfire_type: str) -> str:
        """Get icon for campfire type"""
        icons = {
            "dockmaster": "🚢",
            "sanitizer": "🧹",
            "justice": "⚖️",
            "validator": "✅",
            "router": "🔀",
            "generic": "🔥"
        }
        return icons.get(campfire_type, "🔥")
    
    def _get_camper_type(self, camper) -> str:
        """Determine camper type"""
        class_name = camper.__class__.__name__.lower()
        if "loader" in class_name:
            return "loader"
        elif "router" in class_name:
            return "router"
        elif "packer" in class_name:
            return "packer"
        elif "scanner" in class_name:
            return "scanner"
        elif "filter" in class_name:
            return "filter"
        elif "quarantine" in class_name:
            return "quarantine"
        elif "detector" in class_name:
            return "detector"
        elif "enforcer" in class_name:
            return "enforcer"
        elif "governor" in class_name:
            return "governor"
        else:
            return "generic"
    
    def _get_camper_color(self, camper_type: str) -> str:
        """Get color for camper type"""
        colors = {
            "loader": "#4A90E2",
            "router": "#9013FE",
            "packer": "#4A90E2",
            "scanner": "#7ED321",
            "filter": "#7ED321",
            "quarantine": "#F5A623",
            "detector": "#D0021B",
            "enforcer": "#D0021B",
            "governor": "#D0021B",
            "generic": "#50E3C2"
        }
        return colors.get(camper_type, "#50E3C2")
    
    def _get_camper_icon(self, camper_type: str) -> str:
        """Get icon for camper type"""
        icons = {
            "loader": "📥",
            "router": "🔀",
            "packer": "📦",
            "scanner": "🔍",
            "filter": "🧹",
            "quarantine": "🔒",
            "detector": "🚨",
            "enforcer": "👮",
            "governor": "👑",
            "generic": "👤"
        }
        return icons.get(camper_type, "👤")
    
    # Async methods for getting real-time data
    async def _calculate_valley_health(self) -> float:
        """Calculate overall valley health score"""
        if not self.valley.campfires:
            return 0.0
        
        try:
            active_count = 0
            total_count = len(self.valley.campfires)
            
            for cf in self.valley.campfires.values():
                if hasattr(cf, '_running') and getattr(cf, '_running', False):
                    active_count += 1
                elif hasattr(cf, 'is_running') and callable(getattr(cf, 'is_running')):
                    if cf.is_running():
                        active_count += 1
            
            if total_count == 0:
                return 0.0
            
            health_score = active_count / total_count
            return max(0.0, min(1.0, health_score))  # Ensure value is between 0 and 1
        except Exception as e:
            logger.warning(f"Error calculating valley health: {e}")
            return 0.0
    
    async def _get_campfire_status(self, campfire: Campfire) -> NodeStatus:
        """Get current campfire status"""
        if not campfire._running:
            return NodeStatus.OFFLINE
        # Add more sophisticated status detection here
        return NodeStatus.ACTIVE
    
    async def _count_active_campers(self, campfire: Campfire) -> int:
        """Count active campers in campfire"""
        # Placeholder - implement based on actual camper status tracking
        return len(getattr(campfire, 'campers', []))
    
    async def _get_torch_queue_size(self, campfire: Campfire) -> int:
        """Get torch queue size for campfire"""
        # Placeholder - implement based on actual queue tracking
        return 0
    
    async def _get_avg_processing_time(self, campfire: Campfire) -> float:
        """Get average processing time for campfire"""
        # Placeholder - implement based on actual metrics
        return 0.0
    
    async def _get_last_activity(self, campfire: Campfire) -> Optional[datetime]:
        """Get last activity timestamp for campfire"""
        # Placeholder - implement based on actual activity tracking
        return None
    
    async def _get_camper_status(self, camper) -> NodeStatus:
        """Get current camper status"""
        # Placeholder - implement based on actual camper status
        return NodeStatus.ACTIVE
    
    async def _get_current_task(self, camper) -> Optional[str]:
        """Get current task for camper"""
        # Placeholder - implement based on actual task tracking
        return None
    
    async def _get_tasks_completed(self, camper) -> int:
        """Get completed task count for camper"""
        # Placeholder - implement based on actual metrics
        return 0
    
    async def _get_cpu_usage(self, camper) -> float:
        """Get CPU usage for camper"""
        # Placeholder - implement based on actual monitoring
        return 0.0
    
    async def _get_memory_usage(self, camper) -> float:
        """Get memory usage for camper"""
        # Placeholder - implement based on actual monitoring
        return 0.0
    
    # Enhanced data retrieval methods
    async def _get_current_jobs(self, campfire) -> List[Dict[str, Any]]:
        """Get current jobs/tasks being processed by the campfire"""
        try:
            jobs = []
            
            # Check if campfire has active tasks
            if hasattr(campfire, 'current_tasks'):
                for task in getattr(campfire, 'current_tasks', []):
                    job_info = {
                        "id": getattr(task, 'id', 'unknown'),
                        "type": getattr(task, 'type', 'unknown'),
                        "status": getattr(task, 'status', 'unknown'),
                        "progress": getattr(task, 'progress', 0),
                        "started_at": getattr(task, 'started_at', None),
                        "assigned_camper": getattr(task, 'assigned_camper', None)
                    }
                    jobs.append(job_info)
            
            # Check for torch processing
            if hasattr(campfire, '_torch_queue') and campfire._torch_queue:
                for i, torch in enumerate(list(campfire._torch_queue)[:3]):  # Show first 3
                    job_info = {
                        "id": f"torch_{i}",
                        "type": "torch_processing",
                        "status": "queued",
                        "data_type": type(torch).__name__ if torch else "unknown",
                        "queue_position": i + 1
                    }
                    jobs.append(job_info)
            
            return jobs
        except Exception as e:
            logger.warning(f"Error getting current jobs for {campfire.name}: {e}")
            return []
    
    async def _get_party_box_data(self, campfire) -> Dict[str, Any]:
        """Get party box contents and data"""
        try:
            party_box = {}
            
            if hasattr(campfire, 'party_box'):
                pb = campfire.party_box
                party_box = {
                    "total_items": len(getattr(pb, 'items', [])) if hasattr(pb, 'items') else 0,
                    "data_types": [],
                    "recent_additions": [],
                    "storage_usage": getattr(pb, 'storage_usage', 0)
                }
                
                # Get data types
                if hasattr(pb, 'items'):
                    data_types = set()
                    recent_items = []
                    for item in list(getattr(pb, 'items', []))[-5:]:  # Last 5 items
                        data_types.add(type(item).__name__)
                        recent_items.append({
                            "type": type(item).__name__,
                            "timestamp": getattr(item, 'timestamp', None),
                            "size": len(str(item)) if item else 0
                        })
                    party_box["data_types"] = list(data_types)
                    party_box["recent_additions"] = recent_items
            
            return party_box
        except Exception as e:
            logger.warning(f"Error getting party box data for {campfire.name}: {e}")
            return {}
    
    async def _get_input_queue(self, campfire) -> List[Dict[str, Any]]:
        """Get input queue information"""
        try:
            queue_info = []
            
            if hasattr(campfire, '_torch_queue'):
                queue = getattr(campfire, '_torch_queue', [])
                for i, item in enumerate(list(queue)[:5]):  # Show first 5
                    queue_info.append({
                        "position": i + 1,
                        "type": type(item).__name__ if item else "unknown",
                        "size": len(str(item)) if item else 0,
                        "priority": getattr(item, 'priority', 'normal')
                    })
            
            return queue_info
        except Exception as e:
            logger.warning(f"Error getting input queue for {campfire.name}: {e}")
            return []
    
    async def _get_output_queue(self, campfire) -> List[Dict[str, Any]]:
        """Get output queue information"""
        try:
            # Most campfires don't have explicit output queues, but we can check for recent outputs
            output_info = []
            
            if hasattr(campfire, 'recent_outputs'):
                for i, output in enumerate(getattr(campfire, 'recent_outputs', [])[-5:]):
                    output_info.append({
                        "position": i + 1,
                        "type": type(output).__name__ if output else "unknown",
                        "timestamp": getattr(output, 'timestamp', None),
                        "destination": getattr(output, 'destination', 'unknown')
                    })
            
            return output_info
        except Exception as e:
            logger.warning(f"Error getting output queue for {campfire.name}: {e}")
            return []
    
    async def _get_active_camper_details(self, campfire) -> List[Dict[str, Any]]:
        """Get detailed information about active campers"""
        try:
            camper_details = []
            
            if hasattr(campfire, 'campers'):
                for camper in getattr(campfire, 'campers', []):
                    detail = {
                        "name": getattr(camper, 'name', 'unknown'),
                        "type": getattr(camper, 'type', 'unknown'),
                        "status": await self._get_camper_status(camper),
                        "current_task": await self._get_current_task(camper),
                        "tasks_completed": await self._get_tasks_completed(camper),
                        "cpu_usage": await self._get_cpu_usage(camper),
                        "uptime": getattr(camper, 'uptime', 0),
                        "last_activity": getattr(camper, 'last_activity', None)
                    }
                    camper_details.append(detail)
            
            return camper_details
        except Exception as e:
            logger.warning(f"Error getting camper details for {campfire.name}: {e}")
            return []
    
    async def _get_torch_processing_status(self, campfire) -> Dict[str, Any]:
        """Get current torch processing status"""
        try:
            status = {
                "queue_size": await self._get_torch_queue_size(campfire),
                "processing_rate": 0.0,
                "average_processing_time": await self._get_avg_processing_time(campfire),
                "current_torch": None,
                "estimated_completion": None
            }
            
            # Try to get current processing torch
            if hasattr(campfire, '_current_torch'):
                current = getattr(campfire, '_current_torch', None)
                if current:
                    status["current_torch"] = {
                        "type": type(current).__name__,
                        "started_at": getattr(current, 'started_at', None),
                        "progress": getattr(current, 'progress', 0)
                    }
            
            return status
        except Exception as e:
            logger.warning(f"Error getting torch processing status for {campfire.name}: {e}")
            return {}
    
    async def _get_performance_metrics(self, campfire) -> Dict[str, float]:
        """Get performance metrics for the campfire"""
        try:
            metrics = {
                "throughput": 0.0,
                "average_response_time": await self._get_avg_processing_time(campfire),
                "error_rate": 0.0,
                "uptime_percentage": 100.0,
                "memory_usage": 0.0,
                "cpu_usage": 0.0
            }
            
            # Try to get actual metrics if available
            if hasattr(campfire, 'metrics'):
                campfire_metrics = getattr(campfire, 'metrics', {})
                metrics.update(campfire_metrics)
            
            return metrics
        except Exception as e:
            logger.warning(f"Error getting performance metrics for {campfire.name}: {e}")
            return {}
    
    async def _get_error_count(self, campfire) -> int:
        """Get recent error count"""
        try:
            if hasattr(campfire, 'error_count'):
                return getattr(campfire, 'error_count', 0)
            elif hasattr(campfire, 'errors'):
                return len(getattr(campfire, 'errors', []))
            return 0
        except Exception as e:
            logger.warning(f"Error getting error count for {campfire.name}: {e}")
            return 0
    
    async def _get_success_rate(self, campfire) -> float:
        """Get success rate percentage"""
        try:
            if hasattr(campfire, 'success_rate'):
                return getattr(campfire, 'success_rate', 1.0)
            
            # Calculate from completed vs failed tasks
            completed = getattr(campfire, 'completed_tasks', 0)
            failed = getattr(campfire, 'failed_tasks', 0)
            
            if completed + failed == 0:
                return 1.0
            
            return completed / (completed + failed)
        except Exception as e:
            logger.warning(f"Error getting success rate for {campfire.name}: {e}")
            return 1.0
    
    async def _get_flow_rate(self, source: Campfire, target: Campfire) -> float:
        """Get torch flow rate between campfires"""
        # Placeholder - implement based on actual torch tracking
        return 0.0
    
    async def _get_avg_latency(self, source: Campfire, target: Campfire) -> float:
        """Get average latency between campfires"""
        # Placeholder - implement based on actual metrics
        return 0.0


class NodeRenderer:
    """Handles rendering logic for different node types"""
    
    @staticmethod
    def get_node_style(node: NodeData) -> Dict[str, any]:
        """Get CSS/styling properties for a node"""
        base_style = {
            "position": "absolute",
            "left": f"{node.position.x}px",
            "top": f"{node.position.y}px",
            "width": f"{node.size or 50}px",
            "height": f"{node.size or 50}px",
            "backgroundColor": node.color or "#50E3C2",
            "borderRadius": "50%",
            "display": "flex",
            "alignItems": "center",
            "justifyContent": "center",
            "fontSize": f"{(node.size or 50) * 0.3}px",
            "cursor": "pointer",
            "transition": "all 0.3s ease"
        }
        
        # Status-based styling
        if node.status == NodeStatus.ERROR:
            base_style["border"] = "3px solid #D0021B"
        elif node.status == NodeStatus.BUSY:
            base_style["animation"] = "pulse 1s infinite"
        elif node.status == NodeStatus.OFFLINE:
            base_style["opacity"] = "0.5"
        
        return base_style
    
    @staticmethod
    def get_connection_style(connection: Connection) -> Dict[str, any]:
        """Get CSS/styling properties for a connection"""
        return {
            "stroke": connection.color or "#888888",
            "strokeWidth": connection.width or 1.0,
            "fill": "none",
            "opacity": 0.8
        }
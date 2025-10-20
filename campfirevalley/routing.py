"""
Advanced Routing System for CampfireValley

This module provides sophisticated routing capabilities including multi-hop routing,
load balancing, failover mechanisms, and intelligent path optimization.
"""

import asyncio
import json
import logging
import hashlib
from typing import Dict, List, Any, Optional, Set, Tuple, Callable, Union
from datetime import datetime, timedelta
from enum import Enum
from dataclasses import dataclass, field
from abc import ABC, abstractmethod
import random
import heapq

from .models import Torch, SecurityLevel


class RouteStatus(str, Enum):
    """Status of a route"""
    ACTIVE = "active"
    DEGRADED = "degraded"
    FAILED = "failed"
    MAINTENANCE = "maintenance"


class LoadBalancingAlgorithm(str, Enum):
    """Load balancing algorithms"""
    ROUND_ROBIN = "round_robin"
    WEIGHTED_ROUND_ROBIN = "weighted_round_robin"
    LEAST_CONNECTIONS = "least_connections"
    LEAST_RESPONSE_TIME = "least_response_time"
    HASH_BASED = "hash_based"
    RANDOM = "random"


class FailoverStrategy(str, Enum):
    """Failover strategies"""
    IMMEDIATE = "immediate"
    GRACEFUL = "graceful"
    CIRCUIT_BREAKER = "circuit_breaker"


@dataclass
class RouteMetrics:
    """Metrics for a route"""
    latency_ms: float = 0.0
    success_rate: float = 1.0
    active_connections: int = 0
    total_requests: int = 0
    failed_requests: int = 0
    last_success: Optional[datetime] = None
    last_failure: Optional[datetime] = None
    bandwidth_utilization: float = 0.0


@dataclass
class RouteNode:
    """A node in the routing network"""
    address: str
    weight: int = 1
    max_connections: int = 1000
    status: RouteStatus = RouteStatus.ACTIVE
    metrics: RouteMetrics = field(default_factory=RouteMetrics)
    tags: Set[str] = field(default_factory=set)
    capabilities: Set[str] = field(default_factory=set)
    health_check_url: Optional[str] = None
    last_health_check: Optional[datetime] = None


@dataclass
class RoutePath:
    """A complete routing path"""
    path_id: str
    nodes: List[RouteNode]
    total_weight: float
    estimated_latency: float
    reliability_score: float
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_used: Optional[datetime] = None
    use_count: int = 0


@dataclass
class RouteRequest:
    """Request for routing a torch"""
    torch: Torch
    source_address: str
    destination_address: str
    requirements: Dict[str, Any] = field(default_factory=dict)
    constraints: Dict[str, Any] = field(default_factory=dict)
    priority: int = 0


@dataclass
class RouteResponse:
    """Response from routing system"""
    success: bool
    path: Optional[RoutePath]
    error_message: Optional[str] = None
    alternative_paths: List[RoutePath] = field(default_factory=list)
    routing_time_ms: float = 0.0


class IRouteHealthChecker(ABC):
    """Interface for route health checking"""
    
    @abstractmethod
    async def check_node_health(self, node: RouteNode) -> bool:
        """Check if a node is healthy"""
        pass
    
    @abstractmethod
    async def get_node_metrics(self, node: RouteNode) -> RouteMetrics:
        """Get current metrics for a node"""
        pass


class ILoadBalancer(ABC):
    """Interface for load balancing"""
    
    @abstractmethod
    async def select_node(
        self, 
        nodes: List[RouteNode], 
        request: RouteRequest
    ) -> Optional[RouteNode]:
        """Select the best node for a request"""
        pass


class BasicHealthChecker(IRouteHealthChecker):
    """Basic health checker implementation"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    async def check_node_health(self, node: RouteNode) -> bool:
        """Basic health check - just check if node is marked as active"""
        if node.status == RouteStatus.FAILED:
            return False
        
        # Simulate health check based on recent failures
        if node.metrics.failed_requests > 0:
            failure_rate = node.metrics.failed_requests / max(node.metrics.total_requests, 1)
            if failure_rate > 0.5:  # More than 50% failure rate
                return False
        
        return True
    
    async def get_node_metrics(self, node: RouteNode) -> RouteMetrics:
        """Return current node metrics"""
        return node.metrics


class SmartLoadBalancer(ILoadBalancer):
    """Smart load balancer with multiple algorithms"""
    
    def __init__(self, algorithm: LoadBalancingAlgorithm = LoadBalancingAlgorithm.LEAST_CONNECTIONS):
        self.algorithm = algorithm
        self.round_robin_counters: Dict[str, int] = {}
        self.logger = logging.getLogger(__name__)
    
    async def select_node(
        self, 
        nodes: List[RouteNode], 
        request: RouteRequest
    ) -> Optional[RouteNode]:
        """Select the best node based on the configured algorithm"""
        
        # Filter out failed nodes
        healthy_nodes = [n for n in nodes if n.status != RouteStatus.FAILED]
        if not healthy_nodes:
            return None
        
        if self.algorithm == LoadBalancingAlgorithm.ROUND_ROBIN:
            return self._round_robin_select(healthy_nodes)
        
        elif self.algorithm == LoadBalancingAlgorithm.WEIGHTED_ROUND_ROBIN:
            return self._weighted_round_robin_select(healthy_nodes)
        
        elif self.algorithm == LoadBalancingAlgorithm.LEAST_CONNECTIONS:
            return self._least_connections_select(healthy_nodes)
        
        elif self.algorithm == LoadBalancingAlgorithm.LEAST_RESPONSE_TIME:
            return self._least_response_time_select(healthy_nodes)
        
        elif self.algorithm == LoadBalancingAlgorithm.HASH_BASED:
            return self._hash_based_select(healthy_nodes, request)
        
        elif self.algorithm == LoadBalancingAlgorithm.RANDOM:
            return random.choice(healthy_nodes)
        
        return healthy_nodes[0]  # Fallback
    
    def _round_robin_select(self, nodes: List[RouteNode]) -> RouteNode:
        """Round robin selection"""
        nodes_key = "|".join(sorted([n.address for n in nodes]))
        
        if nodes_key not in self.round_robin_counters:
            self.round_robin_counters[nodes_key] = 0
        
        index = self.round_robin_counters[nodes_key] % len(nodes)
        self.round_robin_counters[nodes_key] += 1
        
        return nodes[index]
    
    def _weighted_round_robin_select(self, nodes: List[RouteNode]) -> RouteNode:
        """Weighted round robin selection"""
        total_weight = sum(n.weight for n in nodes)
        if total_weight == 0:
            return nodes[0]
        
        # Create weighted list
        weighted_nodes = []
        for node in nodes:
            weighted_nodes.extend([node] * node.weight)
        
        return self._round_robin_select(weighted_nodes)
    
    def _least_connections_select(self, nodes: List[RouteNode]) -> RouteNode:
        """Select node with least active connections"""
        return min(nodes, key=lambda n: n.metrics.active_connections)
    
    def _least_response_time_select(self, nodes: List[RouteNode]) -> RouteNode:
        """Select node with lowest response time"""
        return min(nodes, key=lambda n: n.metrics.latency_ms)
    
    def _hash_based_select(self, nodes: List[RouteNode], request: RouteRequest) -> RouteNode:
        """Hash-based selection for consistent routing"""
        hash_input = f"{request.torch.id}:{request.source_address}:{request.destination_address}"
        hash_value = int(hashlib.sha256(hash_input.encode()).hexdigest(), 16)
        index = hash_value % len(nodes)
        return nodes[index]


class RouteOptimizer:
    """Optimizes routing paths based on various criteria"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def calculate_path_score(self, path: RoutePath, request: RouteRequest) -> float:
        """Calculate a score for a routing path"""
        score = 0.0
        
        # Latency factor (lower is better)
        latency_score = max(0, 100 - path.estimated_latency)
        score += latency_score * 0.3
        
        # Reliability factor
        reliability_score = path.reliability_score * 100
        score += reliability_score * 0.4
        
        # Load factor (prefer less loaded paths)
        avg_load = sum(n.metrics.active_connections for n in path.nodes) / len(path.nodes)
        load_score = max(0, 100 - avg_load)
        score += load_score * 0.2
        
        # Hop count factor (fewer hops is generally better)
        hop_score = max(0, 100 - len(path.nodes) * 10)
        score += hop_score * 0.1
        
        return score
    
    def optimize_path(self, path: RoutePath) -> RoutePath:
        """Optimize a routing path"""
        # For now, just return the original path
        # In a real implementation, this could reorder nodes, remove redundant hops, etc.
        return path


class AdvancedRoutingEngine:
    """Advanced routing engine with multi-hop and load balancing"""
    
    def __init__(
        self,
        health_checker: Optional[IRouteHealthChecker] = None,
        load_balancer: Optional[ILoadBalancer] = None
    ):
        self.health_checker = health_checker or BasicHealthChecker()
        self.load_balancer = load_balancer or SmartLoadBalancer()
        self.route_optimizer = RouteOptimizer()
        
        # Network topology
        self.nodes: Dict[str, RouteNode] = {}
        self.connections: Dict[str, List[str]] = {}  # adjacency list
        
        # Routing cache
        self.path_cache: Dict[str, List[RoutePath]] = {}
        self.cache_ttl = timedelta(minutes=10)
        
        # Circuit breaker state
        self.circuit_breakers: Dict[str, Dict[str, Any]] = {}
        
        self.logger = logging.getLogger(__name__)
    
    def add_node(self, node: RouteNode):
        """Add a node to the routing network"""
        self.nodes[node.address] = node
        if node.address not in self.connections:
            self.connections[node.address] = []
        self.logger.info(f"Added routing node: {node.address}")
    
    def add_connection(self, from_address: str, to_address: str, bidirectional: bool = True):
        """Add a connection between nodes"""
        if from_address not in self.connections:
            self.connections[from_address] = []
        
        if to_address not in self.connections[from_address]:
            self.connections[from_address].append(to_address)
        
        if bidirectional:
            if to_address not in self.connections:
                self.connections[to_address] = []
            if from_address not in self.connections[to_address]:
                self.connections[to_address].append(from_address)
        
        self.logger.info(f"Added connection: {from_address} -> {to_address}")
    
    async def route_torch(self, request: RouteRequest) -> RouteResponse:
        """Route a torch through the network"""
        start_time = datetime.utcnow()
        
        try:
            # Check circuit breakers
            if await self._is_circuit_open(request.source_address, request.destination_address):
                return RouteResponse(
                    success=False,
                    path=None,
                    error_message="Circuit breaker is open"
                )
            
            # Find possible paths
            paths = await self._find_paths(request)
            
            if not paths:
                return RouteResponse(
                    success=False,
                    path=None,
                    error_message="No valid paths found"
                )
            
            # Select best path
            best_path = await self._select_best_path(paths, request)
            
            # Update path usage
            best_path.last_used = datetime.utcnow()
            best_path.use_count += 1
            
            routing_time = (datetime.utcnow() - start_time).total_seconds() * 1000
            
            return RouteResponse(
                success=True,
                path=best_path,
                alternative_paths=paths[1:5],  # Return up to 4 alternatives
                routing_time_ms=routing_time
            )
            
        except Exception as e:
            self.logger.error(f"Error routing torch {request.torch.id}: {e}")
            routing_time = (datetime.utcnow() - start_time).total_seconds() * 1000
            
            return RouteResponse(
                success=False,
                path=None,
                error_message=str(e),
                routing_time_ms=routing_time
            )
    
    async def _find_paths(self, request: RouteRequest) -> List[RoutePath]:
        """Find all possible paths from source to destination"""
        # Check cache first
        cache_key = f"{request.source_address}:{request.destination_address}"
        cached_paths = self._get_cached_paths(cache_key)
        if cached_paths:
            # Filter paths based on current node health
            valid_paths = []
            for path in cached_paths:
                if await self._is_path_healthy(path):
                    valid_paths.append(path)
            if valid_paths:
                return valid_paths
        
        # Find new paths using modified Dijkstra's algorithm
        paths = await self._dijkstra_all_paths(request.source_address, request.destination_address)
        
        # Convert to RoutePath objects
        route_paths = []
        for path_nodes in paths:
            route_path = await self._create_route_path(path_nodes)
            if route_path:
                route_paths.append(route_path)
        
        # Sort by score
        for path in route_paths:
            path.total_weight = self.route_optimizer.calculate_path_score(path, request)
        
        route_paths.sort(key=lambda p: p.total_weight, reverse=True)
        
        # Cache the results
        self._cache_paths(cache_key, route_paths)
        
        return route_paths
    
    async def _dijkstra_all_paths(
        self, 
        source: str, 
        destination: str, 
        max_paths: int = 10
    ) -> List[List[str]]:
        """Find multiple paths using modified Dijkstra's algorithm"""
        
        if source not in self.nodes or destination not in self.nodes:
            return []
        
        # Priority queue: (cost, path)
        pq = [(0, [source])]
        paths = []
        visited_paths = set()
        
        while pq and len(paths) < max_paths:
            cost, path = heapq.heappop(pq)
            current = path[-1]
            
            if current == destination:
                path_key = "->".join(path)
                if path_key not in visited_paths:
                    paths.append(path)
                    visited_paths.add(path_key)
                continue
            
            if len(path) > 5:  # Limit path length
                continue
            
            for neighbor in self.connections.get(current, []):
                if neighbor not in path:  # Avoid cycles
                    neighbor_node = self.nodes.get(neighbor)
                    if neighbor_node and neighbor_node.status != RouteStatus.FAILED:
                        new_cost = cost + neighbor_node.metrics.latency_ms
                        new_path = path + [neighbor]
                        heapq.heappush(pq, (new_cost, new_path))
        
        return paths
    
    async def _create_route_path(self, node_addresses: List[str]) -> Optional[RoutePath]:
        """Create a RoutePath from a list of node addresses"""
        nodes = []
        total_latency = 0.0
        total_reliability = 1.0
        
        for address in node_addresses:
            node = self.nodes.get(address)
            if not node:
                return None
            
            nodes.append(node)
            total_latency += node.metrics.latency_ms
            total_reliability *= node.metrics.success_rate
        
        path_id = hashlib.sha256("->".join(node_addresses).encode()).hexdigest()[:16]
        
        return RoutePath(
            path_id=path_id,
            nodes=nodes,
            total_weight=0.0,  # Will be calculated later
            estimated_latency=total_latency,
            reliability_score=total_reliability
        )
    
    async def _select_best_path(self, paths: List[RoutePath], request: RouteRequest) -> RoutePath:
        """Select the best path from available options"""
        if not paths:
            raise ValueError("No paths available")
        
        # For high priority requests, prefer reliability
        if request.priority > 5:
            return max(paths, key=lambda p: p.reliability_score)
        
        # For normal requests, use the pre-calculated scores
        return max(paths, key=lambda p: p.total_weight)
    
    async def _is_path_healthy(self, path: RoutePath) -> bool:
        """Check if all nodes in a path are healthy"""
        for node in path.nodes:
            if not await self.health_checker.check_node_health(node):
                return False
        return True
    
    async def _is_circuit_open(self, source: str, destination: str) -> bool:
        """Check if circuit breaker is open for this route"""
        circuit_key = f"{source}:{destination}"
        circuit = self.circuit_breakers.get(circuit_key)
        
        if not circuit:
            return False
        
        if circuit["state"] == "open":
            # Check if we should try to close the circuit
            if datetime.utcnow() - circuit["last_failure"] > timedelta(minutes=5):
                circuit["state"] = "half_open"
                return False
            return True
        
        return False
    
    def _get_cached_paths(self, cache_key: str) -> Optional[List[RoutePath]]:
        """Get cached paths if still valid"""
        if cache_key in self.path_cache:
            paths = self.path_cache[cache_key]
            # Check if cache is still valid (simplified check)
            if paths and datetime.utcnow() - paths[0].created_at < self.cache_ttl:
                return paths
            else:
                del self.path_cache[cache_key]
        return None
    
    def _cache_paths(self, cache_key: str, paths: List[RoutePath]):
        """Cache routing paths"""
        self.path_cache[cache_key] = paths
    
    async def update_node_metrics(self, address: str, metrics: RouteMetrics):
        """Update metrics for a node"""
        if address in self.nodes:
            self.nodes[address].metrics = metrics
            self.logger.debug(f"Updated metrics for node {address}")
    
    async def mark_node_failed(self, address: str):
        """Mark a node as failed"""
        if address in self.nodes:
            self.nodes[address].status = RouteStatus.FAILED
            self.logger.warning(f"Marked node {address} as failed")
    
    async def mark_node_recovered(self, address: str):
        """Mark a node as recovered"""
        if address in self.nodes:
            self.nodes[address].status = RouteStatus.ACTIVE
            self.logger.info(f"Marked node {address} as recovered")
    
    def get_network_statistics(self) -> Dict[str, Any]:
        """Get network statistics"""
        total_nodes = len(self.nodes)
        active_nodes = len([n for n in self.nodes.values() if n.status == RouteStatus.ACTIVE])
        failed_nodes = len([n for n in self.nodes.values() if n.status == RouteStatus.FAILED])
        
        return {
            "total_nodes": total_nodes,
            "active_nodes": active_nodes,
            "failed_nodes": failed_nodes,
            "total_connections": sum(len(conns) for conns in self.connections.values()),
            "cached_paths": len(self.path_cache),
            "circuit_breakers": len(self.circuit_breakers)
        }
"""
Simplified advanced routing system used by the test suite.
"""

from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Protocol, Tuple

try:
    import aiohttp
except Exception:  # pragma: no cover
    aiohttp = None

from .models import Torch


class RouteStatus(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class LoadBalancingAlgorithm(Enum):
    ROUND_ROBIN = "round_robin"
    WEIGHTED_ROUND_ROBIN = "weighted_round_robin"
    LEAST_CONNECTIONS = "least_connections"
    RANDOM = "random"


class FailoverStrategy(Enum):
    IMMEDIATE = "immediate"
    GRACEFUL = "graceful"


@dataclass
class RouteMetrics:
    node_id: str
    latency: float
    throughput: float
    error_rate: float
    cpu_usage: float
    memory_usage: float
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class RouteNode:
    id: str
    address: str
    port: int
    weight: float = 1.0
    status: RouteStatus = RouteStatus.UNKNOWN
    metadata: Dict[str, Any] = field(default_factory=dict)
    metrics: Optional[RouteMetrics] = None

    @property
    def endpoint(self) -> str:
        return f"{self.address}:{self.port}"


@dataclass
class RoutePath:
    id: str
    nodes: List[RouteNode]
    total_cost: float = 0.0
    estimated_latency: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_used: Optional[datetime] = None

    def is_healthy(self) -> bool:
        for n in self.nodes:
            if n.status == RouteStatus.UNHEALTHY:
                return False
        return True


@dataclass
class RouteRequest:
    torch: Torch
    source: str
    destination: str
    priority: int = 0
    requirements: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: f"req_{int(time.time() * 1000)}_{random.randint(1000, 9999)}")


@dataclass
class RouteResponse:
    request_id: str
    success: bool
    path: Optional[RoutePath]
    latency: float
    timestamp: datetime = field(default_factory=datetime.utcnow)
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class IRouteHealthChecker(Protocol):
    async def check_health(self, node: RouteNode) -> bool:
        ...

    async def get_metrics(self, node: RouteNode) -> Optional[RouteMetrics]:
        ...


class ILoadBalancer(Protocol):
    def select_node(self, nodes: List[RouteNode]) -> Optional[RouteNode]:
        ...


class BasicHealthChecker:
    async def check_health(self, node: RouteNode) -> bool:
        if aiohttp is None:
            return False
        url = f"http://{node.endpoint}/health"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=2) as resp:
                    return resp.status == 200
        except Exception:
            return False

    async def get_metrics(self, node: RouteNode) -> Optional[RouteMetrics]:
        if aiohttp is None:
            return None
        url = f"http://{node.endpoint}/metrics"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=2) as resp:
                    if resp.status != 200:
                        return None
                    data = await resp.json()
        except Exception:
            return None
        try:
            return RouteMetrics(
                node_id=node.id,
                latency=float(data.get("latency", 0)),
                throughput=float(data.get("throughput", 0)),
                error_rate=float(data.get("error_rate", 0)),
                cpu_usage=float(data.get("cpu_usage", 0)),
                memory_usage=float(data.get("memory_usage", 0)),
            )
        except Exception:
            return None


class SmartLoadBalancer:
    def __init__(self, algorithm: LoadBalancingAlgorithm = LoadBalancingAlgorithm.ROUND_ROBIN):
        self.algorithm = algorithm
        self._rr_index = 0
        self.node_connections: Dict[str, int] = {}
        self._wrr_cycle: List[str] = []
        self._wrr_index = 0

    def update_node_load(self, node_id: str, delta: int) -> None:
        cur = int(self.node_connections.get(node_id, 0))
        nxt = cur + int(delta)
        if nxt < 0:
            nxt = 0
        self.node_connections[node_id] = nxt

    def _healthy_nodes(self, nodes: List[RouteNode]) -> List[RouteNode]:
        return [n for n in nodes if n.status != RouteStatus.UNHEALTHY]

    def select_node(self, nodes: List[RouteNode]) -> Optional[RouteNode]:
        nodes = self._healthy_nodes(nodes)
        if not nodes:
            return None
        if self.algorithm == LoadBalancingAlgorithm.RANDOM:
            return random.choice(nodes)
        if self.algorithm == LoadBalancingAlgorithm.LEAST_CONNECTIONS:
            return min(nodes, key=lambda n: self.node_connections.get(n.id, 0))
        if self.algorithm == LoadBalancingAlgorithm.WEIGHTED_ROUND_ROBIN:
            if not self._wrr_cycle:
                expanded: List[str] = []
                for n in nodes:
                    count = max(1, int(round(float(n.weight))))
                    expanded.extend([n.id] * count)
                if not expanded:
                    return None
                self._wrr_cycle = expanded
                self._wrr_index = 0
            node_id = self._wrr_cycle[self._wrr_index % len(self._wrr_cycle)]
            self._wrr_index += 1
            for n in nodes:
                if n.id == node_id:
                    return n
            self._wrr_cycle = []
            return self.select_node(nodes)
        node = nodes[self._rr_index % len(nodes)]
        self._rr_index += 1
        return node


class RouteOptimizer:
    def __init__(self):
        self.node_graph: Dict[str, List[Tuple[str, float]]] = {}

    def _node_by_id(self, nodes: List[RouteNode]) -> Dict[str, RouteNode]:
        return {n.id: n for n in nodes}

    async def find_optimal_path(self, source: str, destination: str, nodes: List[RouteNode]) -> Optional[RoutePath]:
        by_id = self._node_by_id(nodes)
        if source not in by_id or destination not in by_id:
            return None
        dist: Dict[str, float] = {source: 0.0}
        prev: Dict[str, Optional[str]] = {source: None}
        unvisited = set(self.node_graph.keys()) | {source, destination}
        while unvisited:
            cur = min((n for n in unvisited if n in dist), key=lambda n: dist[n], default=None)
            if cur is None:
                break
            if cur == destination:
                break
            unvisited.remove(cur)
            for nb, cost in self.node_graph.get(cur, []):
                alt = dist[cur] + float(cost)
                if nb not in dist or alt < dist[nb]:
                    dist[nb] = alt
                    prev[nb] = cur
        if destination not in dist:
            return None
        path_nodes: List[str] = []
        cur = destination
        while cur is not None:
            path_nodes.append(cur)
            cur = prev.get(cur)
        path_nodes.reverse()
        route_nodes = [by_id[n] for n in path_nodes if n in by_id]
        return RoutePath(id=f"path_{source}_{destination}", nodes=route_nodes, total_cost=dist[destination])

    async def find_multiple_paths(self, source: str, destination: str, nodes: List[RouteNode], max_paths: int = 3) -> List[RoutePath]:
        by_id = self._node_by_id(nodes)
        results: List[Tuple[float, List[str]]] = []
        max_depth = max(2, len(nodes) + 2)

        def dfs(cur: str, cost: float, path: List[str], seen: set):
            if len(results) >= 200:
                return
            if cur == destination:
                results.append((cost, list(path)))
                return
            if len(path) >= max_depth:
                return
            for nb, w in self.node_graph.get(cur, []):
                if nb in seen:
                    continue
                seen.add(nb)
                path.append(nb)
                dfs(nb, cost + float(w), path, seen)
                path.pop()
                seen.remove(nb)

        if source not in by_id or destination not in by_id:
            return []
        dfs(source, 0.0, [source], {source})
        results.sort(key=lambda x: x[0])
        paths: List[RoutePath] = []
        for cost, ids in results[:max_paths]:
            paths.append(RoutePath(id=f"path_{len(paths)+1}", nodes=[by_id[i] for i in ids], total_cost=cost))
        return paths

    async def optimize_path(self, original_path: RoutePath, nodes: List[RouteNode]) -> RoutePath:
        if not original_path.nodes:
            return original_path
        src = original_path.nodes[0].id
        dst = original_path.nodes[-1].id
        best = await self.find_optimal_path(src, dst, nodes)
        if best and (original_path.total_cost <= 0 or best.total_cost < original_path.total_cost):
            return best
        return original_path

    async def calculate_path_metrics(self, path: RoutePath) -> Dict[str, Any]:
        total_latency = 0.0
        reliability = 1.0
        for n in path.nodes:
            if n.metrics:
                total_latency += float(n.metrics.latency)
                reliability *= max(0.0, 1.0 - float(n.metrics.error_rate))
        return {"total_latency": total_latency, "hop_count": len(path.nodes), "reliability_score": reliability}


class AdvancedRoutingEngine:
    def __init__(self):
        self.nodes: Dict[str, RouteNode] = {}
        self.health_checker: Optional[IRouteHealthChecker] = None
        self.load_balancer: Optional[SmartLoadBalancer] = None
        self.optimizer: Optional[RouteOptimizer] = None
        self.total_routes = 0
        self.successful_routes = 0
        self.failed_routes = 0
        self._latencies: List[float] = []

    async def initialize(self):
        if self.health_checker is None:
            self.health_checker = BasicHealthChecker()
        if self.load_balancer is None:
            self.load_balancer = SmartLoadBalancer()
        if self.optimizer is None:
            self.optimizer = RouteOptimizer()

    async def add_node(self, node: RouteNode):
        self.nodes[node.id] = node

    async def remove_node(self, node_id: str):
        if node_id in self.nodes:
            self.nodes.pop(node_id, None)

    async def route_torch(self, request: RouteRequest) -> RouteResponse:
        self.total_routes += 1
        started = time.perf_counter()
        try:
            resp = await self._execute_route(request)
        except Exception as e:
            self.failed_routes += 1
            latency = (time.perf_counter() - started) * 1000.0
            self._latencies.append(latency)
            return RouteResponse(request_id=request.id, success=False, path=None, latency=latency, error_message=str(e), timestamp=datetime.utcnow())
        if resp.success:
            self.successful_routes += 1
        else:
            self.failed_routes += 1
        self._latencies.append(float(resp.latency))
        return resp

    async def _execute_route(self, request: RouteRequest) -> RouteResponse:
        latency = random.uniform(10.0, 100.0)
        return RouteResponse(request_id=request.id, success=True, path=None, latency=latency, timestamp=datetime.utcnow())

    async def get_route_statistics(self) -> Dict[str, Any]:
        avg = sum(self._latencies) / len(self._latencies) if self._latencies else 0.0
        return {
            "total_routes": self.total_routes,
            "successful_routes": self.successful_routes,
            "failed_routes": self.failed_routes,
            "average_latency": avg,
            "active_nodes": len(self.nodes),
        }

    async def _monitor_node_health(self):
        if not self.health_checker:
            return
        for node in self.nodes.values():
            ok = await self.health_checker.check_health(node)
            node.status = RouteStatus.HEALTHY if ok else RouteStatus.UNHEALTHY


__all__ = [
    "AdvancedRoutingEngine",
    "RouteOptimizer",
    "SmartLoadBalancer",
    "RouteStatus",
    "LoadBalancingAlgorithm",
    "FailoverStrategy",
    "RouteMetrics",
    "RouteNode",
    "RoutePath",
    "RouteRequest",
    "RouteResponse",
    "IRouteHealthChecker",
    "ILoadBalancer",
    "BasicHealthChecker",
]


"""
Tests for the Advanced Routing System components.
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch

from campfirevalley.routing import (
    AdvancedRoutingEngine, RouteOptimizer, SmartLoadBalancer,
    RouteStatus, LoadBalancingAlgorithm, FailoverStrategy,
    RouteMetrics, RouteNode, RoutePath, RouteRequest, RouteResponse,
    IRouteHealthChecker, ILoadBalancer, BasicHealthChecker
)
from campfirevalley.models import Torch


class TestRouteNode:
    """Test cases for RouteNode"""
    
    def test_route_node_creation(self):
        """Test creating a route node"""
        node = RouteNode(
            id="node1",
            address="192.168.1.1",
            port=8080,
            weight=1.0,
            status=RouteStatus.HEALTHY,
            metadata={"region": "us-east"}
        )
        
        assert node.id == "node1"
        assert node.address == "192.168.1.1"
        assert node.port == 8080
        assert node.weight == 1.0
        assert node.status == RouteStatus.HEALTHY
        assert node.metadata == {"region": "us-east"}
    
    def test_route_node_endpoint(self):
        """Test route node endpoint property"""
        node = RouteNode(
            id="node1",
            address="192.168.1.1",
            port=8080
        )
        
        assert node.endpoint == "192.168.1.1:8080"


class TestRoutePath:
    """Test cases for RoutePath"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.node1 = RouteNode(id="node1", address="192.168.1.1", port=8080)
        self.node2 = RouteNode(id="node2", address="192.168.1.2", port=8080)
        self.node3 = RouteNode(id="node3", address="192.168.1.3", port=8080)
    
    def test_route_path_creation(self):
        """Test creating a route path"""
        path = RoutePath(
            id="path1",
            nodes=[self.node1, self.node2],
            total_cost=10.5,
            estimated_latency=50.0,
            metadata={"type": "primary"}
        )
        
        assert path.id == "path1"
        assert len(path.nodes) == 2
        assert path.total_cost == 10.5
        assert path.estimated_latency == 50.0
        assert path.metadata == {"type": "primary"}
    
    def test_route_path_is_healthy(self):
        """Test route path health checking"""
        # All healthy nodes
        self.node1.status = RouteStatus.HEALTHY
        self.node2.status = RouteStatus.HEALTHY
        
        path = RoutePath(id="path1", nodes=[self.node1, self.node2])
        assert path.is_healthy() is True
        
        # One unhealthy node
        self.node2.status = RouteStatus.UNHEALTHY
        assert path.is_healthy() is False
        
        # One degraded node (still considered healthy)
        self.node2.status = RouteStatus.DEGRADED
        assert path.is_healthy() is True


class TestRouteMetrics:
    """Test cases for RouteMetrics"""
    
    def test_route_metrics_creation(self):
        """Test creating route metrics"""
        timestamp = datetime.utcnow()
        
        metrics = RouteMetrics(
            node_id="node1",
            latency=25.5,
            throughput=1000.0,
            error_rate=0.01,
            cpu_usage=0.75,
            memory_usage=0.60,
            timestamp=timestamp
        )
        
        assert metrics.node_id == "node1"
        assert metrics.latency == 25.5
        assert metrics.throughput == 1000.0
        assert metrics.error_rate == 0.01
        assert metrics.cpu_usage == 0.75
        assert metrics.memory_usage == 0.60
        assert metrics.timestamp == timestamp


class TestBasicHealthChecker:
    """Test cases for BasicHealthChecker"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.health_checker = BasicHealthChecker()
        self.node = RouteNode(id="node1", address="192.168.1.1", port=8080)
    
    @pytest.mark.asyncio
    async def test_check_health_healthy(self):
        """Test health check for healthy node"""
        with patch('aiohttp.ClientSession.get') as mock_get:
            mock_response = Mock()
            mock_response.status = 200
            mock_get.return_value.__aenter__.return_value = mock_response
            
            is_healthy = await self.health_checker.check_health(self.node)
            assert is_healthy is True
    
    @pytest.mark.asyncio
    async def test_check_health_unhealthy(self):
        """Test health check for unhealthy node"""
        with patch('aiohttp.ClientSession.get') as mock_get:
            mock_response = Mock()
            mock_response.status = 500
            mock_get.return_value.__aenter__.return_value = mock_response
            
            is_healthy = await self.health_checker.check_health(self.node)
            assert is_healthy is False
    
    @pytest.mark.asyncio
    async def test_check_health_connection_error(self):
        """Test health check with connection error"""
        with patch('aiohttp.ClientSession.get') as mock_get:
            mock_get.side_effect = Exception("Connection failed")
            
            is_healthy = await self.health_checker.check_health(self.node)
            assert is_healthy is False
    
    @pytest.mark.asyncio
    async def test_get_metrics(self):
        """Test getting node metrics"""
        with patch('aiohttp.ClientSession.get') as mock_get:
            mock_response = Mock()
            mock_response.status = 200
            mock_response.json = AsyncMock(return_value={
                "latency": 25.5,
                "throughput": 1000.0,
                "error_rate": 0.01,
                "cpu_usage": 0.75,
                "memory_usage": 0.60
            })
            mock_get.return_value.__aenter__.return_value = mock_response
            
            metrics = await self.health_checker.get_metrics(self.node)
            
            assert metrics is not None
            assert metrics.node_id == "node1"
            assert metrics.latency == 25.5
            assert metrics.throughput == 1000.0


class TestSmartLoadBalancer:
    """Test cases for SmartLoadBalancer"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.load_balancer = SmartLoadBalancer()
        
        self.nodes = [
            RouteNode(id="node1", address="192.168.1.1", port=8080, weight=1.0),
            RouteNode(id="node2", address="192.168.1.2", port=8080, weight=2.0),
            RouteNode(id="node3", address="192.168.1.3", port=8080, weight=1.5)
        ]
        
        for node in self.nodes:
            node.status = RouteStatus.HEALTHY
    
    def test_round_robin_selection(self):
        """Test round-robin load balancing"""
        self.load_balancer.algorithm = LoadBalancingAlgorithm.ROUND_ROBIN
        
        # Test multiple selections
        selected_nodes = []
        for _ in range(6):
            node = self.load_balancer.select_node(self.nodes)
            selected_nodes.append(node.id)
        
        # Should cycle through nodes
        expected = ["node1", "node2", "node3", "node1", "node2", "node3"]
        assert selected_nodes == expected
    
    def test_weighted_round_robin_selection(self):
        """Test weighted round-robin load balancing"""
        self.load_balancer.algorithm = LoadBalancingAlgorithm.WEIGHTED_ROUND_ROBIN
        
        # Test multiple selections
        selected_nodes = []
        for _ in range(9):  # 1 + 2 + 1.5 = 4.5, so 9 selections should cover 2 cycles
            node = self.load_balancer.select_node(self.nodes)
            selected_nodes.append(node.id)
        
        # node2 should appear more frequently due to higher weight
        node2_count = selected_nodes.count("node2")
        node1_count = selected_nodes.count("node1")
        assert node2_count > node1_count
    
    def test_least_connections_selection(self):
        """Test least connections load balancing"""
        self.load_balancer.algorithm = LoadBalancingAlgorithm.LEAST_CONNECTIONS
        
        # Set different connection counts
        self.load_balancer.node_connections["node1"] = 5
        self.load_balancer.node_connections["node2"] = 2
        self.load_balancer.node_connections["node3"] = 8
        
        # Should select node with least connections
        selected = self.load_balancer.select_node(self.nodes)
        assert selected.id == "node2"
    
    def test_select_node_filters_unhealthy(self):
        """Test that unhealthy nodes are filtered out"""
        self.nodes[1].status = RouteStatus.UNHEALTHY
        
        selected_nodes = []
        for _ in range(4):
            node = self.load_balancer.select_node(self.nodes)
            selected_nodes.append(node.id)
        
        # Should not select unhealthy node2
        assert "node2" not in selected_nodes
    
    def test_select_node_no_healthy_nodes(self):
        """Test selection when no healthy nodes available"""
        for node in self.nodes:
            node.status = RouteStatus.UNHEALTHY
        
        selected = self.load_balancer.select_node(self.nodes)
        assert selected is None
    
    def test_update_node_load(self):
        """Test updating node load"""
        self.load_balancer.update_node_load("node1", 10)
        assert self.load_balancer.node_connections["node1"] == 10
        
        self.load_balancer.update_node_load("node1", -3)
        assert self.load_balancer.node_connections["node1"] == 7


class TestRouteOptimizer:
    """Test cases for RouteOptimizer"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.optimizer = RouteOptimizer()
        
        self.nodes = [
            RouteNode(id="node1", address="192.168.1.1", port=8080),
            RouteNode(id="node2", address="192.168.1.2", port=8080),
            RouteNode(id="node3", address="192.168.1.3", port=8080),
            RouteNode(id="node4", address="192.168.1.4", port=8080)
        ]
        
        # Set up node connections (adjacency)
        self.optimizer.node_graph = {
            "node1": [("node2", 10), ("node3", 15)],
            "node2": [("node1", 10), ("node3", 5), ("node4", 20)],
            "node3": [("node1", 15), ("node2", 5), ("node4", 8)],
            "node4": [("node2", 20), ("node3", 8)]
        }
    
    @pytest.mark.asyncio
    async def test_find_optimal_path(self):
        """Test finding optimal path between nodes"""
        path = await self.optimizer.find_optimal_path("node1", "node4", self.nodes)
        
        assert path is not None
        assert path.nodes[0].id == "node1"
        assert path.nodes[-1].id == "node4"
        assert path.total_cost > 0
    
    @pytest.mark.asyncio
    async def test_find_multiple_paths(self):
        """Test finding multiple paths"""
        paths = await self.optimizer.find_multiple_paths("node1", "node4", self.nodes, max_paths=3)
        
        assert len(paths) <= 3
        assert all(path.nodes[0].id == "node1" for path in paths)
        assert all(path.nodes[-1].id == "node4" for path in paths)
        
        # Paths should be sorted by cost (best first)
        if len(paths) > 1:
            assert paths[0].total_cost <= paths[1].total_cost
    
    @pytest.mark.asyncio
    async def test_optimize_existing_path(self):
        """Test optimizing an existing path"""
        original_path = RoutePath(
            id="original",
            nodes=[self.nodes[0], self.nodes[1], self.nodes[3]],  # node1 -> node2 -> node4
            total_cost=30
        )
        
        optimized = await self.optimizer.optimize_path(original_path, self.nodes)
        
        # Should find better path through node3
        assert optimized.total_cost < original_path.total_cost
    
    @pytest.mark.asyncio
    async def test_calculate_path_metrics(self):
        """Test calculating path metrics"""
        path = RoutePath(
            id="test",
            nodes=[self.nodes[0], self.nodes[2], self.nodes[3]]  # node1 -> node3 -> node4
        )
        
        metrics = await self.optimizer.calculate_path_metrics(path)
        
        assert "total_latency" in metrics
        assert "hop_count" in metrics
        assert "reliability_score" in metrics
        assert metrics["hop_count"] == 3  # 3 nodes = 2 hops


class TestAdvancedRoutingEngine:
    """Test cases for AdvancedRoutingEngine"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.routing_engine = AdvancedRoutingEngine()
    
    @pytest.mark.asyncio
    async def test_initialize(self):
        """Test routing engine initialization"""
        await self.routing_engine.initialize()
        
        assert self.routing_engine.load_balancer is not None
        assert self.routing_engine.optimizer is not None
        assert self.routing_engine.health_checker is not None
    
    @pytest.mark.asyncio
    async def test_add_node(self):
        """Test adding a node"""
        await self.routing_engine.initialize()
        
        node = RouteNode(id="test_node", address="192.168.1.100", port=8080)
        await self.routing_engine.add_node(node)
        
        assert "test_node" in self.routing_engine.nodes
        assert self.routing_engine.nodes["test_node"] == node
    
    @pytest.mark.asyncio
    async def test_remove_node(self):
        """Test removing a node"""
        await self.routing_engine.initialize()
        
        node = RouteNode(id="test_node", address="192.168.1.100", port=8080)
        await self.routing_engine.add_node(node)
        
        await self.routing_engine.remove_node("test_node")
        assert "test_node" not in self.routing_engine.nodes
    
    @pytest.mark.asyncio
    async def test_route_torch(self):
        """Test routing a torch"""
        await self.routing_engine.initialize()
        
        # Add test nodes
        nodes = [
            RouteNode(id="node1", address="192.168.1.1", port=8080),
            RouteNode(id="node2", address="192.168.1.2", port=8080)
        ]
        
        for node in nodes:
            await self.routing_engine.add_node(node)
        
        # Create route request
        torch = Torch(id="test_torch", payload={"data": "test"})
        request = RouteRequest(
            torch=torch,
            source="source1",
            destination="node2",
            priority=1,
            requirements={}
        )
        
        # Mock the actual routing
        with patch.object(self.routing_engine, '_execute_route') as mock_execute:
            mock_execute.return_value = RouteResponse(
                request_id=request.id,
                success=True,
                path=RoutePath(id="path1", nodes=[nodes[0], nodes[1]]),
                latency=25.0,
                timestamp=datetime.utcnow()
            )
            
            response = await self.routing_engine.route_torch(request)
            
            assert response.success is True
            assert response.path is not None
            assert len(response.path.nodes) == 2
    
    @pytest.mark.asyncio
    async def test_get_route_statistics(self):
        """Test getting route statistics"""
        await self.routing_engine.initialize()
        
        stats = await self.routing_engine.get_route_statistics()
        
        assert "total_routes" in stats
        assert "successful_routes" in stats
        assert "failed_routes" in stats
        assert "average_latency" in stats
        assert "active_nodes" in stats
    
    @pytest.mark.asyncio
    async def test_health_monitoring(self):
        """Test health monitoring functionality"""
        await self.routing_engine.initialize()
        
        # Add test node
        node = RouteNode(id="test_node", address="192.168.1.100", port=8080)
        await self.routing_engine.add_node(node)
        
        # Mock health check
        with patch.object(self.routing_engine.health_checker, 'check_health') as mock_health:
            mock_health.return_value = False
            
            await self.routing_engine._monitor_node_health()
            
            # Node should be marked as unhealthy
            assert self.routing_engine.nodes["test_node"].status == RouteStatus.UNHEALTHY


class TestRouteRequest:
    """Test cases for RouteRequest"""
    
    def test_route_request_creation(self):
        """Test creating a route request"""
        torch = Torch(id="test_torch", payload={"data": "test"})
        timestamp = datetime.utcnow()
        
        request = RouteRequest(
            torch=torch,
            source="source1",
            destination="dest1",
            priority=1,
            requirements={"latency": 100},
            timestamp=timestamp,
            metadata={"type": "urgent"}
        )
        
        assert request.torch == torch
        assert request.source == "source1"
        assert request.destination == "dest1"
        assert request.priority == 1
        assert request.requirements == {"latency": 100}
        assert request.timestamp == timestamp
        assert request.metadata == {"type": "urgent"}
        assert request.id is not None  # Should be auto-generated


class TestRouteResponse:
    """Test cases for RouteResponse"""
    
    def test_route_response_creation(self):
        """Test creating a route response"""
        timestamp = datetime.utcnow()
        node1 = RouteNode(id="node1", address="192.168.1.1", port=8080)
        node2 = RouteNode(id="node2", address="192.168.1.2", port=8080)
        path = RoutePath(id="path1", nodes=[node1, node2])
        
        response = RouteResponse(
            request_id="req123",
            success=True,
            path=path,
            latency=25.5,
            timestamp=timestamp,
            error_message=None,
            metadata={"hops": 2}
        )
        
        assert response.request_id == "req123"
        assert response.success is True
        assert response.path == path
        assert response.latency == 25.5
        assert response.timestamp == timestamp
        assert response.error_message is None
        assert response.metadata == {"hops": 2}


# Integration tests
class TestRoutingSystemIntegration:
    """Integration tests for the complete routing system"""
    
    @pytest.mark.asyncio
    async def test_full_routing_workflow(self):
        """Test complete routing workflow"""
        engine = AdvancedRoutingEngine()
        await engine.initialize()
        
        # Set up network topology
        nodes = [
            RouteNode(id="source", address="192.168.1.1", port=8080),
            RouteNode(id="relay1", address="192.168.1.2", port=8080),
            RouteNode(id="relay2", address="192.168.1.3", port=8080),
            RouteNode(id="destination", address="192.168.1.4", port=8080)
        ]
        
        for node in nodes:
            await engine.add_node(node)
        
        # Create and route torch
        torch = Torch(id="test_torch", payload={"message": "Hello World"})
        request = RouteRequest(
            torch=torch,
            source="source",
            destination="destination",
            priority=1
        )
        
        # Mock the routing execution
        with patch.object(engine, '_execute_route') as mock_execute:
            mock_execute.return_value = RouteResponse(
                request_id=request.id,
                success=True,
                path=RoutePath(id="path1", nodes=[nodes[0], nodes[1], nodes[3]]),
                latency=45.0,
                timestamp=datetime.utcnow()
            )
            
            response = await engine.route_torch(request)
            
            assert response.success is True
            assert response.latency > 0
            
            # Check statistics
            stats = await engine.get_route_statistics()
            assert stats["total_routes"] >= 1
    
    @pytest.mark.asyncio
    async def test_failover_scenario(self):
        """Test failover when nodes become unhealthy"""
        engine = AdvancedRoutingEngine()
        await engine.initialize()
        
        # Set up nodes
        nodes = [
            RouteNode(id="source", address="192.168.1.1", port=8080),
            RouteNode(id="primary", address="192.168.1.2", port=8080),
            RouteNode(id="backup", address="192.168.1.3", port=8080),
            RouteNode(id="destination", address="192.168.1.4", port=8080)
        ]
        
        for node in nodes:
            await engine.add_node(node)
        
        # Mark primary as unhealthy
        engine.nodes["primary"].status = RouteStatus.UNHEALTHY
        
        # Route should use backup path
        torch = Torch(id="test_torch", payload={"data": "test"})
        request = RouteRequest(
            torch=torch,
            source="source",
            destination="destination"
        )
        
        # Mock routing to use backup
        with patch.object(engine, '_execute_route') as mock_execute:
            mock_execute.return_value = RouteResponse(
                request_id=request.id,
                success=True,
                path=RoutePath(id="backup_path", nodes=[nodes[0], nodes[2], nodes[3]]),
                latency=55.0,
                timestamp=datetime.utcnow()
            )
            
            response = await engine.route_torch(request)
            
            assert response.success is True
            # Should use backup node
            assert any(node.id == "backup" for node in response.path.nodes)


if __name__ == "__main__":
    pytest.main([__file__])
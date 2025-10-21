"""
Tests for the Monitoring and Logging System components.
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch, call
import json

from campfirevalley.monitoring import (
    MonitoringSystem, PerformanceMonitor, HealthChecker,
    MetricType, AlertSeverity, LogLevel,
    Metric, Alert, PerformanceMetrics, LogEntry,
    IMetricsCollector, IAlertManager, ILogHandler,
    InMemoryMetricsCollector, ConsoleAlertManager, StructuredLogHandler,
    get_monitoring_system, log_info, log_warning, log_error,
    record_counter, record_gauge, send_alert
)


class TestMetric:
    """Test cases for Metric dataclass"""
    
    def test_metric_creation(self):
        """Test creating a metric"""
        timestamp = datetime.utcnow()
        
        metric = Metric(
            name="cpu_usage",
            value=75.5,
            metric_type=MetricType.GAUGE,
            timestamp=timestamp,
            tags={"host": "server1", "region": "us-east"},
            unit="percent"
        )
        
        assert metric.name == "cpu_usage"
        assert metric.value == 75.5
        assert metric.metric_type == MetricType.GAUGE
        assert metric.timestamp == timestamp
        assert metric.tags == {"host": "server1", "region": "us-east"}
        assert metric.unit == "percent"


class TestAlert:
    """Test cases for Alert dataclass"""
    
    def test_alert_creation(self):
        """Test creating an alert"""
        timestamp = datetime.utcnow()
        
        alert = Alert(
            id="alert123",
            title="High CPU Usage",
            message="CPU usage exceeded 90%",
            severity=AlertSeverity.WARNING,
            timestamp=timestamp,
            source="performance_monitor",
            tags={"component": "cpu", "threshold": "90%"},
            resolved=False
        )
        
        assert alert.id == "alert123"
        assert alert.title == "High CPU Usage"
        assert alert.message == "CPU usage exceeded 90%"
        assert alert.severity == AlertSeverity.WARNING
        assert alert.timestamp == timestamp
        assert alert.source == "performance_monitor"
        assert alert.tags == {"component": "cpu", "threshold": "90%"}
        assert alert.resolved is False


class TestPerformanceMetrics:
    """Test cases for PerformanceMetrics dataclass"""
    
    def test_performance_metrics_creation(self):
        """Test creating performance metrics"""
        timestamp = datetime.utcnow()
        
        metrics = PerformanceMetrics(
            operation="process_torch",
            duration=125.5,
            success=True,
            timestamp=timestamp,
            metadata={"torch_id": "torch123", "size": 1024}
        )
        
        assert metrics.operation == "process_torch"
        assert metrics.duration == 125.5
        assert metrics.success is True
        assert metrics.timestamp == timestamp
        assert metrics.metadata == {"torch_id": "torch123", "size": 1024}


class TestLogEntry:
    """Test cases for LogEntry dataclass"""
    
    def test_log_entry_creation(self):
        """Test creating a log entry"""
        timestamp = datetime.utcnow()
        
        entry = LogEntry(
            level=LogLevel.INFO,
            message="Processing torch completed",
            timestamp=timestamp,
            source="campfire.process_torch",
            context={"torch_id": "torch123", "duration": 125.5},
            correlation_id="req456"
        )
        
        assert entry.level == LogLevel.INFO
        assert entry.message == "Processing torch completed"
        assert entry.timestamp == timestamp
        assert entry.source == "campfire.process_torch"
        assert entry.context == {"torch_id": "torch123", "duration": 125.5}
        assert entry.correlation_id == "req456"


class TestInMemoryMetricsCollector:
    """Test cases for InMemoryMetricsCollector"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.collector = InMemoryMetricsCollector()
    
    @pytest.mark.asyncio
    async def test_record_metric(self):
        """Test recording a metric"""
        metric = Metric(
            name="test_metric",
            value=100.0,
            metric_type=MetricType.COUNTER
        )
        
        await self.collector.record_metric(metric)
        
        assert len(self.collector.metrics) == 1
        assert self.collector.metrics[0] == metric
    
    @pytest.mark.asyncio
    async def test_get_metrics(self):
        """Test getting metrics"""
        # Record some test metrics
        metrics = [
            Metric(name="metric1", value=10, metric_type=MetricType.GAUGE),
            Metric(name="metric2", value=20, metric_type=MetricType.COUNTER),
            Metric(name="metric1", value=15, metric_type=MetricType.GAUGE)
        ]
        
        for metric in metrics:
            await self.collector.record_metric(metric)
        
        # Get all metrics
        all_metrics = await self.collector.get_metrics()
        assert len(all_metrics) == 3
        
        # Get metrics by name
        metric1_metrics = await self.collector.get_metrics(metric_name="metric1")
        assert len(metric1_metrics) == 2
        assert all(m.name == "metric1" for m in metric1_metrics)
        
        # Get metrics with limit
        limited_metrics = await self.collector.get_metrics(limit=2)
        assert len(limited_metrics) == 2
    
    @pytest.mark.asyncio
    async def test_get_metric_summary(self):
        """Test getting metric summary"""
        # Record metrics with same name
        for i in range(5):
            metric = Metric(
                name="test_metric",
                value=i * 10,
                metric_type=MetricType.GAUGE
            )
            await self.collector.record_metric(metric)
        
        summary = await self.collector.get_metric_summary("test_metric")
        
        assert summary["count"] == 5
        assert summary["min"] == 0
        assert summary["max"] == 40
        assert summary["avg"] == 20
        assert summary["latest"] == 40
    
    @pytest.mark.asyncio
    async def test_clear_metrics(self):
        """Test clearing metrics"""
        metric = Metric(name="test", value=1, metric_type=MetricType.COUNTER)
        await self.collector.record_metric(metric)
        
        assert len(self.collector.metrics) == 1
        
        await self.collector.clear_metrics()
        assert len(self.collector.metrics) == 0


class TestConsoleAlertManager:
    """Test cases for ConsoleAlertManager"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.alert_manager = ConsoleAlertManager()
    
    @pytest.mark.asyncio
    async def test_send_alert(self):
        """Test sending an alert"""
        alert = Alert(
            id="test_alert",
            title="Test Alert",
            message="This is a test alert",
            severity=AlertSeverity.INFO,
            source="test"
        )
        
        with patch('builtins.print') as mock_print:
            await self.alert_manager.send_alert(alert)
            
            # Should print the alert
            mock_print.assert_called_once()
            call_args = mock_print.call_args[0][0]
            assert "Test Alert" in call_args
            assert "This is a test alert" in call_args
    
    @pytest.mark.asyncio
    async def test_get_alerts(self):
        """Test getting alerts"""
        alerts = [
            Alert(id="alert1", title="Alert 1", message="Message 1", 
                  severity=AlertSeverity.INFO, source="test"),
            Alert(id="alert2", title="Alert 2", message="Message 2", 
                  severity=AlertSeverity.WARNING, source="test")
        ]
        
        for alert in alerts:
            await self.alert_manager.send_alert(alert)
        
        # Get all alerts
        all_alerts = await self.alert_manager.get_alerts()
        assert len(all_alerts) == 2
        
        # Get alerts by severity
        warning_alerts = await self.alert_manager.get_alerts(severity=AlertSeverity.WARNING)
        assert len(warning_alerts) == 1
        assert warning_alerts[0].severity == AlertSeverity.WARNING
    
    @pytest.mark.asyncio
    async def test_resolve_alert(self):
        """Test resolving an alert"""
        alert = Alert(
            id="test_alert",
            title="Test Alert",
            message="Test message",
            severity=AlertSeverity.INFO,
            source="test"
        )
        
        await self.alert_manager.send_alert(alert)
        await self.alert_manager.resolve_alert("test_alert")
        
        # Alert should be marked as resolved
        alerts = await self.alert_manager.get_alerts()
        assert len(alerts) == 1
        assert alerts[0].resolved is True


class TestStructuredLogHandler:
    """Test cases for StructuredLogHandler"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.log_handler = StructuredLogHandler()
    
    @pytest.mark.asyncio
    async def test_log_entry(self):
        """Test logging an entry"""
        entry = LogEntry(
            level=LogLevel.INFO,
            message="Test log message",
            source="test_module",
            context={"key": "value"}
        )
        
        with patch('builtins.print') as mock_print:
            await self.log_handler.log(entry)
            
            # Should print structured log
            mock_print.assert_called_once()
            call_args = mock_print.call_args[0][0]
            
            # Should be valid JSON
            log_data = json.loads(call_args)
            assert log_data["level"] == "INFO"
            assert log_data["message"] == "Test log message"
            assert log_data["source"] == "test_module"
            assert log_data["context"] == {"key": "value"}
    
    @pytest.mark.asyncio
    async def test_get_logs(self):
        """Test getting logs"""
        entries = [
            LogEntry(level=LogLevel.INFO, message="Info message", source="test"),
            LogEntry(level=LogLevel.ERROR, message="Error message", source="test"),
            LogEntry(level=LogLevel.DEBUG, message="Debug message", source="test")
        ]
        
        for entry in entries:
            await self.log_handler.log(entry)
        
        # Get all logs
        all_logs = await self.log_handler.get_logs()
        assert len(all_logs) == 3
        
        # Get logs by level
        error_logs = await self.log_handler.get_logs(level=LogLevel.ERROR)
        assert len(error_logs) == 1
        assert error_logs[0].level == LogLevel.ERROR
        
        # Get logs with limit
        limited_logs = await self.log_handler.get_logs(limit=2)
        assert len(limited_logs) == 2


class TestPerformanceMonitor:
    """Test cases for PerformanceMonitor"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.metrics_collector = InMemoryMetricsCollector()
        self.performance_monitor = PerformanceMonitor(self.metrics_collector)
    
    @pytest.mark.asyncio
    async def test_monitor_performance_success(self):
        """Test monitoring successful operation performance"""
        async def test_operation():
            await asyncio.sleep(0.1)  # Simulate work
            return "success"
        
        result = await self.performance_monitor.monitor_performance(
            "test_operation", test_operation
        )
        
        assert result == "success"
        
        # Check that metrics were recorded
        metrics = await self.metrics_collector.get_metrics()
        duration_metrics = [m for m in metrics if m.name == "operation_duration"]
        success_metrics = [m for m in metrics if m.name == "operation_success"]
        
        assert len(duration_metrics) == 1
        assert len(success_metrics) == 1
        assert duration_metrics[0].value >= 100  # At least 100ms
        assert success_metrics[0].value == 1
    
    @pytest.mark.asyncio
    async def test_monitor_performance_failure(self):
        """Test monitoring failed operation performance"""
        async def failing_operation():
            await asyncio.sleep(0.05)
            raise ValueError("Test error")
        
        with pytest.raises(ValueError):
            await self.performance_monitor.monitor_performance(
                "failing_operation", failing_operation
            )
        
        # Check that failure metrics were recorded
        metrics = await self.metrics_collector.get_metrics()
        failure_metrics = [m for m in metrics if m.name == "operation_failure"]
        
        assert len(failure_metrics) == 1
        assert failure_metrics[0].value == 1
    
    @pytest.mark.asyncio
    async def test_record_performance_metrics(self):
        """Test recording performance metrics directly"""
        perf_metrics = PerformanceMetrics(
            operation="test_op",
            duration=250.5,
            success=True,
            metadata={"param": "value"}
        )
        
        await self.performance_monitor.record_performance_metrics(perf_metrics)
        
        # Check recorded metrics
        metrics = await self.metrics_collector.get_metrics()
        
        duration_metrics = [m for m in metrics if m.name == "operation_duration"]
        success_metrics = [m for m in metrics if m.name == "operation_success"]
        
        assert len(duration_metrics) == 1
        assert len(success_metrics) == 1
        assert duration_metrics[0].value == 250.5
        assert duration_metrics[0].tags["operation"] == "test_op"
    
    @pytest.mark.asyncio
    async def test_get_performance_summary(self):
        """Test getting performance summary"""
        # Record multiple performance metrics
        operations = [
            ("op1", 100, True),
            ("op1", 150, True),
            ("op1", 200, False),
            ("op2", 50, True)
        ]
        
        for op_name, duration, success in operations:
            perf_metrics = PerformanceMetrics(
                operation=op_name,
                duration=duration,
                success=success
            )
            await self.performance_monitor.record_performance_metrics(perf_metrics)
        
        summary = await self.performance_monitor.get_performance_summary("op1")
        
        assert summary["total_operations"] == 3
        assert summary["successful_operations"] == 2
        assert summary["failed_operations"] == 1
        assert summary["success_rate"] == 2/3
        assert summary["avg_duration"] == 150  # (100 + 150 + 200) / 3


class TestHealthChecker:
    """Test cases for HealthChecker"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.metrics_collector = InMemoryMetricsCollector()
        self.alert_manager = ConsoleAlertManager()
        self.health_checker = HealthChecker(self.metrics_collector, self.alert_manager)
    
    @pytest.mark.asyncio
    async def test_add_health_check(self):
        """Test adding a health check"""
        async def test_check():
            return True, "All good"
        
        self.health_checker.add_health_check("test_service", test_check)
        
        assert "test_service" in self.health_checker.health_checks
    
    @pytest.mark.asyncio
    async def test_check_health_all_healthy(self):
        """Test health check when all services are healthy"""
        async def healthy_check():
            return True, "Service is healthy"
        
        self.health_checker.add_health_check("service1", healthy_check)
        self.health_checker.add_health_check("service2", healthy_check)
        
        results = await self.health_checker.check_health()
        
        assert len(results) == 2
        assert all(result["healthy"] for result in results.values())
        
        # Check that metrics were recorded
        metrics = await self.metrics_collector.get_metrics()
        health_metrics = [m for m in metrics if m.name == "service_health"]
        assert len(health_metrics) == 2
        assert all(m.value == 1 for m in health_metrics)  # 1 = healthy
    
    @pytest.mark.asyncio
    async def test_check_health_with_unhealthy_service(self):
        """Test health check with unhealthy service"""
        async def healthy_check():
            return True, "Service is healthy"
        
        async def unhealthy_check():
            return False, "Service is down"
        
        self.health_checker.add_health_check("healthy_service", healthy_check)
        self.health_checker.add_health_check("unhealthy_service", unhealthy_check)
        
        with patch.object(self.alert_manager, 'send_alert') as mock_alert:
            results = await self.health_checker.check_health()
            
            assert results["healthy_service"]["healthy"] is True
            assert results["unhealthy_service"]["healthy"] is False
            
            # Should send alert for unhealthy service
            mock_alert.assert_called_once()
            alert_call = mock_alert.call_args[0][0]
            assert "unhealthy_service" in alert_call.title
    
    @pytest.mark.asyncio
    async def test_check_specific_service(self):
        """Test checking specific service health"""
        async def test_check():
            return True, "Service OK"
        
        self.health_checker.add_health_check("specific_service", test_check)
        
        results = await self.health_checker.check_health(service_name="specific_service")
        
        assert len(results) == 1
        assert "specific_service" in results
        assert results["specific_service"]["healthy"] is True


class TestMonitoringSystem:
    """Test cases for MonitoringSystem"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.monitoring_system = MonitoringSystem()
    
    @pytest.mark.asyncio
    async def test_initialize(self):
        """Test monitoring system initialization"""
        await self.monitoring_system.initialize()
        
        assert self.monitoring_system.metrics_collector is not None
        assert self.monitoring_system.alert_manager is not None
        assert self.monitoring_system.log_handler is not None
        assert self.monitoring_system.performance_monitor is not None
        assert self.monitoring_system.health_checker is not None
    
    @pytest.mark.asyncio
    async def test_log_methods(self):
        """Test logging methods"""
        await self.monitoring_system.initialize()
        
        with patch.object(self.monitoring_system.log_handler, 'log') as mock_log:
            await self.monitoring_system.log_info("Info message", source="test")
            await self.monitoring_system.log_warning("Warning message", source="test")
            await self.monitoring_system.log_error("Error message", source="test")
            
            assert mock_log.call_count == 3
            
            # Check log levels
            calls = mock_log.call_args_list
            assert calls[0][0][0].level == LogLevel.INFO
            assert calls[1][0][0].level == LogLevel.WARNING
            assert calls[2][0][0].level == LogLevel.ERROR
    
    @pytest.mark.asyncio
    async def test_record_metric(self):
        """Test recording metrics"""
        await self.monitoring_system.initialize()
        
        with patch.object(self.monitoring_system.metrics_collector, 'record_metric') as mock_record:
            await self.monitoring_system.record_metric(
                "test_metric", 100, MetricType.GAUGE, tags={"env": "test"}
            )
            
            mock_record.assert_called_once()
            metric = mock_record.call_args[0][0]
            assert metric.name == "test_metric"
            assert metric.value == 100
            assert metric.metric_type == MetricType.GAUGE
            assert metric.tags == {"env": "test"}
    
    @pytest.mark.asyncio
    async def test_send_alert(self):
        """Test sending alerts"""
        await self.monitoring_system.initialize()
        
        with patch.object(self.monitoring_system.alert_manager, 'send_alert') as mock_send:
            await self.monitoring_system.send_alert(
                "Test Alert", "Test message", AlertSeverity.WARNING, source="test"
            )
            
            mock_send.assert_called_once()
            alert = mock_send.call_args[0][0]
            assert alert.title == "Test Alert"
            assert alert.message == "Test message"
            assert alert.severity == AlertSeverity.WARNING
            assert alert.source == "test"
    
    @pytest.mark.asyncio
    async def test_monitor_performance(self):
        """Test performance monitoring"""
        await self.monitoring_system.initialize()
        
        async def test_operation():
            return "result"
        
        with patch.object(self.monitoring_system.performance_monitor, 'monitor_performance') as mock_monitor:
            mock_monitor.return_value = "result"
            
            result = await self.monitoring_system.monitor_performance("test_op", test_operation)
            
            assert result == "result"
            mock_monitor.assert_called_once_with("test_op", test_operation)
    
    @pytest.mark.asyncio
    async def test_get_system_status(self):
        """Test getting system status"""
        await self.monitoring_system.initialize()
        
        # Mock health check results
        with patch.object(self.monitoring_system.health_checker, 'check_health') as mock_health:
            mock_health.return_value = {
                "service1": {"healthy": True, "message": "OK"},
                "service2": {"healthy": False, "message": "Down"}
            }
            
            status = await self.monitoring_system.get_system_status()
            
            assert "health_checks" in status
            assert "metrics_summary" in status
            assert "recent_alerts" in status
            assert status["overall_health"] is False  # One service is down


class TestGlobalFunctions:
    """Test cases for global convenience functions"""
    
    @pytest.mark.asyncio
    async def test_get_monitoring_system(self):
        """Test getting global monitoring system"""
        system1 = get_monitoring_system()
        system2 = get_monitoring_system()
        
        # Should return the same instance (singleton)
        assert system1 is system2
    
    @pytest.mark.asyncio
    async def test_convenience_functions(self):
        """Test convenience functions"""
        # Mock the global monitoring system
        mock_system = Mock()
        mock_system.log_info = AsyncMock()
        mock_system.log_warning = AsyncMock()
        mock_system.log_error = AsyncMock()
        mock_system.record_metric = AsyncMock()
        mock_system.send_alert = AsyncMock()
        
        with patch('campfirevalley.monitoring.get_monitoring_system', return_value=mock_system):
            await log_info("Info message")
            await log_warning("Warning message")
            await log_error("Error message")
            await record_metric("test_metric", 100, MetricType.COUNTER)
            await send_alert("Alert", "Message", AlertSeverity.INFO)
            
            mock_system.log_info.assert_called_once_with("Info message", source=None, context=None)
            mock_system.log_warning.assert_called_once_with("Warning message", source=None, context=None)
            mock_system.log_error.assert_called_once_with("Error message", source=None, context=None)
            mock_system.record_metric.assert_called_once_with("test_metric", 100, MetricType.COUNTER, tags=None, unit=None)
            mock_system.send_alert.assert_called_once_with("Alert", "Message", AlertSeverity.INFO, source=None, tags=None)


# Integration tests
class TestMonitoringSystemIntegration:
    """Integration tests for the complete monitoring system"""
    
    @pytest.mark.asyncio
    async def test_full_monitoring_workflow(self):
        """Test complete monitoring workflow"""
        system = MonitoringSystem()
        await system.initialize()
        
        # Add health check
        async def test_service_check():
            return True, "Service is running"
        
        system.health_checker.add_health_check("test_service", test_service_check)
        
        # Log some messages
        await system.log_info("System started", source="main")
        await system.log_warning("High memory usage", source="monitor")
        
        # Record some metrics
        await system.record_metric("cpu_usage", 75.5, MetricType.GAUGE)
        await system.record_metric("requests_total", 1000, MetricType.COUNTER)
        
        # Send an alert
        await system.send_alert("Test Alert", "This is a test", AlertSeverity.INFO)
        
        # Monitor performance
        async def test_operation():
            await asyncio.sleep(0.01)
            return "completed"
        
        result = await system.monitor_performance("test_operation", test_operation)
        assert result == "completed"
        
        # Check system status
        status = await system.get_system_status()
        
        assert status["overall_health"] is True
        assert len(status["health_checks"]) == 1
        assert "metrics_summary" in status
        assert len(status["recent_alerts"]) == 1
        
        # Verify metrics were recorded
        metrics = await system.metrics_collector.get_metrics()
        assert len(metrics) >= 4  # cpu_usage, requests_total, operation_duration, operation_success
        
        # Verify logs were recorded
        logs = await system.log_handler.get_logs()
        assert len(logs) >= 2  # info and warning messages
        
        # Verify alerts were sent
        alerts = await system.alert_manager.get_alerts()
        assert len(alerts) >= 1


if __name__ == "__main__":
    pytest.main([__file__])
"""
Comprehensive Logging and Monitoring System for CampfireValley

This module provides advanced logging, metrics collection, alerting,
and performance monitoring capabilities for the valley ecosystem.
"""

import time
import json
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Callable, Union
from enum import Enum
from dataclasses import dataclass, field
from collections import defaultdict, deque
from abc import ABC, abstractmethod
import threading
from contextlib import contextmanager

# Monitoring Enums
class MetricType(Enum):
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    TIMER = "timer"

class AlertSeverity(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class LogLevel(Enum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"

# Data Classes
@dataclass
class Metric:
    name: str
    type: MetricType
    value: Union[int, float]
    timestamp: datetime = field(default_factory=datetime.utcnow)
    tags: Dict[str, str] = field(default_factory=dict)
    labels: Dict[str, str] = field(default_factory=dict)

@dataclass
class Alert:
    id: str
    severity: AlertSeverity
    message: str
    source: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    resolved: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class PerformanceMetrics:
    component: str
    operation: str
    duration: float
    success: bool
    timestamp: datetime = field(default_factory=datetime.utcnow)
    memory_usage: Optional[float] = None
    cpu_usage: Optional[float] = None
    error_message: Optional[str] = None

@dataclass
class LogEntry:
    level: LogLevel
    message: str
    component: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    context: Dict[str, Any] = field(default_factory=dict)
    correlation_id: Optional[str] = None

# Interfaces
class IMetricsCollector(ABC):
    @abstractmethod
    async def collect_metric(self, metric: Metric) -> None:
        pass
    
    @abstractmethod
    async def get_metrics(self, name: str, start_time: datetime, end_time: datetime) -> List[Metric]:
        pass

class IAlertManager(ABC):
    @abstractmethod
    async def send_alert(self, alert: Alert) -> None:
        pass
    
    @abstractmethod
    async def resolve_alert(self, alert_id: str) -> None:
        pass

class ILogHandler(ABC):
    @abstractmethod
    async def handle_log(self, entry: LogEntry) -> None:
        pass

# Implementations
class InMemoryMetricsCollector(IMetricsCollector):
    def __init__(self, max_metrics: int = 10000):
        self.metrics: Dict[str, deque] = defaultdict(lambda: deque(maxlen=max_metrics))
        self._lock = threading.Lock()
    
    async def collect_metric(self, metric: Metric) -> None:
        with self._lock:
            self.metrics[metric.name].append(metric)
    
    async def get_metrics(self, name: str, start_time: datetime, end_time: datetime) -> List[Metric]:
        with self._lock:
            if name not in self.metrics:
                return []
            
            return [
                metric for metric in self.metrics[name]
                if start_time <= metric.timestamp <= end_time
            ]
    
    def get_latest_metric(self, name: str) -> Optional[Metric]:
        with self._lock:
            if name in self.metrics and self.metrics[name]:
                return self.metrics[name][-1]
            return None

class ConsoleAlertManager(IAlertManager):
    def __init__(self):
        self.alerts: Dict[str, Alert] = {}
        self.logger = logging.getLogger(__name__)
    
    async def send_alert(self, alert: Alert) -> None:
        self.alerts[alert.id] = alert
        severity_emoji = {
            AlertSeverity.LOW: "🟡",
            AlertSeverity.MEDIUM: "🟠", 
            AlertSeverity.HIGH: "🔴",
            AlertSeverity.CRITICAL: "🚨"
        }
        
        emoji = severity_emoji.get(alert.severity, "⚠️")
        self.logger.warning(f"{emoji} ALERT [{alert.severity.value.upper()}] {alert.source}: {alert.message}")
    
    async def resolve_alert(self, alert_id: str) -> None:
        if alert_id in self.alerts:
            self.alerts[alert_id].resolved = True
            self.logger.info(f"✅ Alert {alert_id} resolved")

class StructuredLogHandler(ILogHandler):
    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger(__name__)
        self.log_entries: deque = deque(maxlen=1000)
    
    async def handle_log(self, entry: LogEntry) -> None:
        self.log_entries.append(entry)
        
        # Format structured log
        log_data = {
            "timestamp": entry.timestamp.isoformat(),
            "level": entry.level.value,
            "component": entry.component,
            "message": entry.message,
            "context": entry.context
        }
        
        if entry.correlation_id:
            log_data["correlation_id"] = entry.correlation_id
        
        # Log to standard logger
        log_level = getattr(logging, entry.level.value.upper())
        self.logger.log(log_level, json.dumps(log_data))

class PerformanceMonitor:
    def __init__(self, metrics_collector: IMetricsCollector):
        self.metrics_collector = metrics_collector
        self.active_operations: Dict[str, float] = {}
        self._lock = threading.Lock()
    
    @contextmanager
    def monitor_operation(self, component: str, operation: str):
        operation_id = f"{component}.{operation}.{int(time.time() * 1000)}"
        start_time = time.time()
        
        with self._lock:
            self.active_operations[operation_id] = start_time
        
        try:
            yield
            success = True
            error_message = None
        except Exception as e:
            success = False
            error_message = str(e)
            raise
        finally:
            end_time = time.time()
            duration = end_time - start_time
            
            with self._lock:
                self.active_operations.pop(operation_id, None)
            
            # Record performance metrics
            perf_metric = PerformanceMetrics(
                component=component,
                operation=operation,
                duration=duration,
                success=success,
                error_message=error_message
            )
            
            # Convert to metric and collect
            metric = Metric(
                name=f"{component}.{operation}.duration",
                type=MetricType.TIMER,
                value=duration,
                tags={"component": component, "operation": operation, "success": str(success)}
            )
            
            asyncio.create_task(self.metrics_collector.collect_metric(metric))

class HealthChecker:
    def __init__(self, metrics_collector: IMetricsCollector, alert_manager: IAlertManager):
        self.metrics_collector = metrics_collector
        self.alert_manager = alert_manager
        self.health_checks: Dict[str, Callable] = {}
        self.thresholds: Dict[str, Dict[str, Any]] = {}
        self.running = False
        self.check_interval = 30  # seconds
    
    def register_health_check(self, name: str, check_func: Callable, thresholds: Dict[str, Any]):
        self.health_checks[name] = check_func
        self.thresholds[name] = thresholds
    
    async def start_monitoring(self):
        self.running = True
        while self.running:
            await self._run_health_checks()
            await asyncio.sleep(self.check_interval)
    
    def stop_monitoring(self):
        self.running = False
    
    async def _run_health_checks(self):
        for name, check_func in self.health_checks.items():
            try:
                result = await check_func() if asyncio.iscoroutinefunction(check_func) else check_func()
                
                # Record health metric
                metric = Metric(
                    name=f"health.{name}",
                    type=MetricType.GAUGE,
                    value=1 if result else 0,
                    tags={"check": name}
                )
                await self.metrics_collector.collect_metric(metric)
                
                # Check thresholds and send alerts
                if not result and name in self.thresholds:
                    alert = Alert(
                        id=f"health.{name}.{int(time.time())}",
                        severity=AlertSeverity.HIGH,
                        message=f"Health check failed: {name}",
                        source="HealthChecker"
                    )
                    await self.alert_manager.send_alert(alert)
                    
            except Exception as e:
                # Health check itself failed
                alert = Alert(
                    id=f"health.{name}.error.{int(time.time())}",
                    severity=AlertSeverity.CRITICAL,
                    message=f"Health check error for {name}: {str(e)}",
                    source="HealthChecker"
                )
                await self.alert_manager.send_alert(alert)

class MonitoringSystem:
    def __init__(self):
        self.metrics_collector = InMemoryMetricsCollector()
        self.alert_manager = ConsoleAlertManager()
        self.log_handler = StructuredLogHandler()
        self.performance_monitor = PerformanceMonitor(self.metrics_collector)
        self.health_checker = HealthChecker(self.metrics_collector, self.alert_manager)
        
        # Setup default health checks
        self._setup_default_health_checks()
    
    def _setup_default_health_checks(self):
        """Setup default health checks for the system"""
        
        async def memory_check():
            try:
                import psutil
                memory = psutil.virtual_memory()
                return memory.percent < 90  # Alert if memory usage > 90%
            except ImportError:
                return True  # Skip if psutil not available
        
        async def disk_check():
            try:
                import psutil
                disk = psutil.disk_usage('/')
                return disk.percent < 95  # Alert if disk usage > 95%
            except (ImportError, FileNotFoundError):
                return True  # Skip if psutil not available or on Windows
        
        self.health_checker.register_health_check(
            "memory_usage", 
            memory_check, 
            {"max_percent": 90}
        )
        
        self.health_checker.register_health_check(
            "disk_usage", 
            disk_check, 
            {"max_percent": 95}
        )
    
    async def log(self, level: LogLevel, message: str, component: str, 
                  context: Optional[Dict[str, Any]] = None, 
                  correlation_id: Optional[str] = None):
        """Log a message with structured logging"""
        entry = LogEntry(
            level=level,
            message=message,
            component=component,
            context=context or {},
            correlation_id=correlation_id
        )
        await self.log_handler.handle_log(entry)
    
    async def record_metric(self, name: str, value: Union[int, float], 
                           metric_type: MetricType = MetricType.GAUGE,
                           tags: Optional[Dict[str, str]] = None):
        """Record a metric"""
        metric = Metric(
            name=name,
            type=metric_type,
            value=value,
            tags=tags or {}
        )
        await self.metrics_collector.collect_metric(metric)
    
    async def send_alert(self, severity: AlertSeverity, message: str, source: str,
                        metadata: Optional[Dict[str, Any]] = None):
        """Send an alert"""
        alert = Alert(
            id=f"{source}.{int(time.time())}",
            severity=severity,
            message=message,
            source=source,
            metadata=metadata or {}
        )
        await self.alert_manager.send_alert(alert)
    
    def monitor_performance(self, component: str, operation: str):
        """Context manager for monitoring operation performance"""
        return self.performance_monitor.monitor_operation(component, operation)
    
    async def start_health_monitoring(self):
        """Start the health monitoring system"""
        await self.health_checker.start_monitoring()
    
    def stop_health_monitoring(self):
        """Stop the health monitoring system"""
        self.health_checker.stop_monitoring()
    
    async def get_system_status(self) -> Dict[str, Any]:
        """Get overall system status"""
        now = datetime.utcnow()
        last_hour = now - timedelta(hours=1)
        
        # Get recent metrics
        status = {
            "timestamp": now.isoformat(),
            "health_checks": {},
            "recent_alerts": [],
            "performance_summary": {}
        }
        
        # Check recent alerts
        recent_alerts = [
            alert for alert in self.alert_manager.alerts.values()
            if alert.timestamp >= last_hour and not alert.resolved
        ]
        status["recent_alerts"] = [
            {
                "id": alert.id,
                "severity": alert.severity.value,
                "message": alert.message,
                "source": alert.source,
                "timestamp": alert.timestamp.isoformat()
            }
            for alert in recent_alerts
        ]
        
        return status

# Global monitoring instance
_monitoring_system = None

def get_monitoring_system() -> MonitoringSystem:
    """Get the global monitoring system instance"""
    global _monitoring_system
    if _monitoring_system is None:
        _monitoring_system = MonitoringSystem()
    return _monitoring_system

# Convenience functions
async def log_info(message: str, component: str, **kwargs):
    monitoring = get_monitoring_system()
    await monitoring.log(LogLevel.INFO, message, component, **kwargs)

async def log_error(message: str, component: str, **kwargs):
    monitoring = get_monitoring_system()
    await monitoring.log(LogLevel.ERROR, message, component, **kwargs)

async def log_warning(message: str, component: str, **kwargs):
    monitoring = get_monitoring_system()
    await monitoring.log(LogLevel.WARNING, message, component, **kwargs)

async def record_counter(name: str, value: int = 1, tags: Optional[Dict[str, str]] = None):
    monitoring = get_monitoring_system()
    await monitoring.record_metric(name, value, MetricType.COUNTER, tags)

async def record_gauge(name: str, value: Union[int, float], tags: Optional[Dict[str, str]] = None):
    monitoring = get_monitoring_system()
    await monitoring.record_metric(name, value, MetricType.GAUGE, tags)

async def send_alert(severity: AlertSeverity, message: str, source: str, **kwargs):
    monitoring = get_monitoring_system()
    await monitoring.send_alert(severity, message, source, **kwargs)
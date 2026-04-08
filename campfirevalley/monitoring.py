"""
Comprehensive Logging and Monitoring System for CampfireValley

This module provides advanced logging, metrics collection, alerting,
and performance monitoring capabilities for the valley ecosystem.
"""

import time
import json
import logging
import asyncio
import math
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
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

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
    metric_type: MetricType
    value: Union[int, float]
    timestamp: datetime = field(default_factory=datetime.utcnow)
    tags: Dict[str, str] = field(default_factory=dict)
    unit: Optional[str] = None

    @property
    def type(self) -> MetricType:
        return self.metric_type

@dataclass
class Alert:
    id: str
    title: str
    severity: AlertSeverity
    message: str
    source: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    resolved: bool = False
    tags: Dict[str, Any] = field(default_factory=dict)

@dataclass
class PerformanceMetrics:
    operation: str
    duration: float
    success: bool
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class LogEntry:
    level: LogLevel
    message: str
    source: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    context: Dict[str, Any] = field(default_factory=dict)
    correlation_id: Optional[str] = None

# Interfaces
class IMetricsCollector(ABC):
    @abstractmethod
    async def record_metric(self, metric: Metric) -> None:
        pass
    
    @abstractmethod
    async def get_metrics(self, metric_name: Optional[str] = None, limit: Optional[int] = None) -> List[Metric]:
        pass

    @abstractmethod
    async def get_metric_summary(self, metric_name: str) -> Dict[str, Any]:
        pass

    @abstractmethod
    async def clear_metrics(self) -> None:
        pass

class IAlertManager(ABC):
    @abstractmethod
    async def send_alert(self, alert: Alert) -> None:
        pass
    
    @abstractmethod
    async def get_alerts(self, severity: Optional[AlertSeverity] = None, limit: Optional[int] = None) -> List[Alert]:
        pass

    @abstractmethod
    async def resolve_alert(self, alert_id: str) -> None:
        pass

class ILogHandler(ABC):
    @abstractmethod
    async def log(self, entry: LogEntry) -> None:
        pass

    @abstractmethod
    async def get_logs(self, level: Optional[LogLevel] = None, limit: Optional[int] = None) -> List[LogEntry]:
        pass

# Implementations
class InMemoryMetricsCollector(IMetricsCollector):
    def __init__(self, max_metrics: int = 10000):
        self._max_metrics = max_metrics
        self.metrics: List[Metric] = []
        self._lock = threading.Lock()

    async def record_metric(self, metric: Metric) -> None:
        with self._lock:
            self.metrics.append(metric)
            if len(self.metrics) > self._max_metrics:
                self.metrics = self.metrics[-self._max_metrics :]

    async def get_metrics(self, metric_name: Optional[str] = None, limit: Optional[int] = None) -> List[Metric]:
        with self._lock:
            items = [m for m in self.metrics if (metric_name is None or m.name == metric_name)]
            if limit is not None:
                try:
                    limit = int(limit)
                except Exception:
                    limit = None
            if limit:
                items = items[-limit:]
            return list(items)

    async def get_metric_summary(self, metric_name: str) -> Dict[str, Any]:
        metrics = await self.get_metrics(metric_name=metric_name)
        if not metrics:
            return {"count": 0, "min": None, "max": None, "avg": None, "latest": None}
        values = [m.value for m in metrics]
        return {
            "count": len(values),
            "min": min(values),
            "max": max(values),
            "avg": sum(values) / len(values) if values else None,
            "latest": values[-1] if values else None,
        }

    async def clear_metrics(self) -> None:
        with self._lock:
            self.metrics.clear()

class ConsoleAlertManager(IAlertManager):
    def __init__(self):
        self.alerts: Dict[str, Alert] = {}
        self.logger = logging.getLogger(__name__)
    
    async def send_alert(self, alert: Alert) -> None:
        self.alerts[alert.id] = alert
        print(f"[{alert.severity.name}] {alert.title}: {alert.message} ({alert.source})")

    async def get_alerts(self, severity: Optional[AlertSeverity] = None, limit: Optional[int] = None) -> List[Alert]:
        items = list(self.alerts.values())
        if severity is not None:
            items = [a for a in items if a.severity == severity]
        items.sort(key=lambda a: a.timestamp)
        if limit is not None:
            try:
                limit = int(limit)
            except Exception:
                limit = None
        if limit:
            items = items[-limit:]
        return items
    
    async def resolve_alert(self, alert_id: str) -> None:
        if alert_id in self.alerts:
            self.alerts[alert_id].resolved = True
            self.logger.info(f"✅ Alert {alert_id} resolved")

class StructuredLogHandler(ILogHandler):
    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger(__name__)
        self.log_entries: deque = deque(maxlen=1000)
    
    async def log(self, entry: LogEntry) -> None:
        self.log_entries.append(entry)
        
        log_data = {
            "timestamp": entry.timestamp.isoformat(),
            "level": entry.level.name,
            "source": entry.source,
            "message": entry.message,
            "context": entry.context
        }
        
        if entry.correlation_id:
            log_data["correlation_id"] = entry.correlation_id
        print(json.dumps(log_data))

    async def handle_log(self, entry: LogEntry) -> None:
        await self.log(entry)

    async def get_logs(self, level: Optional[LogLevel] = None, limit: Optional[int] = None) -> List[LogEntry]:
        items = list(self.log_entries)
        if level is not None:
            items = [e for e in items if e.level == level]
        if limit is not None:
            try:
                limit = int(limit)
            except Exception:
                limit = None
        if limit:
            items = items[-limit:]
        return items

class PerformanceMonitor:
    def __init__(self, metrics_collector: IMetricsCollector):
        self.metrics_collector = metrics_collector
        self.performance_history: List[PerformanceMetrics] = []

    async def monitor_performance(self, operation: str, func: Callable, *args, **kwargs):
        start = time.perf_counter()
        try:
            result = await func(*args, **kwargs) if asyncio.iscoroutinefunction(func) else func(*args, **kwargs)
        except Exception:
            duration_ms = math.ceil((time.perf_counter() - start) * 1000.0)
            pm = PerformanceMetrics(operation=operation, duration=duration_ms, success=False)
            await self.record_performance_metrics(pm)
            raise
        duration_ms = math.ceil((time.perf_counter() - start) * 1000.0)
        pm = PerformanceMetrics(operation=operation, duration=duration_ms, success=True)
        await self.record_performance_metrics(pm)
        return result

    async def record_performance_metrics(self, perf: PerformanceMetrics) -> None:
        self.performance_history.append(perf)
        await self.metrics_collector.record_metric(
            Metric(
                name="operation_duration",
                value=perf.duration,
                metric_type=MetricType.HISTOGRAM,
                tags={"operation": perf.operation},
            )
        )
        await self.metrics_collector.record_metric(
            Metric(
                name="operation_success" if perf.success else "operation_failure",
                value=1,
                metric_type=MetricType.COUNTER,
                tags={"operation": perf.operation},
            )
        )

    async def get_performance_summary(self, operation: str) -> Dict[str, Any]:
        items = [p for p in self.performance_history if p.operation == operation]
        if not items:
            return {"total_operations": 0, "successful_operations": 0, "failed_operations": 0, "success_rate": 0.0, "avg_duration": None}
        total = len(items)
        success = len([p for p in items if p.success])
        failed = total - success
        avg = sum([p.duration for p in items]) / total
        return {
            "total_operations": total,
            "successful_operations": success,
            "failed_operations": failed,
            "success_rate": success / total if total else 0.0,
            "avg_duration": avg,
        }

    def monitor_operation(self, component: str, operation: str):
        @contextmanager
        def _cm():
            yield
        return _cm()

class HealthChecker:
    def __init__(self, metrics_collector: IMetricsCollector, alert_manager: IAlertManager):
        self.metrics_collector = metrics_collector
        self.alert_manager = alert_manager
        self.health_checks: Dict[str, Callable] = {}

    def add_health_check(self, name: str, check_func: Callable) -> None:
        self.health_checks[name] = check_func

    async def check_health(self, service_name: Optional[str] = None) -> Dict[str, Any]:
        names = [service_name] if service_name else list(self.health_checks.keys())
        results: Dict[str, Any] = {}
        for name in names:
            check = self.health_checks.get(name)
            if not check:
                continue
            try:
                healthy, msg = await check() if asyncio.iscoroutinefunction(check) else check()
            except Exception as e:
                healthy, msg = False, str(e)
            results[name] = {"healthy": bool(healthy), "message": msg}
            await self.metrics_collector.record_metric(
                Metric(name="service_health", value=1 if healthy else 0, metric_type=MetricType.GAUGE, tags={"service": name})
            )
            if not healthy:
                await self.alert_manager.send_alert(
                    Alert(
                        id=f"health_{name}_{int(time.time())}",
                        title=f"Health check failed: {name}",
                        message=msg,
                        severity=AlertSeverity.WARNING,
                        source="HealthChecker",
                    )
                )
        return results

class MonitoringSystem:
    def __init__(self):
        self.metrics_collector: Optional[IMetricsCollector] = None
        self.alert_manager: Optional[IAlertManager] = None
        self.log_handler: Optional[ILogHandler] = None
        self.performance_monitor: Optional[PerformanceMonitor] = None
        self.health_checker: Optional[HealthChecker] = None

    async def initialize(self) -> None:
        if self.metrics_collector is None:
            self.metrics_collector = InMemoryMetricsCollector()
        if self.alert_manager is None:
            self.alert_manager = ConsoleAlertManager()
        if self.log_handler is None:
            self.log_handler = StructuredLogHandler()
        if self.performance_monitor is None:
            self.performance_monitor = PerformanceMonitor(self.metrics_collector)
        if self.health_checker is None:
            self.health_checker = HealthChecker(self.metrics_collector, self.alert_manager)
        return None
    
    def _setup_default_health_checks(self):
        return None
    
    async def log(self, level: LogLevel, message: str, component: str,
                  context: Optional[Dict[str, Any]] = None,
                  correlation_id: Optional[str] = None):
        if not self.log_handler:
            await self.initialize()
        entry = LogEntry(level=level, message=message, source=component, context=context or {}, correlation_id=correlation_id)
        await self.log_handler.log(entry)

    async def log_info(self, message: str, source: Optional[str] = None, context: Optional[Dict[str, Any]] = None):
        await self.log(LogLevel.INFO, message, source or "app", context=context)

    async def log_warning(self, message: str, source: Optional[str] = None, context: Optional[Dict[str, Any]] = None):
        await self.log(LogLevel.WARNING, message, source or "app", context=context)

    async def log_error(self, message: str, source: Optional[str] = None, context: Optional[Dict[str, Any]] = None):
        await self.log(LogLevel.ERROR, message, source or "app", context=context)
    
    async def record_metric(self, name: str, value: Union[int, float],
                           metric_type: MetricType = MetricType.GAUGE,
                           tags: Optional[Dict[str, str]] = None,
                           unit: Optional[str] = None):
        if not self.metrics_collector:
            await self.initialize()
        metric = Metric(name=name, value=value, metric_type=metric_type, tags=tags or {}, unit=unit)
        await self.metrics_collector.record_metric(metric)
    
    async def send_alert(self, title: str, message: str, severity: AlertSeverity, source: Optional[str] = None, tags: Optional[Dict[str, Any]] = None):
        if not self.alert_manager:
            await self.initialize()
        alert = Alert(id=f"alert_{int(time.time()*1000)}", title=title, message=message, severity=severity, source=source or "app", tags=tags or {})
        await self.alert_manager.send_alert(alert)
    
    async def monitor_performance(self, operation: str, func: Callable, *args, **kwargs):
        if not self.performance_monitor:
            await self.initialize()
        return await self.performance_monitor.monitor_performance(operation, func, *args, **kwargs)
    
    async def get_system_status(self) -> Dict[str, Any]:
        if not self.health_checker or not self.metrics_collector or not self.alert_manager:
            await self.initialize()
        health = await self.health_checker.check_health()
        overall = all(v.get("healthy") for v in health.values()) if health else True
        recent_alerts = await self.alert_manager.get_alerts(limit=10)
        metrics_summary = {}
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "health_checks": health,
            "metrics_summary": metrics_summary,
            "recent_alerts": recent_alerts,
            "overall_health": overall,
        }

# Global monitoring instance
_monitoring_system = None

def get_monitoring_system() -> MonitoringSystem:
    """Get the global monitoring system instance"""
    global _monitoring_system
    if _monitoring_system is None:
        _monitoring_system = MonitoringSystem()
    return _monitoring_system

# Convenience functions
async def log_info(message: str, source: Optional[str] = None, context: Optional[Dict[str, Any]] = None):
    monitoring = get_monitoring_system()
    await monitoring.log_info(message, source=source, context=context)

async def log_warning(message: str, source: Optional[str] = None, context: Optional[Dict[str, Any]] = None):
    monitoring = get_monitoring_system()
    await monitoring.log_warning(message, source=source, context=context)

async def log_error(message: str, source: Optional[str] = None, context: Optional[Dict[str, Any]] = None):
    monitoring = get_monitoring_system()
    await monitoring.log_error(message, source=source, context=context)

async def record_metric(name: str, value: Union[int, float], metric_type: MetricType, tags: Optional[Dict[str, str]] = None, unit: Optional[str] = None):
    monitoring = get_monitoring_system()
    await monitoring.record_metric(name, value, metric_type, tags=tags, unit=unit)

async def record_counter(name: str, value: int = 1, tags: Optional[Dict[str, str]] = None):
    monitoring = get_monitoring_system()
    await monitoring.record_metric(name, value, MetricType.COUNTER, tags)

async def record_gauge(name: str, value: Union[int, float], tags: Optional[Dict[str, str]] = None):
    monitoring = get_monitoring_system()
    await monitoring.record_metric(name, value, MetricType.GAUGE, tags)

async def send_alert(title: str, message: str, severity: AlertSeverity, source: Optional[str] = None, tags: Optional[Dict[str, Any]] = None):
    monitoring = get_monitoring_system()
    await monitoring.send_alert(title, message, severity, source=source, tags=tags)

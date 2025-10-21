"""CampfireValley - A distributed torch processing framework

CampfireValley provides a secure, scalable platform for processing and routing
"torches" (data packets) across a network of valleys (nodes) using campfires
(processing units) and campers (workers).

Built on top of the pyCampfires framework for LLM orchestration and multimodal AI.
"""

# Import base campfires framework
from campfires import (
    Campfire as BaseCampfire,
    Camper as BaseCamper,
    Torch as BaseTorch,
    LLMCamperMixin,
    OpenRouterConfig,
    MultimodalCamperMixin,
    MultimodalLLMCamperMixin,
    ZeitgeistEngine,
    ZeitgeistConfig
)
from campfires.core.ollama import OllamaConfig

# CampfireValley core modules
from .models import *
from .interfaces import *
from .config import ValleyConfig, CampfireConfig
from .valley import Valley
from .campfire import Campfire
from .llm_campfire import LLMCampfire, LLMCamper, create_openrouter_campfire, create_ollama_campfire
from .mcp import RedisMCPBroker
from .key_manager import CampfireKeyManager, IKeyManager
from . import campfires
from .vali import (
    VALICoordinator, VALIServiceRegistry, IVALIService, BaseVALIService,
    VALIServiceType, VALIServiceStatus, ContentValidatorService, SignatureVerifierService
)
from .security_scanner import EnhancedSecurityScanner, ThreatLevel, ScanEngine, ThreatSignature

# Justice System
from .justice import (
    JusticeSystem, PolicyEngine, EnforcementEngine,
    PolicyRule, ViolationEvent, EnforcementAction,
    ViolationType, ActionType, Severity
)

# Specialist Campfires
from .specialist_campfires import (
    SanitizerCampfire, ValidatorCampfire, RouterCampfire,
    SanitizationLevel, ValidationMode, RoutingStrategy,
    SanitizationRule, ValidationRule, RoutingRule
)

# Advanced Routing
from .routing import (
    AdvancedRoutingEngine, RouteOptimizer, SmartLoadBalancer,
    RouteStatus, LoadBalancingAlgorithm, FailoverStrategy,
    RouteMetrics, RouteNode, RoutePath, RouteRequest, RouteResponse,
    IRouteHealthChecker, ILoadBalancer, BasicHealthChecker
)

# Monitoring and Logging
from .monitoring import (
    MonitoringSystem, PerformanceMonitor, HealthChecker,
    MetricType, AlertSeverity, LogLevel,
    Metric, Alert, PerformanceMetrics, LogEntry,
    IMetricsCollector, IAlertManager, ILogHandler,
    InMemoryMetricsCollector, ConsoleAlertManager, StructuredLogHandler,
    get_monitoring_system, log_info, log_warning, log_error,
    record_counter, record_gauge, send_alert
)

# Configuration Management
from .config_manager import (
    ConfigManager, ConfigFormat, ConfigScope, ConfigEnvironment,
    ConfigSource, ConfigValidationRule, ConfigChange, ConfigVersion,
    IConfigProvider, IConfigValidator, IConfigEncryption,
    FileConfigProvider, SchemaConfigValidator, SimpleConfigEncryption,
    get_config_manager, load_config_from_file, get_config_value,
    set_config_value, config_override
)

# Hierarchical Storage and Enhanced Party Box
from .hierarchical_storage import (
    HierarchicalStorageManager, StorageTier, StoragePolicy, CompressionType,
    AccessPattern, CompressionManager, DeduplicationManager, HierarchicalPartyBox
)
from .party_box import (
    FileSystemPartyBox, PartyBoxManager
)

__version__ = "1.1.0"

__all__ = [
    # Core classes
    "Valley",
    "Campfire", 
    "LLMCampfire",
    "LLMCamper",
    "RedisMCPBroker",
    "CampfireKeyManager",
    
    # Base pyCampfires components
    "BaseCampfire",
    "BaseCamper",
    "BaseTorch",
    "LLMCamperMixin",
    "OpenRouterConfig",
    "OllamaConfig",

    
    # Factory functions
    "create_openrouter_campfire",
    "create_ollama_campfire",
    
    # Default campfires
    "campfires",
    
    # VALI Services
    "VALICoordinator",
    "VALIServiceRegistry", 
    "IVALIService",
    "BaseVALIService",
    "VALIServiceType",
    "VALIServiceStatus",
    "ContentValidatorService",
    "SignatureVerifierService",
    "EnhancedSecurityScanner",
    "ThreatLevel",
    "ScanEngine", 
    "ThreatSignature",
    
    # Justice System
    "JusticeSystem",
    "PolicyEngine",
    "EnforcementEngine", 
    "PolicyRule",
    "ViolationEvent",
    "EnforcementAction",
    "ViolationType",
    "ActionType",
    "Severity",
    
    # Specialist Campfires
    "SanitizerCampfire",
    "ValidatorCampfire",
    "RouterCampfire",
    "SanitizationLevel",
    "ValidationMode",
    "RoutingStrategy",
    "SanitizationRule",
    "ValidationRule",
    "RoutingRule",
    
    # Advanced Routing
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
    
    # Monitoring and Logging
    "MonitoringSystem",
    "PerformanceMonitor",
    "HealthChecker",
    "MetricType",
    "AlertSeverity",
    "LogLevel",
    "Metric",
    "Alert",
    "PerformanceMetrics",
    "LogEntry",
    "IMetricsCollector",
    "IAlertManager",
    "ILogHandler",
    "InMemoryMetricsCollector",
    "ConsoleAlertManager",
    "StructuredLogHandler",
    "get_monitoring_system",
    "log_info",
    "log_warning",
    "log_error",
    "record_metric",
    "send_alert",
    
    # Configuration Management
    "ConfigManager",
    "ConfigFormat",
    "ConfigScope",
    "ConfigEnvironment",
    "ConfigSource",
    "ConfigValidationRule",
    "ConfigChange",
    "ConfigVersion",
    "IConfigProvider",
    "IConfigValidator",
    "IConfigEncryption",
    "FileConfigProvider",
    "SchemaConfigValidator",
    "SimpleConfigEncryption",
    "get_config_manager",
    "load_config_from_file",
    "get_config_value",
    "set_config_value",
    "config_override",
    
    # Hierarchical Storage and Enhanced Party Box
    "HierarchicalStorageManager",
    "StorageTier",
    "StoragePolicy",
    "CompressionType",
    "AccessPattern",
    "DataLifecycleManager",
    "StorageOptimizer",
    "DeduplicationEngine",
    "CompressionEngine",
    "HierarchicalPartyBox",
    "FileSystemPartyBox",
    "PartyBoxManager",
    "create_filesystem_party_box",
    "create_hierarchical_party_box",
    "migrate_from_filesystem_party_box",
    
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
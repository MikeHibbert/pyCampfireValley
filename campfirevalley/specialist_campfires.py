"""Specialist Campfires for CampfireValley

This module provides specialized campfire implementations for specific tasks:
- SanitizerCampfire: Sanitizes torch content
- ValidatorCampfire: Validates torch content using VALI services
- RouterCampfire: Advanced routing with rules and strategies
"""

import asyncio
import json
import re
import html
import logging
import hashlib
from typing import Dict, List, Any, Optional, Set, Tuple, Callable
from datetime import datetime, timedelta
from enum import Enum
from dataclasses import dataclass, field
from abc import ABC, abstractmethod

from .models import Torch, SecurityLevel, CampfireConfig
from .interfaces import ICampfire, IMCPBroker, IKeyManager, IJustice
from .campfire import Campfire
from .vali import VALICoordinator, VALIServiceType
from .justice import JusticeSystem, ActionType
from .routing import AdvancedRoutingEngine, RouteRequest, RouteNode, LoadBalancingAlgorithm


class SanitizationLevel(str, Enum):
    """Levels of sanitization to apply"""
    BASIC = "basic"
    STANDARD = "standard"
    AGGRESSIVE = "aggressive"
    CUSTOM = "custom"


class ValidationMode(str, Enum):
    """Validation modes"""
    STRICT = "strict"
    STANDARD = "standard"
    PERMISSIVE = "permissive"


class RoutingStrategy(str, Enum):
    """Routing strategies"""
    DIRECT = "direct"
    LOAD_BALANCED = "load_balanced"
    MULTI_HOP = "multi_hop"
    FAILOVER = "failover"
    BROADCAST = "broadcast"


@dataclass
class SanitizationRule:
    """Rule for sanitizing torch content"""
    name: str
    pattern: str
    replacement: str
    description: str
    enabled: bool = True
    regex_flags: int = re.IGNORECASE


@dataclass
class ValidationRule:
    """Rule for validating torch content"""
    name: str
    condition: str  # JSON condition
    error_message: str
    severity: str = "error"  # error, warning, info
    enabled: bool = True


@dataclass
class RoutingRule:
    """Rule for routing decisions"""
    name: str
    condition: str  # JSON condition
    target_addresses: List[str]
    priority: int = 0
    enabled: bool = True


class SanitizerCampfire(Campfire):
    """
    Specialized campfire for sanitizing torch content
    """
    
    def __init__(
        self,
        config: CampfireConfig,
        mcp_broker: IMCPBroker,
        key_manager: IKeyManager,
        sanitization_level: SanitizationLevel = SanitizationLevel.STANDARD
    ):
        super().__init__(config, mcp_broker, key_manager)
        self.sanitization_level = sanitization_level
        self.sanitization_rules: List[SanitizationRule] = []
        self.custom_sanitizers: Dict[str, Callable] = {}
        self._load_default_rules()
    
    def _load_default_rules(self):
        """Load default sanitization rules"""
        default_rules = [
            # XSS Prevention
            SanitizationRule(
                name="remove_script_tags",
                pattern=r"<script[^>]*>.*?</script>",
                replacement="[SCRIPT_REMOVED]",
                description="Remove script tags to prevent XSS"
            ),
            SanitizationRule(
                name="remove_event_handlers",
                pattern=r"\s*on\w+\s*=\s*[\"'][^\"']*[\"']",
                replacement="",
                description="Remove event handlers"
            ),
            
            # SQL Injection Prevention
            SanitizationRule(
                name="escape_sql_keywords",
                pattern=r"\b(union|select|insert|delete|drop|create|alter)\s+",
                replacement=lambda m: m.group(0).replace(" ", "_"),
                description="Escape SQL keywords"
            ),
            
            # Code Execution Prevention
            SanitizationRule(
                name="remove_exec_functions",
                pattern=r"\b(eval|exec|system|shell_exec|passthru)\s*\(",
                replacement="[EXEC_REMOVED](",
                description="Remove code execution functions"
            ),
            
            # Path Traversal Prevention
            SanitizationRule(
                name="sanitize_paths",
                pattern=r"\.\.[\\/]+",
                replacement="",
                description="Remove path traversal sequences"
            ),
            
            # Command Injection Prevention
            SanitizationRule(
                name="escape_command_chars",
                pattern=r"[;&|`$(){}[\]<>]",
                replacement=lambda m: f"\\{m.group(0)}",
                description="Escape command injection characters"
            ),
            
            # URL Sanitization
            SanitizationRule(
                name="sanitize_suspicious_urls",
                pattern=r"https?://[^\s]*\.(tk|ml|ga|cf)\b",
                replacement="[SUSPICIOUS_URL_REMOVED]",
                description="Remove suspicious URL domains"
            ),
            
            # Data Sanitization
            SanitizationRule(
                name="mask_sensitive_data",
                pattern=r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b",
                replacement="[CARD_NUMBER_MASKED]",
                description="Mask credit card numbers"
            ),
            SanitizationRule(
                name="mask_ssn",
                pattern=r"\b\d{3}-\d{2}-\d{4}\b",
                replacement="[SSN_MASKED]",
                description="Mask social security numbers"
            ),
        ]
        
        # Filter rules based on sanitization level
        if self.sanitization_level == SanitizationLevel.BASIC:
            self.sanitization_rules = [r for r in default_rules if r.name in [
                "remove_script_tags", "remove_exec_functions"
            ]]
        elif self.sanitization_level == SanitizationLevel.STANDARD:
            self.sanitization_rules = [r for r in default_rules if r.name not in [
                "mask_sensitive_data", "mask_ssn"
            ]]
        elif self.sanitization_level == SanitizationLevel.AGGRESSIVE:
            self.sanitization_rules = default_rules
        # CUSTOM level starts with no rules - user must add them
    
    def add_sanitization_rule(self, rule: SanitizationRule):
        """Add a custom sanitization rule"""
        self.sanitization_rules.append(rule)
        self.logger.info(f"Added sanitization rule: {rule.name}")
    
    def remove_sanitization_rule(self, rule_name: str):
        """Remove a sanitization rule"""
        self.sanitization_rules = [r for r in self.sanitization_rules if r.name != rule_name]
        self.logger.info(f"Removed sanitization rule: {rule_name}")
    
    def register_custom_sanitizer(self, name: str, sanitizer: Callable[[str], str]):
        """Register a custom sanitizer function"""
        self.custom_sanitizers[name] = sanitizer
        self.logger.info(f"Registered custom sanitizer: {name}")
    
    async def process_torch(self, torch: Torch) -> Torch:
        """Process and sanitize torch content"""
        try:
            self.logger.info(f"Sanitizing torch {torch.id}")
            
            # Create a copy of the torch for sanitization
            sanitized_torch = Torch(
                id=torch.id,
                sender_valley=torch.sender_valley,
                target_address=torch.target_address,
                payload=torch.payload.copy(),
                attachments=torch.attachments.copy(),
                signature=torch.signature,
                timestamp=torch.timestamp
            )
            
            # Sanitize payload
            sanitized_torch.payload = await self._sanitize_payload(sanitized_torch.payload)
            
            # Sanitize attachments
            sanitized_torch.attachments = await self._sanitize_attachments(sanitized_torch.attachments)
            
            # Update signature after sanitization
            sanitized_torch.signature = await self._generate_sanitized_signature(sanitized_torch)
            
            self.logger.info(f"Successfully sanitized torch {torch.id}")
            return sanitized_torch
            
        except Exception as e:
            self.logger.error(f"Error sanitizing torch {torch.id}: {e}")
            raise
    
    async def _sanitize_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Sanitize torch payload"""
        sanitized = {}
        
        for key, value in payload.items():
            if isinstance(value, str):
                sanitized[key] = await self._sanitize_string(value)
            elif isinstance(value, dict):
                sanitized[key] = await self._sanitize_payload(value)
            elif isinstance(value, list):
                sanitized[key] = [
                    await self._sanitize_string(item) if isinstance(item, str)
                    else await self._sanitize_payload(item) if isinstance(item, dict)
                    else item
                    for item in value
                ]
            else:
                sanitized[key] = value
        
        return sanitized
    
    async def _sanitize_string(self, text: str) -> str:
        """Sanitize a string value"""
        sanitized = text
        
        # Apply sanitization rules
        for rule in self.sanitization_rules:
            if not rule.enabled:
                continue
            
            try:
                if callable(rule.replacement):
                    sanitized = re.sub(rule.pattern, rule.replacement, sanitized, flags=rule.regex_flags)
                else:
                    sanitized = re.sub(rule.pattern, rule.replacement, sanitized, flags=rule.regex_flags)
            except Exception as e:
                self.logger.warning(f"Error applying sanitization rule {rule.name}: {e}")
        
        # Apply custom sanitizers
        for name, sanitizer in self.custom_sanitizers.items():
            try:
                sanitized = sanitizer(sanitized)
            except Exception as e:
                self.logger.warning(f"Error applying custom sanitizer {name}: {e}")
        
        return sanitized
    
    async def _sanitize_attachments(self, attachments: List[str]) -> List[str]:
        """Sanitize attachment references"""
        sanitized = []
        
        for attachment in attachments:
            # Sanitize attachment reference
            sanitized_ref = await self._sanitize_string(attachment)
            
            # Validate attachment reference format
            if self._is_valid_attachment_reference(sanitized_ref):
                sanitized.append(sanitized_ref)
            else:
                self.logger.warning(f"Invalid attachment reference removed: {attachment}")
        
        return sanitized
    
    def _is_valid_attachment_reference(self, reference: str) -> bool:
        """Validate attachment reference format"""
        # Basic validation - can be extended
        return (
            len(reference) <= 1000 and
            not re.search(r"[<>\"'&]", reference) and
            reference.strip() == reference
        )
    
    async def _generate_sanitized_signature(self, torch: Torch) -> str:
        """Generate new signature for sanitized torch"""
        content = f"{torch.id}:{torch.sender_valley}:{json.dumps(torch.payload, sort_keys=True)}"
        return hashlib.sha256(content.encode()).hexdigest()


class ValidatorCampfire(Campfire):
    """
    Specialized campfire for validating torch content
    """
    
    def __init__(
        self,
        config: CampfireConfig,
        mcp_broker: IMCPBroker,
        key_manager: IKeyManager,
        vali_coordinator: VALICoordinator,
        validation_mode: ValidationMode = ValidationMode.STANDARD
    ):
        super().__init__(config, mcp_broker, key_manager)
        self.vali_coordinator = vali_coordinator
        self.validation_mode = validation_mode
        self.validation_rules: List[ValidationRule] = []
        self.custom_validators: Dict[str, Callable] = {}
        self._load_default_rules()
    
    def _load_default_rules(self):
        """Load default validation rules"""
        default_rules = [
            ValidationRule(
                name="required_fields",
                condition=json.dumps({
                    "type": "required_fields",
                    "fields": ["type", "content"]
                }),
                error_message="Missing required fields in payload"
            ),
            ValidationRule(
                name="payload_size_limit",
                condition=json.dumps({
                    "type": "max_size",
                    "max_bytes": 10 * 1024 * 1024  # 10MB
                }),
                error_message="Payload exceeds size limit"
            ),
            ValidationRule(
                name="attachment_count_limit",
                condition=json.dumps({
                    "type": "max_attachments",
                    "max_count": 100
                }),
                error_message="Too many attachments"
            ),
            ValidationRule(
                name="valid_json_structure",
                condition=json.dumps({
                    "type": "json_valid"
                }),
                error_message="Invalid JSON structure in payload"
            ),
            ValidationRule(
                name="timestamp_validation",
                condition=json.dumps({
                    "type": "timestamp_range",
                    "max_future_hours": 1,
                    "max_past_hours": 24
                }),
                error_message="Timestamp outside acceptable range"
            ),
            ValidationRule(
                name="signature_format",
                condition=json.dumps({
                    "type": "signature_format",
                    "min_length": 32
                }),
                error_message="Invalid signature format"
            )
        ]
        
        # Filter rules based on validation mode
        if self.validation_mode == ValidationMode.PERMISSIVE:
            self.validation_rules = [r for r in default_rules if r.name in [
                "required_fields", "payload_size_limit"
            ]]
        elif self.validation_mode == ValidationMode.STANDARD:
            self.validation_rules = [r for r in default_rules if r.name != "timestamp_validation"]
        elif self.validation_mode == ValidationMode.STRICT:
            self.validation_rules = default_rules
    
    def add_validation_rule(self, rule: ValidationRule):
        """Add a custom validation rule"""
        self.validation_rules.append(rule)
        self.logger.info(f"Added validation rule: {rule.name}")
    
    def register_custom_validator(self, name: str, validator: Callable[[Torch], Tuple[bool, str]]):
        """Register a custom validator function"""
        self.custom_validators[name] = validator
        self.logger.info(f"Registered custom validator: {name}")
    
    async def process_torch(self, torch: Torch) -> Torch:
        """Process and validate torch"""
        try:
            self.logger.info(f"Validating torch {torch.id}")
            
            # Run validation rules
            validation_errors = await self._validate_torch(torch)
            
            if validation_errors:
                error_msg = "; ".join(validation_errors)
                self.logger.error(f"Torch {torch.id} validation failed: {error_msg}")
                raise ValueError(f"Validation failed: {error_msg}")
            
            # Run VALI services for additional validation
            await self._run_vali_validation(torch)
            
            self.logger.info(f"Successfully validated torch {torch.id}")
            return torch
            
        except Exception as e:
            self.logger.error(f"Error validating torch {torch.id}: {e}")
            raise
    
    async def _validate_torch(self, torch: Torch) -> List[str]:
        """Validate torch against rules"""
        errors = []
        
        for rule in self.validation_rules:
            if not rule.enabled:
                continue
            
            try:
                condition = json.loads(rule.condition)
                is_valid = await self._evaluate_validation_condition(torch, condition)
                
                if not is_valid:
                    errors.append(f"{rule.name}: {rule.error_message}")
                    
            except Exception as e:
                self.logger.warning(f"Error evaluating validation rule {rule.name}: {e}")
                if self.validation_mode == ValidationMode.STRICT:
                    errors.append(f"{rule.name}: Rule evaluation error")
        
        # Run custom validators
        for name, validator in self.custom_validators.items():
            try:
                is_valid, error_msg = validator(torch)
                if not is_valid:
                    errors.append(f"{name}: {error_msg}")
            except Exception as e:
                self.logger.warning(f"Error running custom validator {name}: {e}")
                if self.validation_mode == ValidationMode.STRICT:
                    errors.append(f"{name}: Validator error")
        
        return errors
    
    async def _evaluate_validation_condition(self, torch: Torch, condition: Dict[str, Any]) -> bool:
        """Evaluate a validation condition"""
        condition_type = condition.get("type")
        
        if condition_type == "required_fields":
            fields = condition.get("fields", [])
            return all(field in torch.payload for field in fields)
        
        elif condition_type == "max_size":
            max_bytes = condition.get("max_bytes", 0)
            payload_size = len(json.dumps(torch.payload).encode())
            return payload_size <= max_bytes
        
        elif condition_type == "max_attachments":
            max_count = condition.get("max_count", 0)
            return len(torch.attachments) <= max_count
        
        elif condition_type == "json_valid":
            try:
                json.dumps(torch.payload)
                return True
            except (TypeError, ValueError):
                return False
        
        elif condition_type == "timestamp_range":
            max_future_hours = condition.get("max_future_hours", 1)
            max_past_hours = condition.get("max_past_hours", 24)
            now = datetime.utcnow()
            
            future_limit = now + timedelta(hours=max_future_hours)
            past_limit = now - timedelta(hours=max_past_hours)
            
            return past_limit <= torch.timestamp <= future_limit
        
        elif condition_type == "signature_format":
            min_length = condition.get("min_length", 32)
            return len(torch.signature) >= min_length
        
        return True
    
    async def _run_vali_validation(self, torch: Torch):
        """Run VALI services for additional validation"""
        try:
            # Content validation
            response = await self.vali_coordinator.request_service(
                VALIServiceType.CONTENT_VALIDATION,
                {
                    "torch_id": torch.id,
                    "payload": torch.payload,
                    "attachments": torch.attachments
                }
            )
            
            if response.status != "completed":
                raise ValueError("VALI content validation failed")
            
            # Signature verification
            response = await self.vali_coordinator.request_service(
                VALIServiceType.SIGNATURE_VERIFICATION,
                {
                    "torch_id": torch.id,
                    "signature": torch.signature,
                    "payload": torch.payload
                }
            )
            
            if response.status != "completed":
                raise ValueError("VALI signature verification failed")
                
        except Exception as e:
            if self.validation_mode == ValidationMode.STRICT:
                raise
            else:
                self.logger.warning(f"VALI validation warning for torch {torch.id}: {e}")


class RouterCampfire(Campfire):
    """
    Specialized campfire for advanced torch routing
    """
    
    def __init__(
        self,
        config: CampfireConfig,
        mcp_broker: IMCPBroker,
        key_manager: IKeyManager,
        justice_system: JusticeSystem,
        default_strategy: RoutingStrategy = RoutingStrategy.DIRECT,
        routing_engine: Optional[AdvancedRoutingEngine] = None
    ):
        super().__init__(config, mcp_broker, key_manager)
        self.justice_system = justice_system
        self.default_strategy = default_strategy
        self.routing_engine = routing_engine or AdvancedRoutingEngine()
        self.routing_rules: List[RoutingRule] = []
        self.route_cache: Dict[str, Tuple[List[str], datetime]] = {}
        self.cache_ttl = timedelta(minutes=15)
        self.load_balancer_state: Dict[str, int] = {}
        self._load_default_rules()
        self._initialize_routing_network()
    
    def _load_default_rules(self):
        """Load default routing rules"""
        default_rules = [
            RoutingRule(
                name="high_priority_direct",
                condition=json.dumps({
                    "type": "payload_field",
                    "field": "priority",
                    "value": "high"
                }),
                target_addresses=["priority.valley"],
                priority=100
            ),
            RoutingRule(
                name="security_quarantine",
                condition=json.dumps({
                    "type": "payload_field",
                    "field": "security_flag",
                    "value": "quarantine"
                }),
                target_addresses=["quarantine.valley"],
                priority=90
            ),
            RoutingRule(
                name="large_payload_specialized",
                condition=json.dumps({
                    "type": "payload_size",
                    "min_size": 1024 * 1024  # 1MB
                }),
                target_addresses=["large-data.valley", "backup-large.valley"],
                priority=50
            )
        ]
        
        self.routing_rules = default_rules
    
    def _initialize_routing_network(self):
        """Initialize the routing network with default nodes"""
        # Add some default routing nodes
        default_nodes = [
            RouteNode(
                address="primary.valley",
                weight=10,
                max_connections=1000,
                capabilities={"high_throughput", "secure"}
            ),
            RouteNode(
                address="secondary.valley", 
                weight=5,
                max_connections=500,
                capabilities={"backup", "reliable"}
            ),
            RouteNode(
                address="edge.valley",
                weight=3,
                max_connections=200,
                capabilities={"edge_processing", "low_latency"}
            ),
            RouteNode(
                address="quarantine.valley",
                weight=1,
                max_connections=100,
                capabilities={"quarantine", "security"}
            )
        ]
        
        for node in default_nodes:
            self.routing_engine.add_node(node)
        
        # Add connections between nodes
        self.routing_engine.add_connection("primary.valley", "secondary.valley")
        self.routing_engine.add_connection("primary.valley", "edge.valley")
        self.routing_engine.add_connection("secondary.valley", "edge.valley")
        self.routing_engine.add_connection("edge.valley", "quarantine.valley")
    
    def add_routing_rule(self, rule: RoutingRule):
        """Add a custom routing rule"""
        self.routing_rules.append(rule)
        self.routing_rules.sort(key=lambda r: r.priority, reverse=True)
        self.logger.info(f"Added routing rule: {rule.name}")
    
    async def process_torch(self, torch: Torch) -> Torch:
        """Process and route torch using advanced routing engine"""
        try:
            self.logger.info(f"Routing torch {torch.id}")
            
            # Check with justice system first
            decision = await self.justice_system.evaluate_torch(torch)
            
            if decision.action == ActionType.BLOCK:
                raise ValueError(f"Torch blocked by justice system: {decision.reason}")
            elif decision.action == ActionType.QUARANTINE:
                torch.target_address = "quarantine.valley"
                self.logger.warning(f"Torch {torch.id} quarantined: {decision.reason}")
                return torch
            
            # Create routing request
            route_request = RouteRequest(
                torch=torch,
                source_address=torch.sender_valley,
                destination_address=torch.target_address or "primary.valley",
                requirements=self._extract_routing_requirements(torch),
                priority=self._calculate_torch_priority(torch)
            )
            
            # Use advanced routing engine
            route_response = await self.routing_engine.route_torch(route_request)
            
            if not route_response.success:
                # Fallback to legacy routing
                self.logger.warning(f"Advanced routing failed for torch {torch.id}: {route_response.error_message}")
                targets = await self._determine_routing_targets(torch)
                if targets:
                    final_target = await self._apply_routing_strategy(torch, targets)
                    torch.target_address = final_target
                else:
                    raise ValueError("No valid routing targets found")
            else:
                # Use the path from advanced routing
                if route_response.path and route_response.path.nodes:
                    # For now, use the final destination from the path
                    torch.target_address = route_response.path.nodes[-1].address
                    self.logger.info(f"Advanced routing selected path with {len(route_response.path.nodes)} hops")
            
            self.logger.info(f"Routed torch {torch.id} to {torch.target_address}")
            return torch
            
        except Exception as e:
            self.logger.error(f"Error routing torch {torch.id}: {e}")
            raise
    
    def _extract_routing_requirements(self, torch: Torch) -> Dict[str, Any]:
        """Extract routing requirements from torch"""
        requirements = {}
        
        # Extract from payload
        if "routing_requirements" in torch.payload:
            requirements.update(torch.payload["routing_requirements"])
        
        # Infer requirements from torch properties
        if "security_level" in torch.payload:
            requirements["security_level"] = torch.payload["security_level"]
        
        if "priority" in torch.payload:
            requirements["priority"] = torch.payload["priority"]
        
        # Size-based requirements
        payload_size = len(json.dumps(torch.payload).encode())
        if payload_size > 1024 * 1024:  # 1MB
            requirements["large_payload"] = True
        
        return requirements
    
    def _calculate_torch_priority(self, torch: Torch) -> int:
        """Calculate priority for torch routing"""
        priority = 0
        
        # Base priority from payload
        if "priority" in torch.payload:
            if torch.payload["priority"] == "high":
                priority += 10
            elif torch.payload["priority"] == "medium":
                priority += 5
        
        # Security-based priority
        if "security_flag" in torch.payload:
            if torch.payload["security_flag"] == "urgent":
                priority += 15
            elif torch.payload["security_flag"] == "quarantine":
                priority += 20
        
        # Time-sensitive priority
        if torch.timestamp:
            age = (datetime.utcnow() - torch.timestamp).total_seconds()
            if age > 3600:  # Older than 1 hour
                priority += 5
        
        return priority
    
    async def _determine_routing_targets(self, torch: Torch) -> List[str]:
        """Determine possible routing targets for torch"""
        # Check cache first
        cache_key = self._generate_cache_key(torch)
        cached_targets = self._get_cached_targets(cache_key)
        if cached_targets:
            return cached_targets
        
        targets = []
        
        # Evaluate routing rules
        for rule in self.routing_rules:
            if not rule.enabled:
                continue
            
            try:
                condition = json.loads(rule.condition)
                if await self._evaluate_routing_condition(torch, condition):
                    targets.extend(rule.target_addresses)
                    break  # Use first matching rule (highest priority)
            except Exception as e:
                self.logger.warning(f"Error evaluating routing rule {rule.name}: {e}")
        
        # Fallback to original target if no rules matched
        if not targets and torch.target_address:
            targets = [torch.target_address]
        
        # Cache the result
        self._cache_targets(cache_key, targets)
        
        return targets
    
    async def _evaluate_routing_condition(self, torch: Torch, condition: Dict[str, Any]) -> bool:
        """Evaluate a routing condition"""
        condition_type = condition.get("type")
        
        if condition_type == "payload_field":
            field = condition.get("field")
            value = condition.get("value")
            return torch.payload.get(field) == value
        
        elif condition_type == "payload_size":
            min_size = condition.get("min_size", 0)
            max_size = condition.get("max_size", float('inf'))
            payload_size = len(json.dumps(torch.payload).encode())
            return min_size <= payload_size <= max_size
        
        elif condition_type == "sender_valley":
            allowed_valleys = condition.get("valleys", [])
            return torch.sender_valley in allowed_valleys
        
        elif condition_type == "time_window":
            start_hour = condition.get("start_hour", 0)
            end_hour = condition.get("end_hour", 24)
            current_hour = datetime.utcnow().hour
            return start_hour <= current_hour <= end_hour
        
        return False
    
    async def _apply_routing_strategy(self, torch: Torch, targets: List[str]) -> str:
        """Apply routing strategy to select final target"""
        if len(targets) == 1:
            return targets[0]
        
        if self.default_strategy == RoutingStrategy.DIRECT:
            return targets[0]
        
        elif self.default_strategy == RoutingStrategy.LOAD_BALANCED:
            return self._load_balance_target(targets)
        
        elif self.default_strategy == RoutingStrategy.FAILOVER:
            # For now, just return first available target
            # In a real implementation, this would check target availability
            return targets[0]
        
        elif self.default_strategy == RoutingStrategy.MULTI_HOP:
            # For multi-hop, we'd typically return an intermediate target
            # For now, just use load balancing
            return self._load_balance_target(targets)
        
        elif self.default_strategy == RoutingStrategy.BROADCAST:
            # For broadcast, we'd send to all targets
            # For now, just return the first one
            return targets[0]
        
        return targets[0]
    
    def _load_balance_target(self, targets: List[str]) -> str:
        """Select target using round-robin load balancing"""
        targets_key = "|".join(sorted(targets))
        
        if targets_key not in self.load_balancer_state:
            self.load_balancer_state[targets_key] = 0
        
        index = self.load_balancer_state[targets_key] % len(targets)
        self.load_balancer_state[targets_key] += 1
        
        return targets[index]
    
    def _generate_cache_key(self, torch: Torch) -> str:
        """Generate cache key for routing decision"""
        content = f"{torch.sender_valley}:{torch.target_address}:{json.dumps(torch.payload, sort_keys=True)}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]
    
    def _get_cached_targets(self, cache_key: str) -> Optional[List[str]]:
        """Get cached routing targets if still valid"""
        if cache_key in self.route_cache:
            targets, timestamp = self.route_cache[cache_key]
            if datetime.utcnow() - timestamp < self.cache_ttl:
                return targets
            else:
                del self.route_cache[cache_key]
        return None
    
    def _cache_targets(self, cache_key: str, targets: List[str]):
        """Cache routing targets"""
        self.route_cache[cache_key] = (targets, datetime.utcnow())
        
        # Clean old cache entries
        current_time = datetime.utcnow()
        expired_keys = [
            key for key, (_, timestamp) in self.route_cache.items()
            if current_time - timestamp > self.cache_ttl
        ]
        for key in expired_keys:
            del self.route_cache[key]
    
    def get_routing_statistics(self) -> Dict[str, Any]:
        """Get routing statistics"""
        return {
            "total_rules": len(self.routing_rules),
            "enabled_rules": len([r for r in self.routing_rules if r.enabled]),
            "cache_size": len(self.route_cache),
            "load_balancer_targets": len(self.load_balancer_state),
            "default_strategy": self.default_strategy.value
        }
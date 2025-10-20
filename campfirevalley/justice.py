"""
Justice System for CampfireValley

This module implements the Justice system responsible for violation detection,
policy enforcement, and corrective actions. The Justice system works with
VALI services to ensure compliance and security across the valley network.
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional, Set, Callable, Union
from datetime import datetime, timedelta
from enum import Enum
from dataclasses import dataclass, field
import json

from .models import (
    Torch, Violation, Action, Decision, SecurityLevel,
    VALIServiceRequest, VALIServiceResponse, ScanResult
)
from .interfaces import IMCPBroker, IJustice
from .vali import VALICoordinator, VALIServiceType


class ViolationType(str, Enum):
    """Types of violations that can be detected"""
    SECURITY_THREAT = "security_threat"
    POLICY_VIOLATION = "policy_violation"
    CONTENT_VIOLATION = "content_violation"
    SIZE_VIOLATION = "size_violation"
    RATE_VIOLATION = "rate_violation"
    AUTHENTICATION_FAILURE = "authentication_failure"
    AUTHORIZATION_FAILURE = "authorization_failure"
    MALWARE_DETECTED = "malware_detected"
    SUSPICIOUS_BEHAVIOR = "suspicious_behavior"
    COMPLIANCE_FAILURE = "compliance_failure"


class ActionType(str, Enum):
    """Types of actions that can be taken"""
    ALLOW = "allow"
    BLOCK = "block"
    QUARANTINE = "quarantine"
    SANITIZE = "sanitize"
    LOG_ONLY = "log_only"
    RATE_LIMIT = "rate_limit"
    REQUIRE_APPROVAL = "require_approval"
    REDIRECT = "redirect"
    TRANSFORM = "transform"
    ESCALATE = "escalate"


class Severity(str, Enum):
    """Severity levels for violations"""
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class PolicyRule:
    """Represents a policy rule for violation detection"""
    id: str
    name: str
    description: str
    violation_type: ViolationType
    severity: Severity
    condition: str  # JSON-serializable condition
    action: ActionType
    metadata: Dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class ViolationEvent:
    """Represents a detected violation event"""
    id: str
    torch_id: str
    sender_valley: str
    violation_type: ViolationType
    severity: Severity
    description: str
    rule_id: str
    evidence: Dict[str, Any]
    timestamp: datetime = field(default_factory=datetime.utcnow)
    resolved: bool = False
    resolution_action: Optional[ActionType] = None
    resolution_timestamp: Optional[datetime] = None


@dataclass
class EnforcementAction:
    """Represents an enforcement action to be taken"""
    id: str
    violation_event_id: str
    action_type: ActionType
    parameters: Dict[str, Any]
    scheduled_time: datetime
    executed: bool = False
    execution_time: Optional[datetime] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class PolicyEngine:
    """Engine for evaluating policy rules against torches"""
    
    def __init__(self):
        self.rules: Dict[str, PolicyRule] = {}
        self.logger = logging.getLogger(f"{__name__}.PolicyEngine")
    
    def add_rule(self, rule: PolicyRule) -> None:
        """Add a policy rule"""
        self.rules[rule.id] = rule
        self.logger.info(f"Added policy rule: {rule.name} ({rule.id})")
    
    def remove_rule(self, rule_id: str) -> None:
        """Remove a policy rule"""
        if rule_id in self.rules:
            rule = self.rules.pop(rule_id)
            self.logger.info(f"Removed policy rule: {rule.name} ({rule_id})")
    
    def update_rule(self, rule: PolicyRule) -> None:
        """Update an existing policy rule"""
        rule.updated_at = datetime.utcnow()
        self.rules[rule.id] = rule
        self.logger.info(f"Updated policy rule: {rule.name} ({rule.id})")
    
    def get_rule(self, rule_id: str) -> Optional[PolicyRule]:
        """Get a policy rule by ID"""
        return self.rules.get(rule_id)
    
    def list_rules(self, enabled_only: bool = True) -> List[PolicyRule]:
        """List all policy rules"""
        rules = list(self.rules.values())
        if enabled_only:
            rules = [rule for rule in rules if rule.enabled]
        return rules
    
    async def evaluate_torch(self, torch: Torch, scan_results: Optional[List[ScanResult]] = None) -> List[ViolationEvent]:
        """Evaluate a torch against all policy rules"""
        violations = []
        
        for rule in self.list_rules():
            try:
                if await self._evaluate_rule(torch, rule, scan_results):
                    violation = ViolationEvent(
                        id=f"violation_{torch.id}_{rule.id}_{int(datetime.utcnow().timestamp())}",
                        torch_id=torch.id,
                        sender_valley=torch.sender_valley,
                        violation_type=rule.violation_type,
                        severity=rule.severity,
                        description=f"Rule '{rule.name}' violated: {rule.description}",
                        rule_id=rule.id,
                        evidence=await self._collect_evidence(torch, rule, scan_results)
                    )
                    violations.append(violation)
                    
            except Exception as e:
                self.logger.error(f"Error evaluating rule {rule.id}: {e}")
        
        return violations
    
    async def _evaluate_rule(self, torch: Torch, rule: PolicyRule, scan_results: Optional[List[ScanResult]]) -> bool:
        """Evaluate a single rule against a torch"""
        try:
            condition = json.loads(rule.condition)
            return await self._evaluate_condition(torch, condition, scan_results)
        except Exception as e:
            self.logger.error(f"Error evaluating condition for rule {rule.id}: {e}")
            return False
    
    async def _evaluate_condition(self, torch: Torch, condition: Dict[str, Any], scan_results: Optional[List[ScanResult]]) -> bool:
        """Evaluate a condition against a torch"""
        condition_type = condition.get("type")
        
        if condition_type == "payload_size":
            max_size = condition.get("max_size", 0)
            payload_size = len(json.dumps(torch.payload))
            return payload_size > max_size
        
        elif condition_type == "attachment_count":
            max_count = condition.get("max_count", 0)
            return len(torch.attachments) > max_count
        
        elif condition_type == "security_scan_failed":
            if scan_results:
                return any(not result.is_safe for result in scan_results)
            return False
        
        elif condition_type == "sender_blacklist":
            blacklist = condition.get("blacklist", [])
            return torch.sender_valley in blacklist
        
        elif condition_type == "payload_contains":
            patterns = condition.get("patterns", [])
            payload_str = json.dumps(torch.payload).lower()
            return any(pattern.lower() in payload_str for pattern in patterns)
        
        elif condition_type == "time_window":
            start_hour = condition.get("start_hour", 0)
            end_hour = condition.get("end_hour", 24)
            current_hour = datetime.utcnow().hour
            if start_hour <= end_hour:
                return not (start_hour <= current_hour <= end_hour)
            else:  # Overnight window
                return not (current_hour >= start_hour or current_hour <= end_hour)
        
        elif condition_type == "and":
            sub_conditions = condition.get("conditions", [])
            return all(await self._evaluate_condition(torch, cond, scan_results) for cond in sub_conditions)
        
        elif condition_type == "or":
            sub_conditions = condition.get("conditions", [])
            return any(await self._evaluate_condition(torch, cond, scan_results) for cond in sub_conditions)
        
        elif condition_type == "not":
            sub_condition = condition.get("condition", {})
            return not await self._evaluate_condition(torch, sub_condition, scan_results)
        
        return False
    
    async def _collect_evidence(self, torch: Torch, rule: PolicyRule, scan_results: Optional[List[ScanResult]]) -> Dict[str, Any]:
        """Collect evidence for a violation"""
        evidence = {
            "torch_id": torch.id,
            "sender_valley": torch.sender_valley,
            "payload_size": len(json.dumps(torch.payload)),
            "attachment_count": len(torch.attachments),
            "timestamp": torch.timestamp.isoformat(),
            "rule_condition": rule.condition
        }
        
        if scan_results:
            evidence["scan_results"] = [
                {
                    "is_safe": result.is_safe,
                    "violations": result.violations,
                    "confidence_score": result.confidence_score
                }
                for result in scan_results
            ]
        
        return evidence


class EnforcementEngine:
    """Engine for executing enforcement actions"""
    
    def __init__(self, mcp_broker: IMCPBroker):
        self.mcp_broker = mcp_broker
        self.pending_actions: Dict[str, EnforcementAction] = {}
        self.action_handlers: Dict[ActionType, Callable] = {}
        self.logger = logging.getLogger(f"{__name__}.EnforcementEngine")
        self._setup_default_handlers()
    
    def _setup_default_handlers(self):
        """Setup default action handlers"""
        self.action_handlers = {
            ActionType.ALLOW: self._handle_allow,
            ActionType.BLOCK: self._handle_block,
            ActionType.QUARANTINE: self._handle_quarantine,
            ActionType.SANITIZE: self._handle_sanitize,
            ActionType.LOG_ONLY: self._handle_log_only,
            ActionType.RATE_LIMIT: self._handle_rate_limit,
            ActionType.REQUIRE_APPROVAL: self._handle_require_approval,
            ActionType.REDIRECT: self._handle_redirect,
            ActionType.TRANSFORM: self._handle_transform,
            ActionType.ESCALATE: self._handle_escalate
        }
    
    def register_action_handler(self, action_type: ActionType, handler: Callable):
        """Register a custom action handler"""
        self.action_handlers[action_type] = handler
        self.logger.info(f"Registered custom handler for action type: {action_type}")
    
    async def schedule_action(self, action: EnforcementAction) -> None:
        """Schedule an enforcement action"""
        self.pending_actions[action.id] = action
        self.logger.info(f"Scheduled enforcement action: {action.action_type} for violation {action.violation_event_id}")
    
    async def execute_action(self, action_id: str) -> bool:
        """Execute a scheduled enforcement action"""
        if action_id not in self.pending_actions:
            self.logger.error(f"Action {action_id} not found")
            return False
        
        action = self.pending_actions[action_id]
        
        if action.executed:
            self.logger.warning(f"Action {action_id} already executed")
            return True
        
        try:
            handler = self.action_handlers.get(action.action_type)
            if not handler:
                raise ValueError(f"No handler for action type: {action.action_type}")
            
            result = await handler(action)
            
            action.executed = True
            action.execution_time = datetime.utcnow()
            action.result = result
            
            self.logger.info(f"Successfully executed action {action_id}")
            return True
            
        except Exception as e:
            action.error = str(e)
            self.logger.error(f"Failed to execute action {action_id}: {e}")
            return False
    
    async def _handle_allow(self, action: EnforcementAction) -> Dict[str, Any]:
        """Handle allow action"""
        return {"action": "allow", "message": "Torch allowed to proceed"}
    
    async def _handle_block(self, action: EnforcementAction) -> Dict[str, Any]:
        """Handle block action"""
        reason = action.parameters.get("reason", "Policy violation")
        return {"action": "block", "reason": reason}
    
    async def _handle_quarantine(self, action: EnforcementAction) -> Dict[str, Any]:
        """Handle quarantine action"""
        duration = action.parameters.get("duration_hours", 24)
        return {"action": "quarantine", "duration_hours": duration}
    
    async def _handle_sanitize(self, action: EnforcementAction) -> Dict[str, Any]:
        """Handle sanitize action"""
        sanitization_rules = action.parameters.get("rules", [])
        return {"action": "sanitize", "rules_applied": sanitization_rules}
    
    async def _handle_log_only(self, action: EnforcementAction) -> Dict[str, Any]:
        """Handle log only action"""
        self.logger.warning(f"Policy violation logged: {action.violation_event_id}")
        return {"action": "log_only", "logged": True}
    
    async def _handle_rate_limit(self, action: EnforcementAction) -> Dict[str, Any]:
        """Handle rate limit action"""
        limit = action.parameters.get("requests_per_minute", 10)
        return {"action": "rate_limit", "limit": limit}
    
    async def _handle_require_approval(self, action: EnforcementAction) -> Dict[str, Any]:
        """Handle require approval action"""
        approver = action.parameters.get("approver", "admin")
        return {"action": "require_approval", "approver": approver}
    
    async def _handle_redirect(self, action: EnforcementAction) -> Dict[str, Any]:
        """Handle redirect action"""
        target = action.parameters.get("target_address", "quarantine")
        return {"action": "redirect", "target": target}
    
    async def _handle_transform(self, action: EnforcementAction) -> Dict[str, Any]:
        """Handle transform action"""
        transformation = action.parameters.get("transformation", "sanitize")
        return {"action": "transform", "transformation": transformation}
    
    async def _handle_escalate(self, action: EnforcementAction) -> Dict[str, Any]:
        """Handle escalate action"""
        escalation_target = action.parameters.get("target", "security_team")
        return {"action": "escalate", "target": escalation_target}


class JusticeSystem(IJustice):
    """
    Main Justice system coordinating violation detection and enforcement
    """
    
    def __init__(self, mcp_broker: IMCPBroker, vali_coordinator: VALICoordinator):
        self.mcp_broker = mcp_broker
        self.vali_coordinator = vali_coordinator
        self.policy_engine = PolicyEngine()
        self.enforcement_engine = EnforcementEngine(mcp_broker)
        
        self.violation_history: Dict[str, ViolationEvent] = {}
        self.enforcement_history: Dict[str, EnforcementAction] = {}
        
        self.logger = logging.getLogger(f"{__name__}.JusticeSystem")
        self._load_default_policies()
    
    def _load_default_policies(self):
        """Load default security policies"""
        default_rules = [
            PolicyRule(
                id="max_payload_size",
                name="Maximum Payload Size",
                description="Payload size exceeds maximum allowed limit",
                violation_type=ViolationType.SIZE_VIOLATION,
                severity=Severity.MEDIUM,
                condition=json.dumps({"type": "payload_size", "max_size": 10 * 1024 * 1024}),  # 10MB
                action=ActionType.BLOCK
            ),
            PolicyRule(
                id="max_attachments",
                name="Maximum Attachments",
                description="Too many attachments in torch",
                violation_type=ViolationType.POLICY_VIOLATION,
                severity=Severity.LOW,
                condition=json.dumps({"type": "attachment_count", "max_count": 50}),
                action=ActionType.LOG_ONLY
            ),
            PolicyRule(
                id="security_scan_failure",
                name="Security Scan Failure",
                description="Torch failed security scanning",
                violation_type=ViolationType.SECURITY_THREAT,
                severity=Severity.HIGH,
                condition=json.dumps({"type": "security_scan_failed"}),
                action=ActionType.QUARANTINE
            ),
            PolicyRule(
                id="suspicious_content",
                name="Suspicious Content",
                description="Torch contains suspicious patterns",
                violation_type=ViolationType.CONTENT_VIOLATION,
                severity=Severity.MEDIUM,
                condition=json.dumps({
                    "type": "payload_contains",
                    "patterns": ["<script>", "eval(", "exec(", "system("]
                }),
                action=ActionType.SANITIZE
            ),
            PolicyRule(
                id="business_hours_only",
                name="Business Hours Only",
                description="Torch received outside business hours",
                violation_type=ViolationType.POLICY_VIOLATION,
                severity=Severity.LOW,
                condition=json.dumps({"type": "time_window", "start_hour": 9, "end_hour": 17}),
                action=ActionType.REQUIRE_APPROVAL
            )
        ]
        
        for rule in default_rules:
            self.policy_engine.add_rule(rule)
    
    async def evaluate_torch(self, torch: Torch) -> Decision:
        """Evaluate a torch and make a decision"""
        try:
            # First, run VALI scans
            scan_results = await self._run_vali_scans(torch)
            
            # Evaluate against policies
            violations = await self.policy_engine.evaluate_torch(torch, scan_results)
            
            # Store violations
            for violation in violations:
                self.violation_history[violation.id] = violation
            
            # Determine action based on violations
            decision = await self._make_decision(torch, violations, scan_results)
            
            # Schedule enforcement actions
            if decision.action != ActionType.ALLOW:
                await self._schedule_enforcement(decision, violations)
            
            return decision
            
        except Exception as e:
            self.logger.error(f"Error evaluating torch {torch.id}: {e}")
            # Default to block on error
            return Decision(
                torch_id=torch.id,
                action=ActionType.BLOCK,
                reason=f"Evaluation error: {e}",
                confidence=0.0,
                timestamp=datetime.utcnow()
            )
    
    async def _run_vali_scans(self, torch: Torch) -> List[ScanResult]:
        """Run VALI security scans on torch"""
        scan_results = []
        
        try:
            # Security scan
            security_response = await self.vali_coordinator.request_service(
                VALIServiceType.SECURITY_SCAN,
                {
                    "torch_id": torch.id,
                    "sender_valley": torch.sender_valley,
                    "target_address": torch.target_address,
                    "payload": torch.payload,
                    "attachments": torch.attachments,
                    "signature": torch.signature
                },
                {"security_level": SecurityLevel.STANDARD.value}
            )
            
            if security_response.status == "completed":
                scan_result_data = security_response.deliverables.get("scan_result", {})
                scan_result = ScanResult(
                    is_safe=scan_result_data.get("is_safe", False),
                    violations=scan_result_data.get("violations", []),
                    confidence_score=scan_result_data.get("confidence_score", 0.0),
                    scan_timestamp=datetime.utcnow()
                )
                scan_results.append(scan_result)
            
        except Exception as e:
            self.logger.error(f"VALI scan failed for torch {torch.id}: {e}")
        
        return scan_results
    
    async def _make_decision(self, torch: Torch, violations: List[ViolationEvent], scan_results: List[ScanResult]) -> Decision:
        """Make a decision based on violations and scan results"""
        if not violations:
            return Decision(
                torch_id=torch.id,
                action=ActionType.ALLOW,
                reason="No violations detected",
                confidence=1.0,
                timestamp=datetime.utcnow()
            )
        
        # Determine the most severe violation
        severity_order = {
            Severity.INFO: 0,
            Severity.LOW: 1,
            Severity.MEDIUM: 2,
            Severity.HIGH: 3,
            Severity.CRITICAL: 4
        }
        
        max_severity = max(violations, key=lambda v: severity_order[v.severity])
        
        # Get the corresponding rule and action
        rule = self.policy_engine.get_rule(max_severity.rule_id)
        action = rule.action if rule else ActionType.BLOCK
        
        # Calculate confidence based on scan results
        confidence = 0.8  # Base confidence
        if scan_results:
            avg_confidence = sum(result.confidence_score for result in scan_results) / len(scan_results)
            confidence = min(confidence + (avg_confidence * 0.2), 1.0)
        
        return Decision(
            torch_id=torch.id,
            action=action,
            reason=f"Violation detected: {max_severity.description}",
            confidence=confidence,
            timestamp=datetime.utcnow(),
            violations=[
                Violation(
                    type=v.violation_type.value,
                    description=v.description,
                    severity=v.severity.value
                ) for v in violations
            ]
        )
    
    async def _schedule_enforcement(self, decision: Decision, violations: List[ViolationEvent]) -> None:
        """Schedule enforcement actions based on decision"""
        for violation in violations:
            action = EnforcementAction(
                id=f"action_{violation.id}_{int(datetime.utcnow().timestamp())}",
                violation_event_id=violation.id,
                action_type=decision.action,
                parameters={"reason": decision.reason},
                scheduled_time=datetime.utcnow()
            )
            
            await self.enforcement_engine.schedule_action(action)
            self.enforcement_history[action.id] = action
    
    def add_policy_rule(self, rule: PolicyRule) -> None:
        """Add a custom policy rule"""
        self.policy_engine.add_rule(rule)
    
    def remove_policy_rule(self, rule_id: str) -> None:
        """Remove a policy rule"""
        self.policy_engine.remove_rule(rule_id)
    
    def get_violation_history(self, torch_id: Optional[str] = None) -> List[ViolationEvent]:
        """Get violation history"""
        violations = list(self.violation_history.values())
        if torch_id:
            violations = [v for v in violations if v.torch_id == torch_id]
        return sorted(violations, key=lambda v: v.timestamp, reverse=True)
    
    def get_enforcement_history(self, violation_id: Optional[str] = None) -> List[EnforcementAction]:
        """Get enforcement history"""
        actions = list(self.enforcement_history.values())
        if violation_id:
            actions = [a for a in actions if a.violation_event_id == violation_id]
        return sorted(actions, key=lambda a: a.scheduled_time, reverse=True)
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get justice system statistics"""
        violations = list(self.violation_history.values())
        actions = list(self.enforcement_history.values())
        
        return {
            "total_violations": len(violations),
            "violations_by_type": {
                vtype.value: len([v for v in violations if v.violation_type == vtype])
                for vtype in ViolationType
            },
            "violations_by_severity": {
                severity.value: len([v for v in violations if v.severity == severity])
                for severity in Severity
            },
            "total_actions": len(actions),
            "actions_by_type": {
                atype.value: len([a for a in actions if a.action_type == atype])
                for atype in ActionType
            },
            "executed_actions": len([a for a in actions if a.executed]),
            "failed_actions": len([a for a in actions if a.error is not None])
        }
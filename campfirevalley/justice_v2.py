"""
Simplified justice system used by the test suite.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional

from .models import Torch


class ViolationType(Enum):
    RATE_LIMIT = "rate_limit"
    CONTENT_VIOLATION = "content_violation"
    SECURITY_THREAT = "security_threat"


class ActionType(Enum):
    ALLOW = "allow"
    BLOCK = "block"
    THROTTLE = "throttle"
    QUARANTINE = "quarantine"


class Severity(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class PolicyRule:
    id: str
    name: str
    violation_type: ViolationType
    conditions: Dict[str, Any] = field(default_factory=dict)
    action: ActionType = ActionType.ALLOW
    severity: Severity = Severity.LOW
    enabled: bool = True
    description: Optional[str] = None


@dataclass
class ViolationEvent:
    id: str
    violation_type: ViolationType
    severity: Severity
    source: str
    target: str
    description: str
    timestamp: datetime
    policy_id: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EnforcementAction:
    id: str
    action_type: ActionType
    target_id: str
    reason: str
    severity: Severity
    timestamp: datetime
    parameters: Dict[str, Any] = field(default_factory=dict)
    expires_at: Optional[datetime] = None


class PolicyEngine:
    def __init__(self):
        self.policies: Dict[str, PolicyRule] = {}
        self._request_times: Dict[str, List[float]] = {}

    def add_policy(self, rule: PolicyRule) -> None:
        self.policies[rule.id] = rule

    def remove_policy(self, rule_id: str) -> None:
        self.policies.pop(rule_id, None)

    def get_policy(self, rule_id: str) -> Optional[PolicyRule]:
        return self.policies.get(rule_id)

    def _check_rate_limit(self, sender_id: str, max_requests: int, time_window: int) -> bool:
        now = time.time()
        times = self._request_times.get(sender_id, [])
        cutoff = now - float(time_window)
        times = [t for t in times if t >= cutoff]
        times.append(now)
        self._request_times[sender_id] = times
        return len(times) > int(max_requests)

    async def evaluate_torch(self, torch: Torch, sender_id: str) -> List[ViolationEvent]:
        violations: List[ViolationEvent] = []
        payload = {}
        if isinstance(torch.data, dict):
            payload = torch.data
        message = str(payload.get("message") or payload.get("text") or "")

        for rule in list(self.policies.values()):
            if not rule.enabled:
                continue
            if rule.violation_type == ViolationType.RATE_LIMIT:
                max_req = int(rule.conditions.get("max_requests", 10))
                window = int(rule.conditions.get("time_window", 60))
                if self._check_rate_limit(sender_id, max_req, window):
                    violations.append(
                        ViolationEvent(
                            id=f"viol_{int(time.time()*1000)}",
                            violation_type=ViolationType.RATE_LIMIT,
                            severity=rule.severity,
                            source=sender_id,
                            target=torch.torch_id,
                            description="Rate limit exceeded",
                            timestamp=datetime.utcnow(),
                            policy_id=rule.id,
                        )
                    )
            elif rule.violation_type == ViolationType.CONTENT_VIOLATION:
                patterns = rule.conditions.get("blocked_patterns") or []
                hit = any(p.lower() in message.lower() for p in patterns if isinstance(p, str))
                if hit:
                    violations.append(
                        ViolationEvent(
                            id=f"viol_{int(time.time()*1000)}",
                            violation_type=ViolationType.CONTENT_VIOLATION,
                            severity=rule.severity,
                            source=sender_id,
                            target=torch.torch_id,
                            description="Blocked content detected",
                            timestamp=datetime.utcnow(),
                            policy_id=rule.id,
                            metadata={"patterns": patterns},
                        )
                    )
        return violations


class EnforcementEngine:
    def __init__(self):
        self.vali_services: Any = None
        self.active_actions: Dict[str, EnforcementAction] = {}
        self.throttled_sources: Dict[str, datetime] = {}

    async def execute_action(self, action: EnforcementAction) -> bool:
        self.active_actions[action.id] = action
        if action.action_type == ActionType.QUARANTINE and self.vali_services and hasattr(self.vali_services, "quarantine_torch"):
            try:
                return bool(await self.vali_services.quarantine_torch(action.target_id))
            except Exception:
                return False
        if action.action_type == ActionType.THROTTLE:
            delay = int(action.parameters.get("delay", 5))
            until = datetime.utcnow() + timedelta(seconds=delay)
            self.throttled_sources[action.target_id] = until
            action.expires_at = until
        return True

    def is_throttled(self, source_id: str) -> bool:
        until = self.throttled_sources.get(source_id)
        if not until:
            return False
        if until <= datetime.utcnow():
            self.throttled_sources.pop(source_id, None)
            return False
        return True


class JusticeSystem:
    def __init__(self):
        self.policy_engine: Optional[PolicyEngine] = None
        self.enforcement_engine: Optional[EnforcementEngine] = None
        self.violation_history: List[ViolationEvent] = []

    async def initialize(self):
        if self.policy_engine is None:
            self.policy_engine = PolicyEngine()
        if self.enforcement_engine is None:
            self.enforcement_engine = EnforcementEngine()
        if not self.policy_engine.policies:
            self.policy_engine.add_policy(
                PolicyRule(
                    id="default_rate_limit",
                    name="Default Rate Limit",
                    violation_type=ViolationType.RATE_LIMIT,
                    conditions={"max_requests": 10, "time_window": 60},
                    action=ActionType.THROTTLE,
                    severity=Severity.MEDIUM,
                    enabled=True,
                )
            )
            self.policy_engine.add_policy(
                PolicyRule(
                    id="default_content_filter",
                    name="Default Content Filter",
                    violation_type=ViolationType.CONTENT_VIOLATION,
                    conditions={"blocked_patterns": ["spam", "malware"]},
                    action=ActionType.BLOCK,
                    severity=Severity.HIGH,
                    enabled=True,
                )
            )

    async def evaluate_torch(self, torch: Torch, sender_id: str) -> List[ViolationEvent]:
        if not self.policy_engine:
            await self.initialize()
        violations = await self.policy_engine.evaluate_torch(torch, sender_id)
        self.violation_history.extend(violations)
        if self.enforcement_engine and self.enforcement_engine.is_throttled(sender_id):
            return violations
        for v in violations:
            if self.enforcement_engine and v.violation_type == ViolationType.RATE_LIMIT:
                await self.enforce_policy(v)
        return violations

    async def enforce_policy(self, violation: ViolationEvent) -> bool:
        if not self.policy_engine or not self.enforcement_engine:
            await self.initialize()
        rule = self.policy_engine.get_policy(violation.policy_id) if self.policy_engine else None
        action_type = rule.action if rule else ActionType.BLOCK
        target = violation.target if action_type != ActionType.THROTTLE else violation.source
        params = {}
        if action_type == ActionType.THROTTLE:
            params = {"delay": 5}
        action = EnforcementAction(
            id=f"act_{int(time.time()*1000)}",
            action_type=action_type,
            target_id=target,
            reason=violation.description,
            severity=violation.severity,
            timestamp=datetime.utcnow(),
            parameters=params,
        )
        return bool(await self.enforcement_engine.execute_action(action))

    async def get_violation_history(self, source: Optional[str] = None, violation_type: Optional[ViolationType] = None) -> List[ViolationEvent]:
        items = list(self.violation_history)
        if source:
            items = [v for v in items if v.source == source]
        if violation_type:
            items = [v for v in items if v.violation_type == violation_type]
        return items

    async def get_enforcement_actions(self) -> List[EnforcementAction]:
        if not self.enforcement_engine:
            await self.initialize()
        return list(self.enforcement_engine.active_actions.values())


__all__ = [
    "JusticeSystem",
    "PolicyEngine",
    "EnforcementEngine",
    "PolicyRule",
    "ViolationEvent",
    "EnforcementAction",
    "ViolationType",
    "ActionType",
    "Severity",
]


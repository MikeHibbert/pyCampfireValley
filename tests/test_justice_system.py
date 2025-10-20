"""
Tests for the Justice System components.
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch

from campfirevalley.justice import (
    JusticeSystem, PolicyEngine, EnforcementEngine,
    PolicyRule, ViolationEvent, EnforcementAction,
    ViolationType, ActionType, Severity
)
from campfirevalley.models import Torch


class TestPolicyEngine:
    """Test cases for PolicyEngine"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.policy_engine = PolicyEngine()
        
        # Add test policies
        self.rate_limit_rule = PolicyRule(
            id="rate_limit_test",
            name="Rate Limiting",
            violation_type=ViolationType.RATE_LIMIT,
            conditions={"max_requests": 10, "time_window": 60},
            action=ActionType.THROTTLE,
            severity=Severity.MEDIUM,
            enabled=True
        )
        
        self.content_filter_rule = PolicyRule(
            id="content_filter_test",
            name="Content Filtering",
            violation_type=ViolationType.CONTENT_VIOLATION,
            conditions={"blocked_patterns": ["spam", "malware"]},
            action=ActionType.BLOCK,
            severity=Severity.HIGH,
            enabled=True
        )
        
        self.policy_engine.add_policy(self.rate_limit_rule)
        self.policy_engine.add_policy(self.content_filter_rule)
    
    def test_add_policy(self):
        """Test adding a policy"""
        new_rule = PolicyRule(
            id="test_rule",
            name="Test Rule",
            violation_type=ViolationType.SECURITY_THREAT,
            conditions={},
            action=ActionType.QUARANTINE,
            severity=Severity.CRITICAL
        )
        
        self.policy_engine.add_policy(new_rule)
        assert "test_rule" in self.policy_engine.policies
        assert self.policy_engine.policies["test_rule"] == new_rule
    
    def test_remove_policy(self):
        """Test removing a policy"""
        self.policy_engine.remove_policy("rate_limit_test")
        assert "rate_limit_test" not in self.policy_engine.policies
    
    def test_get_policy(self):
        """Test getting a policy"""
        policy = self.policy_engine.get_policy("rate_limit_test")
        assert policy == self.rate_limit_rule
        
        # Test non-existent policy
        assert self.policy_engine.get_policy("non_existent") is None
    
    @pytest.mark.asyncio
    async def test_evaluate_torch_rate_limit(self):
        """Test rate limit evaluation"""
        # Create test torch
        torch = Torch(
            id="test_torch",
            payload={"message": "test"},
            source="test_source",
            destination="test_dest"
        )
        
        # Mock rate tracking
        with patch.object(self.policy_engine, '_check_rate_limit', return_value=True):
            violations = await self.policy_engine.evaluate_torch(torch, "test_source")
            assert len(violations) == 1
            assert violations[0].violation_type == ViolationType.RATE_LIMIT
    
    @pytest.mark.asyncio
    async def test_evaluate_torch_content_filter(self):
        """Test content filtering evaluation"""
        # Create torch with blocked content
        torch = Torch(
            id="test_torch",
            payload={"message": "This contains spam content"},
            source="test_source",
            destination="test_dest"
        )
        
        violations = await self.policy_engine.evaluate_torch(torch, "test_source")
        assert len(violations) == 1
        assert violations[0].violation_type == ViolationType.CONTENT_VIOLATION
    
    @pytest.mark.asyncio
    async def test_evaluate_torch_no_violations(self):
        """Test evaluation with no violations"""
        torch = Torch(
            id="test_torch",
            payload={"message": "Clean content"},
            source="test_source",
            destination="test_dest"
        )
        
        with patch.object(self.policy_engine, '_check_rate_limit', return_value=False):
            violations = await self.policy_engine.evaluate_torch(torch, "test_source")
            assert len(violations) == 0


class TestEnforcementEngine:
    """Test cases for EnforcementEngine"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.enforcement_engine = EnforcementEngine()
        
        # Mock VALI services
        self.mock_vali = Mock()
        self.enforcement_engine.vali_services = self.mock_vali
    
    @pytest.mark.asyncio
    async def test_execute_action_block(self):
        """Test blocking action execution"""
        action = EnforcementAction(
            id="test_action",
            action_type=ActionType.BLOCK,
            target_id="test_torch",
            reason="Policy violation",
            severity=Severity.HIGH,
            timestamp=datetime.utcnow()
        )
        
        result = await self.enforcement_engine.execute_action(action)
        assert result is True
        assert action.id in self.enforcement_engine.active_actions
    
    @pytest.mark.asyncio
    async def test_execute_action_quarantine(self):
        """Test quarantine action execution"""
        action = EnforcementAction(
            id="test_action",
            action_type=ActionType.QUARANTINE,
            target_id="test_torch",
            reason="Security threat",
            severity=Severity.CRITICAL,
            timestamp=datetime.utcnow()
        )
        
        # Mock quarantine service
        self.mock_vali.quarantine_torch = AsyncMock(return_value=True)
        
        result = await self.enforcement_engine.execute_action(action)
        assert result is True
        self.mock_vali.quarantine_torch.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_execute_action_throttle(self):
        """Test throttle action execution"""
        action = EnforcementAction(
            id="test_action",
            action_type=ActionType.THROTTLE,
            target_id="test_source",
            reason="Rate limit exceeded",
            severity=Severity.MEDIUM,
            timestamp=datetime.utcnow(),
            parameters={"delay": 5}
        )
        
        result = await self.enforcement_engine.execute_action(action)
        assert result is True
        assert "test_source" in self.enforcement_engine.throttled_sources
    
    def test_is_throttled(self):
        """Test throttle checking"""
        source = "test_source"
        
        # Initially not throttled
        assert not self.enforcement_engine.is_throttled(source)
        
        # Add throttle
        self.enforcement_engine.throttled_sources[source] = datetime.utcnow() + timedelta(seconds=10)
        assert self.enforcement_engine.is_throttled(source)
        
        # Expired throttle
        self.enforcement_engine.throttled_sources[source] = datetime.utcnow() - timedelta(seconds=10)
        assert not self.enforcement_engine.is_throttled(source)


class TestJusticeSystem:
    """Test cases for JusticeSystem"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.justice_system = JusticeSystem()
    
    @pytest.mark.asyncio
    async def test_initialize(self):
        """Test justice system initialization"""
        await self.justice_system.initialize()
        
        assert self.justice_system.policy_engine is not None
        assert self.justice_system.enforcement_engine is not None
        assert len(self.justice_system.policy_engine.policies) > 0  # Default policies loaded
    
    @pytest.mark.asyncio
    async def test_evaluate_torch(self):
        """Test torch evaluation"""
        await self.justice_system.initialize()
        
        torch = Torch(
            id="test_torch",
            payload={"message": "test"},
            source="test_source",
            destination="test_dest"
        )
        
        violations = await self.justice_system.evaluate_torch(torch, "test_source")
        assert isinstance(violations, list)
    
    @pytest.mark.asyncio
    async def test_enforce_policy(self):
        """Test policy enforcement"""
        await self.justice_system.initialize()
        
        violation = ViolationEvent(
            id="test_violation",
            violation_type=ViolationType.CONTENT_VIOLATION,
            severity=Severity.HIGH,
            source="test_source",
            target="test_torch",
            description="Test violation",
            timestamp=datetime.utcnow(),
            policy_id="test_policy"
        )
        
        result = await self.justice_system.enforce_policy(violation)
        assert result is True
    
    @pytest.mark.asyncio
    async def test_get_violation_history(self):
        """Test getting violation history"""
        await self.justice_system.initialize()
        
        # Add some test violations
        violation1 = ViolationEvent(
            id="violation1",
            violation_type=ViolationType.RATE_LIMIT,
            severity=Severity.MEDIUM,
            source="source1",
            target="torch1",
            description="Rate limit exceeded",
            timestamp=datetime.utcnow(),
            policy_id="rate_limit_policy"
        )
        
        violation2 = ViolationEvent(
            id="violation2",
            violation_type=ViolationType.CONTENT_VIOLATION,
            severity=Severity.HIGH,
            source="source2",
            target="torch2",
            description="Blocked content",
            timestamp=datetime.utcnow(),
            policy_id="content_policy"
        )
        
        self.justice_system.violation_history.extend([violation1, violation2])
        
        # Test getting all violations
        all_violations = await self.justice_system.get_violation_history()
        assert len(all_violations) == 2
        
        # Test filtering by source
        source1_violations = await self.justice_system.get_violation_history(source="source1")
        assert len(source1_violations) == 1
        assert source1_violations[0].source == "source1"
        
        # Test filtering by violation type
        rate_violations = await self.justice_system.get_violation_history(
            violation_type=ViolationType.RATE_LIMIT
        )
        assert len(rate_violations) == 1
        assert rate_violations[0].violation_type == ViolationType.RATE_LIMIT
    
    @pytest.mark.asyncio
    async def test_get_enforcement_actions(self):
        """Test getting enforcement actions"""
        await self.justice_system.initialize()
        
        # Add test action
        action = EnforcementAction(
            id="test_action",
            action_type=ActionType.BLOCK,
            target_id="test_torch",
            reason="Policy violation",
            severity=Severity.HIGH,
            timestamp=datetime.utcnow()
        )
        
        self.justice_system.enforcement_engine.active_actions["test_action"] = action
        
        actions = await self.justice_system.get_enforcement_actions()
        assert len(actions) == 1
        assert actions[0].id == "test_action"


class TestPolicyRule:
    """Test cases for PolicyRule dataclass"""
    
    def test_policy_rule_creation(self):
        """Test creating a policy rule"""
        rule = PolicyRule(
            id="test_rule",
            name="Test Rule",
            violation_type=ViolationType.SECURITY_THREAT,
            conditions={"threshold": 10},
            action=ActionType.QUARANTINE,
            severity=Severity.CRITICAL,
            enabled=True,
            description="Test policy rule"
        )
        
        assert rule.id == "test_rule"
        assert rule.name == "Test Rule"
        assert rule.violation_type == ViolationType.SECURITY_THREAT
        assert rule.conditions == {"threshold": 10}
        assert rule.action == ActionType.QUARANTINE
        assert rule.severity == Severity.CRITICAL
        assert rule.enabled is True
        assert rule.description == "Test policy rule"


class TestViolationEvent:
    """Test cases for ViolationEvent dataclass"""
    
    def test_violation_event_creation(self):
        """Test creating a violation event"""
        timestamp = datetime.utcnow()
        
        violation = ViolationEvent(
            id="test_violation",
            violation_type=ViolationType.RATE_LIMIT,
            severity=Severity.MEDIUM,
            source="test_source",
            target="test_target",
            description="Rate limit exceeded",
            timestamp=timestamp,
            policy_id="rate_limit_policy",
            metadata={"requests": 100}
        )
        
        assert violation.id == "test_violation"
        assert violation.violation_type == ViolationType.RATE_LIMIT
        assert violation.severity == Severity.MEDIUM
        assert violation.source == "test_source"
        assert violation.target == "test_target"
        assert violation.description == "Rate limit exceeded"
        assert violation.timestamp == timestamp
        assert violation.policy_id == "rate_limit_policy"
        assert violation.metadata == {"requests": 100}


class TestEnforcementAction:
    """Test cases for EnforcementAction dataclass"""
    
    def test_enforcement_action_creation(self):
        """Test creating an enforcement action"""
        timestamp = datetime.utcnow()
        
        action = EnforcementAction(
            id="test_action",
            action_type=ActionType.THROTTLE,
            target_id="test_target",
            reason="Policy violation",
            severity=Severity.HIGH,
            timestamp=timestamp,
            parameters={"delay": 30},
            expires_at=timestamp + timedelta(minutes=5)
        )
        
        assert action.id == "test_action"
        assert action.action_type == ActionType.THROTTLE
        assert action.target_id == "test_target"
        assert action.reason == "Policy violation"
        assert action.severity == Severity.HIGH
        assert action.timestamp == timestamp
        assert action.parameters == {"delay": 30}
        assert action.expires_at == timestamp + timedelta(minutes=5)


# Integration tests
class TestJusticeSystemIntegration:
    """Integration tests for the complete Justice System"""
    
    @pytest.mark.asyncio
    async def test_full_violation_workflow(self):
        """Test complete violation detection and enforcement workflow"""
        justice_system = JusticeSystem()
        await justice_system.initialize()
        
        # Create a torch that should trigger violations
        torch = Torch(
            id="violation_torch",
            payload={"message": "This contains spam and malware"},
            source="suspicious_source",
            destination="test_dest"
        )
        
        # Evaluate torch
        violations = await justice_system.evaluate_torch(torch, "suspicious_source")
        
        # Should detect content violation
        content_violations = [v for v in violations if v.violation_type == ViolationType.CONTENT_VIOLATION]
        assert len(content_violations) > 0
        
        # Enforce policy for the violation
        if content_violations:
            result = await justice_system.enforce_policy(content_violations[0])
            assert result is True
            
            # Check that enforcement action was created
            actions = await justice_system.get_enforcement_actions()
            assert len(actions) > 0
    
    @pytest.mark.asyncio
    async def test_rate_limiting_workflow(self):
        """Test rate limiting detection and enforcement"""
        justice_system = JusticeSystem()
        await justice_system.initialize()
        
        source = "rate_limited_source"
        
        # Simulate multiple requests from same source
        for i in range(15):  # Exceed rate limit
            torch = Torch(
                id=f"torch_{i}",
                payload={"message": f"Message {i}"},
                source=source,
                destination="test_dest"
            )
            
            violations = await justice_system.evaluate_torch(torch, source)
            
            # After exceeding rate limit, should get violations
            if i >= 10:  # Assuming rate limit is 10
                rate_violations = [v for v in violations if v.violation_type == ViolationType.RATE_LIMIT]
                if rate_violations:
                    # Should be throttled
                    assert justice_system.enforcement_engine.is_throttled(source)
                    break


if __name__ == "__main__":
    pytest.main([__file__])
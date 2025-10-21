"""
Justice Campfire - Governance, compliance, and violation management functionality.

The Justice campfire provides three essential campers:
- DetectorCamper: Detects policy violations and compliance issues
- EnforcerCamper: Enforces policies and applies sanctions
- GovernorCamper: Manages governance rules and oversight
"""

import asyncio
import logging
import json
import hashlib
from typing import Optional, Dict, Any, List, Set, Tuple
from datetime import datetime, timedelta
from enum import Enum
from dataclasses import dataclass, field

from ..interfaces import ICampfire, IMCPBroker, IJusticeCampfire
from ..models import Torch, CampfireConfig, SecurityLevel
from ..campfire import Campfire, ICamper
from ..vali import VALICoordinator, VALIServiceType


logger = logging.getLogger(__name__)


class ViolationType(Enum):
    """Types of policy violations"""
    CONTENT_POLICY = "content_policy"
    SECURITY_POLICY = "security_policy"
    COMMUNICATION_POLICY = "communication_policy"
    RESOURCE_POLICY = "resource_policy"
    FEDERATION_POLICY = "federation_policy"
    GOVERNANCE_POLICY = "governance_policy"


class SanctionType(Enum):
    """Types of sanctions that can be applied"""
    WARNING = "warning"
    CONTENT_REMOVAL = "content_removal"
    TEMPORARY_RESTRICTION = "temporary_restriction"
    PERMANENT_BAN = "permanent_ban"
    QUARANTINE = "quarantine"
    RATE_LIMIT = "rate_limit"


@dataclass
class PolicyRule:
    """Defines a governance policy rule"""
    id: str
    name: str
    description: str
    violation_type: ViolationType
    severity: int  # 1-10 scale
    enabled: bool = True
    auto_enforce: bool = False
    sanction: SanctionType = SanctionType.WARNING
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class Violation:
    """Represents a policy violation"""
    id: str
    rule_id: str
    torch_id: str
    sender_valley: str
    violation_type: ViolationType
    severity: int
    description: str
    evidence: Dict[str, Any]
    detected_at: datetime
    status: str = "pending"  # pending, reviewed, sanctioned, dismissed
    reviewer: Optional[str] = None
    sanction_applied: Optional[SanctionType] = None


@dataclass
class Sanction:
    """Represents an applied sanction"""
    id: str
    violation_id: str
    target_valley: str
    sanction_type: SanctionType
    duration: Optional[timedelta] = None
    applied_at: datetime = field(default_factory=datetime.utcnow)
    applied_by: str = "system"
    active: bool = True
    details: Dict[str, Any] = field(default_factory=dict)


class DetectorCamper(ICamper):
    """
    Detector camper handles policy violation detection and compliance monitoring.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the Detector camper.
        
        Args:
            config: Camper configuration from campfire steps
        """
        self.config = config
        self.policy_rules: Dict[str, PolicyRule] = {}
        self.violation_threshold = config.get('violation_threshold', 5)
        self.auto_detection_enabled = config.get('auto_detection_enabled', True)
        self.vali_coordinator = None
        self._running = False
        
        # Load default policy rules
        self._load_default_rules()
        
        logger.debug("DetectorCamper initialized")
    
    async def start(self) -> None:
        """Start the Detector camper"""
        self._running = True
        
        # Initialize VALI coordinator if available
        try:
            self.vali_coordinator = VALICoordinator()
            await self.vali_coordinator.start()
            logger.debug("VALI coordinator started for detector")
        except Exception as e:
            logger.warning(f"Could not start VALI coordinator: {e}")
        
        logger.info("DetectorCamper started")
    
    async def stop(self) -> None:
        """Stop the Detector camper"""
        self._running = False
        
        if self.vali_coordinator:
            await self.vali_coordinator.stop()
        
        logger.info("DetectorCamper stopped")
    
    async def process(self, torch: Torch) -> Dict[str, Any]:
        """
        Detect policy violations in torch content.
        
        Args:
            torch: The torch to analyze
            
        Returns:
            Dict containing violation detection results
        """
        if not self._running:
            raise RuntimeError("DetectorCamper is not running")
        
        logger.debug(f"Analyzing torch {torch.id} for policy violations")
        
        try:
            violations = []
            
            # Check against all enabled policy rules
            for rule in self.policy_rules.values():
                if not rule.enabled:
                    continue
                
                violation = await self._check_rule_violation(torch, rule)
                if violation:
                    violations.append(violation)
            
            # Additional VALI compliance check if available
            vali_result = None
            if self.vali_coordinator:
                try:
                    vali_result = await self.vali_coordinator.validate_content(
                        torch.payload, 
                        VALIServiceType.COMPLIANCE_CHECK
                    )
                    
                    if not vali_result.get('is_compliant', True):
                        # Create VALI-based violation
                        vali_violation = Violation(
                            id=self._generate_violation_id(),
                            rule_id="vali_compliance",
                            torch_id=torch.id,
                            sender_valley=torch.sender_valley,
                            violation_type=ViolationType.GOVERNANCE_POLICY,
                            severity=7,
                            description=f"VALI compliance check failed: {vali_result.get('reason', 'Unknown')}",
                            evidence=vali_result,
                            detected_at=datetime.utcnow()
                        )
                        violations.append(vali_violation)
                        
                except Exception as e:
                    logger.warning(f"VALI compliance check failed: {e}")
            
            result = {
                'torch_id': torch.id,
                'violations_detected': len(violations),
                'violations': [self._violation_to_dict(v) for v in violations],
                'vali_result': vali_result,
                'requires_review': any(v.severity >= self.violation_threshold for v in violations),
                'timestamp': datetime.utcnow().isoformat(),
                'detector': 'DetectorCamper'
            }
            
            if violations:
                logger.warning(f"Detected {len(violations)} violations in torch {torch.id}")
            else:
                logger.debug(f"No violations detected in torch {torch.id}")
            
            return result
            
        except Exception as e:
            logger.error(f"Error detecting violations in torch {torch.id}: {e}")
            return {
                'torch_id': torch.id,
                'error': str(e),
                'timestamp': datetime.utcnow().isoformat(),
                'detector': 'DetectorCamper'
            }
    
    async def _check_rule_violation(self, torch: Torch, rule: PolicyRule) -> Optional[Violation]:
        """Check if a torch violates a specific rule"""
        # This is a simplified implementation - in production, this would be much more sophisticated
        
        if rule.violation_type == ViolationType.CONTENT_POLICY:
            # Check for inappropriate content
            content_str = json.dumps(torch.payload).lower()
            if any(word in content_str for word in ['spam', 'malicious', 'inappropriate']):
                return Violation(
                    id=self._generate_violation_id(),
                    rule_id=rule.id,
                    torch_id=torch.id,
                    sender_valley=torch.sender_valley,
                    violation_type=rule.violation_type,
                    severity=rule.severity,
                    description=f"Content policy violation: {rule.name}",
                    evidence={'rule': rule.name, 'content_sample': content_str[:100]},
                    detected_at=datetime.utcnow()
                )
        
        elif rule.violation_type == ViolationType.COMMUNICATION_POLICY:
            # Check communication patterns
            if len(torch.payload.get('message', '')) > 10000:  # Example: message too long
                return Violation(
                    id=self._generate_violation_id(),
                    rule_id=rule.id,
                    torch_id=torch.id,
                    sender_valley=torch.sender_valley,
                    violation_type=rule.violation_type,
                    severity=rule.severity,
                    description=f"Communication policy violation: Message exceeds length limit",
                    evidence={'message_length': len(torch.payload.get('message', ''))},
                    detected_at=datetime.utcnow()
                )
        
        elif rule.violation_type == ViolationType.FEDERATION_POLICY:
            # Check federation-specific rules
            if torch.sender_valley not in self.config.get('allowed_valleys', []):
                return Violation(
                    id=self._generate_violation_id(),
                    rule_id=rule.id,
                    torch_id=torch.id,
                    sender_valley=torch.sender_valley,
                    violation_type=rule.violation_type,
                    severity=rule.severity,
                    description=f"Federation policy violation: Unauthorized valley communication",
                    evidence={'sender_valley': torch.sender_valley},
                    detected_at=datetime.utcnow()
                )
        
        return None
    
    def _load_default_rules(self) -> None:
        """Load default policy rules"""
        default_rules = [
            PolicyRule(
                id="content_policy_spam",
                name="Anti-Spam Policy",
                description="Detects and prevents spam content",
                violation_type=ViolationType.CONTENT_POLICY,
                severity=6,
                auto_enforce=True,
                sanction=SanctionType.CONTENT_REMOVAL
            ),
            PolicyRule(
                id="security_policy_malicious",
                name="Malicious Content Policy",
                description="Detects malicious or harmful content",
                violation_type=ViolationType.SECURITY_POLICY,
                severity=9,
                auto_enforce=True,
                sanction=SanctionType.QUARANTINE
            ),
            PolicyRule(
                id="communication_policy_length",
                name="Message Length Policy",
                description="Enforces reasonable message length limits",
                violation_type=ViolationType.COMMUNICATION_POLICY,
                severity=3,
                auto_enforce=False,
                sanction=SanctionType.WARNING
            ),
            PolicyRule(
                id="federation_policy_authorization",
                name="Valley Authorization Policy",
                description="Ensures only authorized valleys can communicate",
                violation_type=ViolationType.FEDERATION_POLICY,
                severity=8,
                auto_enforce=True,
                sanction=SanctionType.TEMPORARY_RESTRICTION
            )
        ]
        
        for rule in default_rules:
            self.policy_rules[rule.id] = rule
    
    def _generate_violation_id(self) -> str:
        """Generate unique violation ID"""
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        random_hash = hashlib.sha256(f"{timestamp}_{id(self)}".encode()).hexdigest()[:8]
        return f"violation_{timestamp}_{random_hash}"
    
    def _violation_to_dict(self, violation: Violation) -> Dict[str, Any]:
        """Convert violation to dictionary"""
        return {
            'id': violation.id,
            'rule_id': violation.rule_id,
            'torch_id': violation.torch_id,
            'sender_valley': violation.sender_valley,
            'violation_type': violation.violation_type.value,
            'severity': violation.severity,
            'description': violation.description,
            'evidence': violation.evidence,
            'detected_at': violation.detected_at.isoformat(),
            'status': violation.status
        }
    
    def add_policy_rule(self, rule: PolicyRule) -> None:
        """Add a new policy rule"""
        self.policy_rules[rule.id] = rule
        logger.info(f"Added policy rule: {rule.name}")
    
    def remove_policy_rule(self, rule_id: str) -> bool:
        """Remove a policy rule"""
        if rule_id in self.policy_rules:
            del self.policy_rules[rule_id]
            logger.info(f"Removed policy rule: {rule_id}")
            return True
        return False


class EnforcerCamper(ICamper):
    """
    Enforcer camper handles policy enforcement and sanction application.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the Enforcer camper.
        
        Args:
            config: Camper configuration from campfire steps
        """
        self.config = config
        self.active_sanctions: Dict[str, Sanction] = {}
        self.auto_enforcement_enabled = config.get('auto_enforcement_enabled', True)
        self.max_sanctions_per_valley = config.get('max_sanctions_per_valley', 10)
        self._running = False
        
        logger.debug("EnforcerCamper initialized")
    
    async def start(self) -> None:
        """Start the Enforcer camper"""
        self._running = True
        
        # Start sanction cleanup task
        asyncio.create_task(self._sanction_cleanup_task())
        
        logger.info("EnforcerCamper started")
    
    async def stop(self) -> None:
        """Stop the Enforcer camper"""
        self._running = False
        logger.info("EnforcerCamper stopped")
    
    async def process(self, torch: Torch) -> Dict[str, Any]:
        """
        Process enforcement actions for violations.
        
        Args:
            torch: The torch that triggered violations
            
        Returns:
            Dict containing enforcement results
        """
        if not self._running:
            raise RuntimeError("EnforcerCamper is not running")
        
        logger.debug(f"Processing enforcement for torch {torch.id}")
        
        try:
            # This would typically receive violation data from the detector
            # For now, we'll simulate enforcement processing
            
            sanctions_applied = []
            enforcement_actions = []
            
            # Check if valley has active sanctions
            valley_sanctions = self._get_valley_sanctions(torch.sender_valley)
            
            if valley_sanctions:
                logger.info(f"Valley {torch.sender_valley} has {len(valley_sanctions)} active sanctions")
                
                # Apply rate limiting if applicable
                rate_limit_sanctions = [s for s in valley_sanctions if s.sanction_type == SanctionType.RATE_LIMIT]
                if rate_limit_sanctions:
                    enforcement_actions.append({
                        'action': 'rate_limit_applied',
                        'details': f"Rate limiting active for {torch.sender_valley}"
                    })
            
            result = {
                'torch_id': torch.id,
                'sender_valley': torch.sender_valley,
                'sanctions_applied': sanctions_applied,
                'enforcement_actions': enforcement_actions,
                'active_sanctions': len(valley_sanctions),
                'timestamp': datetime.utcnow().isoformat(),
                'enforcer': 'EnforcerCamper'
            }
            
            logger.debug(f"Enforcement processing completed for torch {torch.id}")
            return result
            
        except Exception as e:
            logger.error(f"Error processing enforcement for torch {torch.id}: {e}")
            return {
                'torch_id': torch.id,
                'error': str(e),
                'timestamp': datetime.utcnow().isoformat(),
                'enforcer': 'EnforcerCamper'
            }
    
    async def apply_sanction(self, violation: Violation, sanction_type: SanctionType, 
                           duration: Optional[timedelta] = None, applied_by: str = "system") -> Sanction:
        """Apply a sanction for a violation"""
        sanction = Sanction(
            id=self._generate_sanction_id(),
            violation_id=violation.id,
            target_valley=violation.sender_valley,
            sanction_type=sanction_type,
            duration=duration,
            applied_by=applied_by,
            details={
                'violation_type': violation.violation_type.value,
                'severity': violation.severity,
                'rule_id': violation.rule_id
            }
        )
        
        self.active_sanctions[sanction.id] = sanction
        
        logger.warning(f"Applied {sanction_type.value} sanction to {violation.sender_valley} "
                      f"for violation {violation.id}")
        
        return sanction
    
    async def revoke_sanction(self, sanction_id: str, revoked_by: str = "system") -> bool:
        """Revoke an active sanction"""
        if sanction_id in self.active_sanctions:
            sanction = self.active_sanctions[sanction_id]
            sanction.active = False
            sanction.details['revoked_at'] = datetime.utcnow().isoformat()
            sanction.details['revoked_by'] = revoked_by
            
            logger.info(f"Revoked sanction {sanction_id} by {revoked_by}")
            return True
        
        return False
    
    def _get_valley_sanctions(self, valley_name: str) -> List[Sanction]:
        """Get active sanctions for a valley"""
        return [s for s in self.active_sanctions.values() 
                if s.target_valley == valley_name and s.active]
    
    def _generate_sanction_id(self) -> str:
        """Generate unique sanction ID"""
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        random_hash = hashlib.sha256(f"{timestamp}_{id(self)}".encode()).hexdigest()[:8]
        return f"sanction_{timestamp}_{random_hash}"
    
    async def _sanction_cleanup_task(self) -> None:
        """Background task to clean up expired sanctions"""
        while self._running:
            try:
                current_time = datetime.utcnow()
                expired_sanctions = []
                
                for sanction_id, sanction in self.active_sanctions.items():
                    if (sanction.duration and 
                        current_time > sanction.applied_at + sanction.duration):
                        expired_sanctions.append(sanction_id)
                
                for sanction_id in expired_sanctions:
                    sanction = self.active_sanctions[sanction_id]
                    sanction.active = False
                    sanction.details['expired_at'] = current_time.isoformat()
                    logger.info(f"Sanction {sanction_id} expired and deactivated")
                
                if expired_sanctions:
                    logger.info(f"Cleaned up {len(expired_sanctions)} expired sanctions")
                
            except Exception as e:
                logger.error(f"Error in sanction cleanup task: {e}")
            
            # Sleep for 5 minutes
            await asyncio.sleep(300)


class GovernorCamper(ICamper):
    """
    Governor camper handles governance oversight and policy management.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the Governor camper.
        
        Args:
            config: Camper configuration from campfire steps
        """
        self.config = config
        self.governance_stats = {
            'violations_detected': 0,
            'sanctions_applied': 0,
            'policies_enforced': 0,
            'reviews_completed': 0
        }
        self.oversight_enabled = config.get('oversight_enabled', True)
        self._running = False
        
        logger.debug("GovernorCamper initialized")
    
    async def start(self) -> None:
        """Start the Governor camper"""
        self._running = True
        
        # Start governance monitoring task
        asyncio.create_task(self._governance_monitoring_task())
        
        logger.info("GovernorCamper started")
    
    async def stop(self) -> None:
        """Stop the Governor camper"""
        self._running = False
        logger.info("GovernorCamper stopped")
    
    async def process(self, torch: Torch) -> Dict[str, Any]:
        """
        Process governance oversight for torch.
        
        Args:
            torch: The torch to oversee
            
        Returns:
            Dict containing governance oversight results
        """
        if not self._running:
            raise RuntimeError("GovernorCamper is not running")
        
        logger.debug(f"Processing governance oversight for torch {torch.id}")
        
        try:
            oversight_actions = []
            
            # Governance oversight logic
            if self.oversight_enabled:
                # Check for governance compliance
                compliance_score = await self._calculate_compliance_score(torch)
                
                if compliance_score < 0.7:  # Below threshold
                    oversight_actions.append({
                        'action': 'compliance_review_required',
                        'score': compliance_score,
                        'reason': 'Below governance compliance threshold'
                    })
                
                # Update stats
                self.governance_stats['policies_enforced'] += 1
            
            result = {
                'torch_id': torch.id,
                'oversight_enabled': self.oversight_enabled,
                'oversight_actions': oversight_actions,
                'governance_stats': self.governance_stats.copy(),
                'timestamp': datetime.utcnow().isoformat(),
                'governor': 'GovernorCamper'
            }
            
            logger.debug(f"Governance oversight completed for torch {torch.id}")
            return result
            
        except Exception as e:
            logger.error(f"Error processing governance oversight for torch {torch.id}: {e}")
            return {
                'torch_id': torch.id,
                'error': str(e),
                'timestamp': datetime.utcnow().isoformat(),
                'governor': 'GovernorCamper'
            }
    
    async def _calculate_compliance_score(self, torch: Torch) -> float:
        """Calculate governance compliance score for a torch"""
        # Simplified compliance scoring
        score = 1.0
        
        # Check various compliance factors
        if not torch.signature:
            score -= 0.2  # Missing signature
        
        if len(torch.payload) == 0:
            score -= 0.3  # Empty payload
        
        if torch.sender_valley == "unknown":
            score -= 0.4  # Unknown sender
        
        return max(0.0, score)
    
    async def get_governance_report(self) -> Dict[str, Any]:
        """Generate governance report"""
        return {
            'stats': self.governance_stats.copy(),
            'oversight_enabled': self.oversight_enabled,
            'report_generated_at': datetime.utcnow().isoformat()
        }
    
    async def _governance_monitoring_task(self) -> None:
        """Background task for governance monitoring"""
        while self._running:
            try:
                # Periodic governance monitoring
                logger.debug("Performing governance monitoring check")
                
                # This would include various governance checks
                # For now, just log the current stats
                logger.info(f"Governance stats: {self.governance_stats}")
                
            except Exception as e:
                logger.error(f"Error in governance monitoring task: {e}")
            
            # Sleep for 10 minutes
            await asyncio.sleep(600)


class JusticeCampfire(Campfire, IJusticeCampfire):
    """
    Justice campfire that orchestrates governance, compliance, and violation management.
    
    This campfire provides comprehensive governance functionality,
    ensuring valleys operate within established policies and regulations.
    """
    
    def __init__(self, mcp_broker: IMCPBroker, config: Optional[CampfireConfig] = None):
        """
        Initialize the Justice campfire.
        
        Args:
            mcp_broker: MCP broker for communication
            config: Optional campfire configuration (will create default if not provided)
        """
        if config is None:
            config = self._create_default_config()
        
        super().__init__(config, mcp_broker)
        
        # Initialize campers
        self.detector = DetectorCamper(self._get_camper_config('detector'))
        self.enforcer = EnforcerCamper(self._get_camper_config('enforcer'))
        self.governor = GovernorCamper(self._get_camper_config('governor'))
        
        self._campers = {
            'detector': self.detector,
            'enforcer': self.enforcer,
            'governor': self.governor
        }
        
        logger.info("JusticeCampfire initialized")
    
    async def start(self) -> None:
        """Start the Justice campfire and all campers"""
        await super().start()
        
        # Start all campers
        for camper_name, camper in self._campers.items():
            await camper.start()
            logger.debug(f"Started {camper_name} camper")
        
        logger.info("JusticeCampfire started with all campers")
    
    async def stop(self) -> None:
        """Stop the Justice campfire and all campers"""
        # Stop all campers
        for camper_name, camper in self._campers.items():
            await camper.stop()
            logger.debug(f"Stopped {camper_name} camper")
        
        await super().stop()
        logger.info("JusticeCampfire stopped")
    
    async def process_torch(self, torch: Torch) -> Optional[Torch]:
        """
        Process torch through justice pipeline.
        
        Args:
            torch: The torch to process
            
        Returns:
            Processed torch or None if blocked
        """
        logger.info(f"Processing torch {torch.id} through justice pipeline")
        
        try:
            # Step 1: Detect violations
            detection_result = await self.detector.process(torch)
            violations = detection_result.get('violations', [])
            
            if violations:
                logger.warning(f"Detected {len(violations)} violations in torch {torch.id}")
                
                # Step 2: Apply enforcement
                enforcement_result = await self.enforcer.process(torch)
                
                # Step 3: Governance oversight
                governance_result = await self.governor.process(torch)
                
                # Determine if torch should be blocked
                high_severity_violations = [v for v in violations if v.get('severity', 0) >= 8]
                if high_severity_violations:
                    logger.warning(f"Torch {torch.id} blocked due to high severity violations")
                    return None
            
            # Step 3: Always run governance oversight
            governance_result = await self.governor.process(torch)
            
            logger.info(f"Torch {torch.id} passed justice pipeline")
            return torch
        
        except Exception as e:
            logger.error(f"Error processing torch {torch.id} through justice pipeline: {e}")
            # Safe default: allow torch but log error
            return torch
    
    # IJusticeCampfire interface implementation
    async def detect_violations(self, content: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Detect policy violations in content"""
        # Create temporary torch for detection
        temp_torch = Torch(
            id="temp_detect",
            sender_valley="system",
            target_address="detector",
            payload=content,
            attachments=[],
            signature="",
            timestamp=datetime.utcnow()
        )
        
        detection_result = await self.detector.process(temp_torch)
        return detection_result.get('violations', [])
    
    async def enforce_policies(self, violations: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Enforce policies based on detected violations"""
        enforcement_results = []
        
        for violation_data in violations:
            # Convert dict back to Violation object for processing
            # This is simplified - in production, you'd have proper serialization
            temp_torch = Torch(
                id="temp_enforce",
                sender_valley=violation_data.get('sender_valley', 'unknown'),
                target_address="enforcer",
                payload={},
                attachments=[],
                signature="",
                timestamp=datetime.utcnow()
            )
            
            enforcement_result = await self.enforcer.process(temp_torch)
            enforcement_results.append(enforcement_result)
        
        return {
            'violations_processed': len(violations),
            'enforcement_results': enforcement_results,
            'timestamp': datetime.utcnow().isoformat()
        }
    
    async def manage_quarantine(self, action: str, item_id: str) -> Dict[str, Any]:
        """Manage quarantined content"""
        # This would integrate with the Sanitizer campfire's quarantine system
        # For now, return a placeholder response
        return {
            'action': action,
            'item_id': item_id,
            'status': 'processed',
            'timestamp': datetime.utcnow().isoformat()
        }
    
    def _create_default_config(self) -> CampfireConfig:
        """Create default configuration for Justice campfire"""
        return CampfireConfig(
            name="justice",
            runs_on="valley",
            env={
                "JUSTICE_MODE": "standard",
                "AUTO_ENFORCEMENT": "true"
            },
            steps=[
                {
                    "name": "Detect policy violations",
                    "uses": "camper/detector@v1",
                    "with": {
                        "violation_threshold": 5,
                        "auto_detection_enabled": True,
                        "allowed_valleys": ["TechValley", "CreativeValley", "BusinessValley"]
                    }
                },
                {
                    "name": "Enforce policies and sanctions",
                    "uses": "camper/enforcer@v1",
                    "with": {
                        "auto_enforcement_enabled": True,
                        "max_sanctions_per_valley": 10
                    }
                },
                {
                    "name": "Governance oversight",
                    "uses": "camper/governor@v1",
                    "with": {
                        "oversight_enabled": True
                    }
                }
            ],
            channels=["governance", "justice-control", "policy-enforcement"],
            auditor_enabled=True
        )
    
    def _get_camper_config(self, camper_name: str) -> Dict[str, Any]:
        """Extract configuration for a specific camper from campfire steps"""
        for step in self.config.steps:
            uses = step.get('uses', '')
            if f'camper/{camper_name}@' in uses:
                return step.get('with', {})
        
        # Return default config if not found
        defaults = {
            'detector': {
                'violation_threshold': 5,
                'auto_detection_enabled': True,
                'allowed_valleys': []
            },
            'enforcer': {
                'auto_enforcement_enabled': True,
                'max_sanctions_per_valley': 10
            },
            'governor': {
                'oversight_enabled': True
            }
        }
        
        return defaults.get(camper_name, {})
    
    def get_campers(self) -> Dict[str, ICamper]:
        """Get all active campers"""
        return self._campers.copy()
    
    async def get_governance_report(self) -> Dict[str, Any]:
        """Get comprehensive governance report"""
        return await self.governor.get_governance_report()
    
    async def add_policy_rule(self, rule: PolicyRule) -> None:
        """Add a new policy rule"""
        self.detector.add_policy_rule(rule)
    
    async def apply_sanction(self, violation_data: Dict[str, Any], sanction_type: SanctionType, 
                           duration: Optional[timedelta] = None) -> Dict[str, Any]:
        """Apply a sanction for a violation"""
        # Convert violation data to Violation object
        violation = Violation(
            id=violation_data.get('id', 'unknown'),
            rule_id=violation_data.get('rule_id', 'unknown'),
            torch_id=violation_data.get('torch_id', 'unknown'),
            sender_valley=violation_data.get('sender_valley', 'unknown'),
            violation_type=ViolationType(violation_data.get('violation_type', 'content_policy')),
            severity=violation_data.get('severity', 5),
            description=violation_data.get('description', ''),
            evidence=violation_data.get('evidence', {}),
            detected_at=datetime.fromisoformat(violation_data.get('detected_at', datetime.utcnow().isoformat()))
        )
        
        sanction = await self.enforcer.apply_sanction(violation, sanction_type, duration)
        
        return {
            'sanction_id': sanction.id,
            'violation_id': sanction.violation_id,
            'target_valley': sanction.target_valley,
            'sanction_type': sanction.sanction_type.value,
            'applied_at': sanction.applied_at.isoformat(),
            'active': sanction.active
        }
    
    def __repr__(self) -> str:
        return f"JusticeCampfire(running={self._running}, campers={len(self._campers)})"
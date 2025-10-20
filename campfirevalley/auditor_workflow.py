"""
Auditor Approval Workflow with Justice System Integration.
Handles code review, approval processes, and quality assurance for development teams.
"""

import asyncio
import logging
from typing import Optional, Dict, Any, List, Set
from enum import Enum
from datetime import datetime, timedelta
from .llm_campfire import LLMCampfire
from .models import Torch, CampfireConfig
from .interfaces import IMCPBroker
from .justice import JusticeSystem, PolicyRule, ViolationType, ActionType, Severity
from .monitoring import get_monitoring_system, LogLevel
from .developer_campfires import DeveloperRole, TaskStatus, TaskComplexity


logger = logging.getLogger(__name__)


class ApprovalStatus(str, Enum):
    """Approval status types"""
    PENDING = "pending"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    CONDITIONAL_APPROVAL = "conditional_approval"
    ESCALATED = "escalated"


class ReviewType(str, Enum):
    """Types of reviews"""
    CODE_REVIEW = "code_review"
    ARCHITECTURE_REVIEW = "architecture_review"
    SECURITY_REVIEW = "security_review"
    PERFORMANCE_REVIEW = "performance_review"
    COMPLIANCE_REVIEW = "compliance_review"


class AuditorLevel(str, Enum):
    """Auditor experience levels"""
    JUNIOR = "junior"
    SENIOR = "senior"
    LEAD = "lead"
    PRINCIPAL = "principal"


class ReviewCriteria:
    """Review criteria for different types of reviews"""
    
    CODE_REVIEW_CRITERIA = [
        "Code quality and readability",
        "Adherence to coding standards",
        "Error handling and edge cases",
        "Test coverage and quality",
        "Documentation completeness",
        "Performance considerations",
        "Security best practices"
    ]
    
    ARCHITECTURE_REVIEW_CRITERIA = [
        "System design and architecture",
        "Scalability considerations",
        "Integration patterns",
        "Data flow and storage",
        "Technology choices",
        "Maintainability",
        "Future extensibility"
    ]
    
    SECURITY_REVIEW_CRITERIA = [
        "Authentication and authorization",
        "Data encryption and protection",
        "Input validation and sanitization",
        "Vulnerability assessment",
        "Compliance with security policies",
        "Access control mechanisms",
        "Audit trail and logging"
    ]


class AuditorCampfire(LLMCampfire):
    """
    Auditor campfire that handles approval workflows and quality assurance.
    """
    
    def __init__(self, config: CampfireConfig, mcp_broker: IMCPBroker, 
                 llm_config, auditor_level: AuditorLevel = AuditorLevel.SENIOR):
        """
        Initialize an auditor campfire.
        
        Args:
            config: Campfire configuration
            mcp_broker: MCP broker for communication
            llm_config: LLM configuration
            auditor_level: Experience level of the auditor
        """
        super().__init__(config, mcp_broker, llm_config)
        self.auditor_level = auditor_level
        self.monitoring = get_monitoring_system()
        self.justice_system = JusticeSystem()
        
        # Review tracking
        self.pending_reviews: Dict[str, Dict[str, Any]] = {}
        self.completed_reviews: List[Dict[str, Any]] = []
        self.review_queue: List[str] = []
        
        # Approval thresholds based on auditor level
        self.approval_thresholds = self._get_approval_thresholds()
        
        # Initialize justice system policies for auditing
        self._setup_audit_policies()
        
        logger.info(f"Auditor Campfire '{config.name}' initialized with level: {auditor_level}")
    
    def _get_approval_thresholds(self) -> Dict[str, Any]:
        """Get approval thresholds based on auditor level"""
        thresholds = {
            AuditorLevel.JUNIOR: {
                "max_complexity": TaskComplexity.MODERATE,
                "max_concurrent_reviews": 3,
                "escalation_threshold": 0.7,
                "auto_approve_threshold": 0.9
            },
            AuditorLevel.SENIOR: {
                "max_complexity": TaskComplexity.COMPLEX,
                "max_concurrent_reviews": 5,
                "escalation_threshold": 0.6,
                "auto_approve_threshold": 0.85
            },
            AuditorLevel.LEAD: {
                "max_complexity": TaskComplexity.EXPERT,
                "max_concurrent_reviews": 8,
                "escalation_threshold": 0.5,
                "auto_approve_threshold": 0.8
            },
            AuditorLevel.PRINCIPAL: {
                "max_complexity": TaskComplexity.EXPERT,
                "max_concurrent_reviews": 10,
                "escalation_threshold": 0.4,
                "auto_approve_threshold": 0.75
            }
        }
        
        return thresholds.get(self.auditor_level, thresholds[AuditorLevel.SENIOR])
    
    def _setup_audit_policies(self):
        """Setup justice system policies for auditing"""
        # Code quality policies
        self.justice_system.add_policy(PolicyRule(
            name="code_quality_standard",
            description="Enforce minimum code quality standards",
            violation_type=ViolationType.QUALITY_VIOLATION,
            severity=Severity.MEDIUM,
            action=ActionType.REQUIRE_REVIEW,
            conditions={"code_quality_score": {"min": 0.7}}
        ))
        
        # Security policies
        self.justice_system.add_policy(PolicyRule(
            name="security_review_required",
            description="Require security review for sensitive operations",
            violation_type=ViolationType.SECURITY_VIOLATION,
            severity=Severity.HIGH,
            action=ActionType.BLOCK_ACTION,
            conditions={"contains_security_sensitive": True}
        ))
        
        # Performance policies
        self.justice_system.add_policy(PolicyRule(
            name="performance_standards",
            description="Enforce performance standards",
            violation_type=ViolationType.PERFORMANCE_VIOLATION,
            severity=Severity.MEDIUM,
            action=ActionType.REQUIRE_REVIEW,
            conditions={"performance_score": {"min": 0.6}}
        ))
    
    async def submit_for_review(self, torch: Torch, review_type: ReviewType = ReviewType.CODE_REVIEW) -> str:
        """
        Submit a development task for auditor review.
        
        Args:
            torch: The torch containing the development work
            review_type: Type of review required
            
        Returns:
            Review ID for tracking
        """
        review_id = f"review_{torch.id}_{int(datetime.now().timestamp())}"
        
        # Check if we can accept more reviews
        if len(self.pending_reviews) >= self.approval_thresholds["max_concurrent_reviews"]:
            logger.warning(f"Auditor {self.config.name} at capacity, queueing review {review_id}")
            self.review_queue.append(review_id)
        
        # Create review record
        review_record = {
            "review_id": review_id,
            "torch": torch,
            "review_type": review_type,
            "status": ApprovalStatus.PENDING,
            "submitted_at": datetime.now(),
            "auditor_level": self.auditor_level,
            "criteria": self._get_review_criteria(review_type),
            "developer_role": torch.data.get("developer_analysis", {}).get("role"),
            "complexity": torch.data.get("developer_analysis", {}).get("complexity", "moderate")
        }
        
        self.pending_reviews[review_id] = review_record
        
        # Log submission
        await self.monitoring.record_metric(
            "review_submitted",
            1,
            {
                "review_type": review_type.value,
                "auditor_level": self.auditor_level.value,
                "complexity": review_record["complexity"]
            }
        )
        
        logger.info(f"Review {review_id} submitted for {review_type.value} by {self.auditor_level.value} auditor")
        
        # Start review process asynchronously
        asyncio.create_task(self._process_review(review_id))
        
        return review_id
    
    async def _process_review(self, review_id: str):
        """Process a review using LLM capabilities and justice system"""
        if review_id not in self.pending_reviews:
            logger.error(f"Review {review_id} not found")
            return
        
        review = self.pending_reviews[review_id]
        torch = review["torch"]
        
        try:
            # Update status
            review["status"] = ApprovalStatus.UNDER_REVIEW
            review["review_started_at"] = datetime.now()
            
            # Check justice system policies first
            policy_violations = await self._check_policies(torch)
            
            if policy_violations:
                # Handle policy violations
                await self._handle_policy_violations(review_id, policy_violations)
                return
            
            # Perform LLM-based review
            review_analysis = await self._perform_llm_review(torch, review["review_type"], review["criteria"])
            
            # Calculate review score
            review_score = self._calculate_review_score(review_analysis)
            
            # Make approval decision
            decision = await self._make_approval_decision(review_id, review_analysis, review_score)
            
            # Update review record
            review.update({
                "review_analysis": review_analysis,
                "review_score": review_score,
                "decision": decision,
                "status": decision["status"],
                "completed_at": datetime.now()
            })
            
            # Create response torch
            response_torch = await self._create_review_response(torch, review)
            
            # Send response
            if response_torch:
                await self.send_torch(response_torch)
            
            # Move to completed reviews
            self.completed_reviews.append(self.pending_reviews.pop(review_id))
            
            # Process next review in queue
            if self.review_queue:
                next_review_id = self.review_queue.pop(0)
                if next_review_id in self.pending_reviews:
                    asyncio.create_task(self._process_review(next_review_id))
            
            # Log completion
            await self.monitoring.record_metric(
                "review_completed",
                1,
                {
                    "status": decision["status"].value,
                    "score": review_score,
                    "auditor_level": self.auditor_level.value
                }
            )
            
        except Exception as e:
            logger.error(f"Error processing review {review_id}: {e}")
            review["status"] = ApprovalStatus.ESCALATED
            review["error"] = str(e)
    
    async def _check_policies(self, torch: Torch) -> List[Dict[str, Any]]:
        """Check torch against justice system policies"""
        violations = []
        
        # Extract relevant data for policy checking
        torch_data = torch.data
        developer_analysis = torch_data.get("developer_analysis", {})
        
        # Check each policy
        for policy in self.justice_system.policies:
            violation = await self.justice_system.check_policy_violation(
                policy.name,
                torch_data,
                torch.sender_valley
            )
            
            if violation:
                violations.append({
                    "policy": policy.name,
                    "violation": violation,
                    "severity": policy.severity
                })
        
        return violations
    
    async def _handle_policy_violations(self, review_id: str, violations: List[Dict[str, Any]]):
        """Handle policy violations found during review"""
        review = self.pending_reviews[review_id]
        
        # Determine severity of violations
        max_severity = max(v["violation"].severity for v in violations)
        
        if max_severity == Severity.HIGH:
            review["status"] = ApprovalStatus.REJECTED
            review["rejection_reason"] = "High severity policy violations detected"
        elif max_severity == Severity.MEDIUM:
            review["status"] = ApprovalStatus.CONDITIONAL_APPROVAL
            review["conditions"] = [f"Address {v['policy']} violation" for v in violations]
        else:
            # Low severity - continue with review but note violations
            review["policy_warnings"] = violations
            return  # Continue with normal review process
        
        review["policy_violations"] = violations
        review["completed_at"] = datetime.now()
        
        # Log policy violation
        await self.monitoring.record_metric(
            "policy_violation_detected",
            len(violations),
            {"max_severity": max_severity.value}
        )
    
    async def _perform_llm_review(self, torch: Torch, review_type: ReviewType, criteria: List[str]) -> Dict[str, Any]:
        """Perform LLM-based review analysis"""
        
        # Prepare review prompt
        prompt = self._create_review_prompt(torch, review_type, criteria)
        
        # Create temporary torch for LLM processing
        temp_torch = Torch(
            sender_valley="auditor",
            target_address="auditor:llm",
            signature="review",
            data={"prompt": prompt, "original_torch": torch.data}
        )
        
        # Process with LLM
        response = await self.process_torch_with_llm(temp_torch, prompt)
        
        if response and response.data.get('llm_response'):
            try:
                # Try to parse structured response
                import json
                analysis = json.loads(response.data['llm_response'])
            except:
                # Fallback to text analysis
                analysis = {
                    "overall_assessment": response.data['llm_response'],
                    "criteria_scores": {},
                    "recommendations": [],
                    "issues_found": []
                }
        else:
            analysis = {
                "overall_assessment": "Review failed - LLM processing error",
                "criteria_scores": {},
                "recommendations": ["Retry review process"],
                "issues_found": ["LLM processing failure"]
            }
        
        return analysis
    
    def _create_review_prompt(self, torch: Torch, review_type: ReviewType, criteria: List[str]) -> str:
        """Create a detailed review prompt for the LLM"""
        
        torch_data = torch.data
        developer_analysis = torch_data.get("developer_analysis", {})
        
        prompt = f"""
As a {self.auditor_level.value} level auditor, perform a comprehensive {review_type.value} of the following development work.

DEVELOPMENT TASK DETAILS:
{self._format_torch_data(torch_data)}

DEVELOPER ANALYSIS:
Role: {developer_analysis.get('role', 'Unknown')}
Complexity: {developer_analysis.get('complexity', 'Unknown')}
Approach: {developer_analysis.get('suggested_approach', 'Not provided')}
Risks: {developer_analysis.get('identified_risks', [])}

REVIEW CRITERIA:
{chr(10).join(f"- {criterion}" for criterion in criteria)}

Please provide a detailed review in JSON format with the following structure:
{{
    "overall_assessment": "Detailed overall assessment of the work",
    "criteria_scores": {{
        "criterion_name": {{"score": 0.0-1.0, "comments": "specific feedback"}},
        ...
    }},
    "issues_found": ["List of specific issues that need attention"],
    "recommendations": ["List of specific recommendations for improvement"],
    "approval_recommendation": "approve|conditional_approve|reject",
    "confidence_level": 0.0-1.0,
    "estimated_fix_effort": "time estimate if issues found"
}}

Focus on:
1. Code quality and maintainability
2. Security considerations
3. Performance implications
4. Adherence to best practices
5. Completeness of implementation
6. Test coverage and quality
7. Documentation adequacy

Be thorough but constructive in your feedback.
"""
        
        return prompt
    
    def _format_torch_data(self, torch_data: Dict[str, Any]) -> str:
        """Format torch data for review prompt"""
        formatted = []
        
        # Key fields to include in review
        key_fields = [
            "task_description", "requirements", "implementation", 
            "code_changes", "test_results", "documentation"
        ]
        
        for field in key_fields:
            if field in torch_data:
                value = torch_data[field]
                if isinstance(value, (dict, list)):
                    formatted.append(f"{field.upper()}: {str(value)[:500]}...")
                else:
                    formatted.append(f"{field.upper()}: {value}")
        
        # Include any other relevant data
        for key, value in torch_data.items():
            if key not in key_fields and not key.startswith("_"):
                if isinstance(value, (dict, list)):
                    formatted.append(f"{key.upper()}: {str(value)[:200]}...")
                else:
                    formatted.append(f"{key.upper()}: {value}")
        
        return "\n".join(formatted)
    
    def _get_review_criteria(self, review_type: ReviewType) -> List[str]:
        """Get criteria for specific review type"""
        criteria_map = {
            ReviewType.CODE_REVIEW: ReviewCriteria.CODE_REVIEW_CRITERIA,
            ReviewType.ARCHITECTURE_REVIEW: ReviewCriteria.ARCHITECTURE_REVIEW_CRITERIA,
            ReviewType.SECURITY_REVIEW: ReviewCriteria.SECURITY_REVIEW_CRITERIA,
            ReviewType.PERFORMANCE_REVIEW: ReviewCriteria.CODE_REVIEW_CRITERIA,  # Reuse for now
            ReviewType.COMPLIANCE_REVIEW: ReviewCriteria.CODE_REVIEW_CRITERIA   # Reuse for now
        }
        
        return criteria_map.get(review_type, ReviewCriteria.CODE_REVIEW_CRITERIA)
    
    def _calculate_review_score(self, analysis: Dict[str, Any]) -> float:
        """Calculate overall review score from analysis"""
        criteria_scores = analysis.get("criteria_scores", {})
        
        if not criteria_scores:
            # Fallback scoring based on approval recommendation
            recommendation = analysis.get("approval_recommendation", "conditional_approve")
            score_map = {
                "approve": 0.85,
                "conditional_approve": 0.65,
                "reject": 0.35
            }
            return score_map.get(recommendation, 0.5)
        
        # Calculate weighted average of criteria scores
        total_score = 0
        count = 0
        
        for criterion, details in criteria_scores.items():
            if isinstance(details, dict) and "score" in details:
                total_score += details["score"]
                count += 1
        
        return total_score / count if count > 0 else 0.5
    
    async def _make_approval_decision(self, review_id: str, analysis: Dict[str, Any], score: float) -> Dict[str, Any]:
        """Make approval decision based on analysis and score"""
        review = self.pending_reviews[review_id]
        thresholds = self.approval_thresholds
        
        # Check for auto-approval
        if score >= thresholds["auto_approve_threshold"]:
            status = ApprovalStatus.APPROVED
            reason = "Meets all quality standards for automatic approval"
        
        # Check for escalation
        elif score <= thresholds["escalation_threshold"]:
            status = ApprovalStatus.ESCALATED
            reason = f"Score {score:.2f} below escalation threshold {thresholds['escalation_threshold']}"
        
        # Check complexity limits
        elif review["complexity"] == TaskComplexity.EXPERT and self.auditor_level in [AuditorLevel.JUNIOR, AuditorLevel.SENIOR]:
            status = ApprovalStatus.ESCALATED
            reason = f"Expert level complexity requires {AuditorLevel.LEAD.value} or higher auditor"
        
        # Conditional approval
        elif score >= 0.6:
            status = ApprovalStatus.CONDITIONAL_APPROVAL
            reason = "Acceptable with conditions"
        
        # Rejection
        else:
            status = ApprovalStatus.REJECTED
            reason = f"Score {score:.2f} below minimum standards"
        
        return {
            "status": status,
            "reason": reason,
            "score": score,
            "auditor_level": self.auditor_level,
            "decision_timestamp": datetime.now()
        }
    
    async def _create_review_response(self, original_torch: Torch, review: Dict[str, Any]) -> Optional[Torch]:
        """Create response torch with review results"""
        
        response_data = {
            "review_id": review["review_id"],
            "original_torch_id": original_torch.id,
            "review_type": review["review_type"].value,
            "status": review["status"].value,
            "auditor_level": self.auditor_level.value,
            "review_score": review.get("review_score", 0),
            "decision": review.get("decision", {}),
            "analysis": review.get("review_analysis", {}),
            "policy_violations": review.get("policy_violations", []),
            "conditions": review.get("conditions", []),
            "timestamp": datetime.now().isoformat()
        }
        
        # Add specific feedback based on status
        if review["status"] == ApprovalStatus.APPROVED:
            response_data["message"] = "Work approved - meets all quality standards"
        elif review["status"] == ApprovalStatus.CONDITIONAL_APPROVAL:
            response_data["message"] = "Conditional approval - address listed conditions"
        elif review["status"] == ApprovalStatus.REJECTED:
            response_data["message"] = "Work rejected - significant issues require resolution"
        elif review["status"] == ApprovalStatus.ESCALATED:
            response_data["message"] = "Review escalated to higher level auditor"
        
        # Create response torch
        response_torch = Torch(
            sender_valley=self.config.name,
            target_address=original_torch.sender_valley,
            signature="audit_response",
            data=response_data
        )
        
        return response_torch
    
    async def get_review_status(self, review_id: str) -> Optional[Dict[str, Any]]:
        """Get status of a specific review"""
        if review_id in self.pending_reviews:
            return self.pending_reviews[review_id]
        
        # Check completed reviews
        for review in self.completed_reviews:
            if review["review_id"] == review_id:
                return review
        
        return None
    
    def get_auditor_metrics(self) -> Dict[str, Any]:
        """Get performance metrics for this auditor"""
        total_reviews = len(self.completed_reviews)
        
        if total_reviews == 0:
            return {
                "auditor_level": self.auditor_level.value,
                "total_reviews": 0,
                "pending_reviews": len(self.pending_reviews),
                "queue_length": len(self.review_queue)
            }
        
        # Calculate metrics
        approved = sum(1 for r in self.completed_reviews if r["status"] == ApprovalStatus.APPROVED)
        rejected = sum(1 for r in self.completed_reviews if r["status"] == ApprovalStatus.REJECTED)
        conditional = sum(1 for r in self.completed_reviews if r["status"] == ApprovalStatus.CONDITIONAL_APPROVAL)
        escalated = sum(1 for r in self.completed_reviews if r["status"] == ApprovalStatus.ESCALATED)
        
        avg_score = sum(r.get("review_score", 0) for r in self.completed_reviews) / total_reviews
        
        return {
            "auditor_level": self.auditor_level.value,
            "total_reviews": total_reviews,
            "pending_reviews": len(self.pending_reviews),
            "queue_length": len(self.review_queue),
            "approval_rate": approved / total_reviews,
            "rejection_rate": rejected / total_reviews,
            "conditional_rate": conditional / total_reviews,
            "escalation_rate": escalated / total_reviews,
            "average_score": avg_score,
            "capacity_utilization": len(self.pending_reviews) / self.approval_thresholds["max_concurrent_reviews"]
        }


# Factory functions for creating auditors
def create_auditor(config: CampfireConfig, mcp_broker: IMCPBroker, llm_config, 
                  level: AuditorLevel = AuditorLevel.SENIOR) -> AuditorCampfire:
    """Create an auditor campfire with specified level"""
    return AuditorCampfire(config, mcp_broker, llm_config, level)


def create_audit_team(valley_name: str, mcp_broker: IMCPBroker, llm_config) -> Dict[str, AuditorCampfire]:
    """
    Create a complete audit team with different levels.
    
    Args:
        valley_name: Name of the valley
        mcp_broker: MCP broker for communication
        llm_config: LLM configuration
        
    Returns:
        Dictionary of auditor campfires by level
    """
    team = {}
    
    levels = [
        (AuditorLevel.SENIOR, "senior-auditor"),
        (AuditorLevel.LEAD, "lead-auditor"),
        (AuditorLevel.PRINCIPAL, "principal-auditor")
    ]
    
    for level, name in levels:
        config = CampfireConfig(
            name=f"{valley_name}-{name}",
            channels=["auditor-review", "escalation", "compliance"]
        )
        
        team[level.value] = AuditorCampfire(config, mcp_broker, llm_config, level)
    
    return team
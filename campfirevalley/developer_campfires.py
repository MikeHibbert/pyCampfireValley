"""
Specialized Developer Campfires using pyCampfires LLM capabilities.
These campfires represent different development team roles with specialized AI assistance.
"""

import asyncio
import logging
from typing import Optional, Dict, Any, List
from enum import Enum
from .llm_campfire import LLMCampfire, create_openrouter_campfire
from .models import Torch, CampfireConfig
from .interfaces import IMCPBroker
from .justice import JusticeSystem, PolicyRule, ViolationType, ActionType, Severity
from .monitoring import get_monitoring_system, LogLevel


logger = logging.getLogger(__name__)


class DeveloperRole(str, Enum):
    """Developer role types"""
    BACKEND = "backend"
    FRONTEND = "frontend"
    TESTING = "testing"
    DEVOPS = "devops"
    ARCHITECT = "architect"
    SECURITY = "security"


class TaskComplexity(str, Enum):
    """Task complexity levels"""
    SIMPLE = "simple"
    MODERATE = "moderate"
    COMPLEX = "complex"
    EXPERT = "expert"


class TaskStatus(str, Enum):
    """Task status tracking"""
    RECEIVED = "received"
    ANALYZING = "analyzing"
    IN_PROGRESS = "in_progress"
    REVIEW_READY = "review_ready"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    REJECTED = "rejected"


class DeveloperCampfire(LLMCampfire):
    """
    Base class for specialized developer campfires with LLM capabilities.
    """
    
    def __init__(self, config: CampfireConfig, mcp_broker: IMCPBroker, 
                 llm_config, role: DeveloperRole):
        """
        Initialize a developer campfire.
        
        Args:
            config: Campfire configuration
            mcp_broker: MCP broker for communication
            llm_config: LLM configuration (OpenRouter or Ollama)
            role: Developer role specialization
        """
        super().__init__(config, mcp_broker, llm_config)
        self.role = role
        self.monitoring = get_monitoring_system()
        self.active_tasks: Dict[str, Dict[str, Any]] = {}
        self.completed_tasks: List[Dict[str, Any]] = []
        
        # Role-specific prompts and capabilities
        self.role_prompts = self._get_role_prompts()
        self.expertise_areas = self._get_expertise_areas()
        
        logger.info(f"Developer Campfire '{config.name}' initialized for role: {role}")
    
    def _get_role_prompts(self) -> Dict[str, str]:
        """Get role-specific prompts for different tasks"""
        base_prompts = {
            "analyze_task": f"As a {self.role.value} developer, analyze this task and provide your assessment.",
            "estimate_effort": f"As a {self.role.value} developer, estimate the effort required for this task.",
            "suggest_approach": f"As a {self.role.value} developer, suggest the best approach for this task.",
            "review_code": f"As a {self.role.value} developer, review this code and provide feedback.",
            "identify_risks": f"As a {self.role.value} developer, identify potential risks in this approach."
        }
        
        # Role-specific customizations
        role_specific = {
            DeveloperRole.BACKEND: {
                "analyze_task": "As a backend developer, analyze this task focusing on API design, database schema, performance, and scalability considerations.",
                "suggest_approach": "As a backend developer, suggest the best technical approach considering architecture patterns, data flow, and system integration."
            },
            DeveloperRole.FRONTEND: {
                "analyze_task": "As a frontend developer, analyze this task focusing on user experience, component design, accessibility, and performance.",
                "suggest_approach": "As a frontend developer, suggest the best approach considering UI/UX patterns, responsive design, and user interaction flows."
            },
            DeveloperRole.TESTING: {
                "analyze_task": "As a testing specialist, analyze this task focusing on test coverage, quality assurance, and validation strategies.",
                "suggest_approach": "As a testing specialist, suggest comprehensive testing approaches including unit, integration, and end-to-end testing strategies."
            },
            DeveloperRole.DEVOPS: {
                "analyze_task": "As a DevOps engineer, analyze this task focusing on deployment, infrastructure, monitoring, and operational concerns.",
                "suggest_approach": "As a DevOps engineer, suggest the best approach for deployment, CI/CD, infrastructure as code, and operational monitoring."
            }
        }
        
        if self.role in role_specific:
            base_prompts.update(role_specific[self.role])
        
        return base_prompts
    
    def _get_expertise_areas(self) -> List[str]:
        """Get expertise areas for this developer role"""
        expertise_map = {
            DeveloperRole.BACKEND: [
                "API Design", "Database Design", "System Architecture", "Performance Optimization",
                "Security Implementation", "Microservices", "Data Processing", "Server Management"
            ],
            DeveloperRole.FRONTEND: [
                "UI/UX Design", "Component Architecture", "Responsive Design", "Accessibility",
                "Performance Optimization", "State Management", "User Experience", "Cross-browser Compatibility"
            ],
            DeveloperRole.TESTING: [
                "Test Strategy", "Quality Assurance", "Test Automation", "Performance Testing",
                "Security Testing", "Regression Testing", "Test Coverage Analysis", "Bug Tracking"
            ],
            DeveloperRole.DEVOPS: [
                "CI/CD Pipelines", "Infrastructure as Code", "Container Orchestration", "Monitoring",
                "Deployment Strategies", "Cloud Platforms", "Security Operations", "Performance Monitoring"
            ]
        }
        
        return expertise_map.get(self.role, [])
    
    async def process_development_task(self, torch: Torch) -> Optional[Torch]:
        """
        Process a development task using role-specific LLM capabilities.
        
        Args:
            torch: The torch containing the development task
            
        Returns:
            Processed torch with development analysis and recommendations
        """
        task_id = torch.id
        task_data = torch.data
        
        try:
            # Update task status
            self.active_tasks[task_id] = {
                "torch": torch,
                "status": TaskStatus.ANALYZING,
                "started_at": torch.timestamp,
                "role": self.role
            }
            
            # Analyze the task
            analysis = await self._analyze_task(task_data)
            
            # Estimate effort and complexity
            effort_estimate = await self._estimate_effort(task_data, analysis)
            
            # Suggest approach
            approach = await self._suggest_approach(task_data, analysis)
            
            # Identify risks
            risks = await self._identify_risks(task_data, analysis, approach)
            
            # Update torch with analysis results
            torch.data.update({
                "developer_analysis": {
                    "role": self.role.value,
                    "expertise_areas": self.expertise_areas,
                    "analysis": analysis,
                    "effort_estimate": effort_estimate,
                    "suggested_approach": approach,
                    "identified_risks": risks,
                    "complexity": self._determine_complexity(effort_estimate),
                    "status": TaskStatus.REVIEW_READY.value
                }
            })
            
            # Update task status
            self.active_tasks[task_id]["status"] = TaskStatus.REVIEW_READY
            
            # Log metrics
            await self.monitoring.record_metric(
                "developer_task_analyzed",
                1,
                {"role": self.role.value, "complexity": torch.data["developer_analysis"]["complexity"]}
            )
            
            logger.info(f"Task {task_id} analyzed by {self.role.value} developer")
            return torch
            
        except Exception as e:
            logger.error(f"Error processing development task {task_id}: {e}")
            
            # Update task status to blocked
            if task_id in self.active_tasks:
                self.active_tasks[task_id]["status"] = TaskStatus.BLOCKED
                self.active_tasks[task_id]["error"] = str(e)
            
            return None
    
    async def _analyze_task(self, task_data: Dict[str, Any]) -> str:
        """Analyze the task using LLM"""
        prompt = f"""
{self.role_prompts['analyze_task']}

Task Details:
{self._format_task_data(task_data)}

Please provide a detailed analysis including:
1. Understanding of requirements
2. Technical considerations
3. Dependencies and prerequisites
4. Potential challenges
5. Success criteria
"""
        
        response = await self.process_torch_with_llm(
            torch=None,  # Create a temporary torch for LLM processing
            prompt=prompt
        )
        
        return response.data.get('llm_response', 'Analysis failed') if response else 'Analysis failed'
    
    async def _estimate_effort(self, task_data: Dict[str, Any], analysis: str) -> Dict[str, Any]:
        """Estimate effort required for the task"""
        prompt = f"""
{self.role_prompts['estimate_effort']}

Task Details:
{self._format_task_data(task_data)}

Previous Analysis:
{analysis}

Please provide effort estimation including:
1. Time estimate (hours/days)
2. Complexity level (simple/moderate/complex/expert)
3. Required skills and expertise
4. Resource requirements
5. Confidence level in estimate

Format as JSON with keys: time_estimate, complexity, required_skills, resources, confidence
"""
        
        # Create temporary torch for LLM processing
        temp_torch = Torch(
            sender_valley="system",
            target_address="system:llm",
            signature="temp",
            data={"prompt": prompt}
        )
        
        response = await self.process_torch_with_llm(temp_torch, prompt)
        
        if response and response.data.get('llm_response'):
            try:
                # Try to parse JSON response
                import json
                return json.loads(response.data['llm_response'])
            except:
                # Fallback to text response
                return {"estimate": response.data['llm_response']}
        
        return {"estimate": "Estimation failed"}
    
    async def _suggest_approach(self, task_data: Dict[str, Any], analysis: str) -> str:
        """Suggest technical approach for the task"""
        prompt = f"""
{self.role_prompts['suggest_approach']}

Task Details:
{self._format_task_data(task_data)}

Analysis:
{analysis}

Please suggest a detailed technical approach including:
1. Step-by-step implementation plan
2. Technology choices and rationale
3. Architecture considerations
4. Best practices to follow
5. Quality assurance measures
"""
        
        temp_torch = Torch(
            sender_valley="system",
            target_address="system:llm",
            signature="temp",
            data={"prompt": prompt}
        )
        
        response = await self.process_torch_with_llm(temp_torch, prompt)
        return response.data.get('llm_response', 'Approach suggestion failed') if response else 'Approach suggestion failed'
    
    async def _identify_risks(self, task_data: Dict[str, Any], analysis: str, approach: str) -> List[str]:
        """Identify potential risks in the task"""
        prompt = f"""
{self.role_prompts['identify_risks']}

Task Details:
{self._format_task_data(task_data)}

Analysis:
{analysis}

Suggested Approach:
{approach}

Please identify potential risks including:
1. Technical risks
2. Timeline risks
3. Resource risks
4. Quality risks
5. Integration risks

Provide as a list of specific, actionable risk items.
"""
        
        temp_torch = Torch(
            sender_valley="system",
            target_address="system:llm",
            signature="temp",
            data={"prompt": prompt}
        )
        
        response = await self.process_torch_with_llm(temp_torch, prompt)
        
        if response and response.data.get('llm_response'):
            # Try to extract list from response
            risks_text = response.data['llm_response']
            # Simple parsing - split by lines and clean up
            risks = [line.strip('- ').strip() for line in risks_text.split('\n') 
                    if line.strip() and not line.strip().startswith('#')]
            return risks[:10]  # Limit to top 10 risks
        
        return ["Risk identification failed"]
    
    def _format_task_data(self, task_data: Dict[str, Any]) -> str:
        """Format task data for LLM prompt"""
        formatted = []
        for key, value in task_data.items():
            if isinstance(value, (dict, list)):
                formatted.append(f"{key}: {str(value)[:200]}...")
            else:
                formatted.append(f"{key}: {value}")
        return "\n".join(formatted)
    
    def _determine_complexity(self, effort_estimate: Dict[str, Any]) -> str:
        """Determine task complexity from effort estimate"""
        if isinstance(effort_estimate, dict):
            complexity = effort_estimate.get('complexity', 'moderate')
            if complexity.lower() in ['simple', 'moderate', 'complex', 'expert']:
                return complexity.lower()
        
        # Fallback logic based on time estimate
        time_str = str(effort_estimate.get('time_estimate', ''))
        if 'hour' in time_str.lower():
            return 'simple'
        elif 'day' in time_str.lower():
            if any(num in time_str for num in ['1', '2', '3']):
                return 'moderate'
            else:
                return 'complex'
        
        return 'moderate'
    
    async def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get status of a specific task"""
        return self.active_tasks.get(task_id)
    
    async def complete_task(self, task_id: str, deliverables: Dict[str, Any]) -> bool:
        """Mark a task as completed with deliverables"""
        if task_id in self.active_tasks:
            task = self.active_tasks.pop(task_id)
            task["status"] = TaskStatus.COMPLETED
            task["deliverables"] = deliverables
            task["completed_at"] = asyncio.get_event_loop().time()
            
            self.completed_tasks.append(task)
            
            # Log completion metric
            await self.monitoring.record_metric(
                "developer_task_completed",
                1,
                {"role": self.role.value}
            )
            
            logger.info(f"Task {task_id} completed by {self.role.value} developer")
            return True
        
        return False
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """Get performance metrics for this developer"""
        total_tasks = len(self.completed_tasks) + len(self.active_tasks)
        completed_count = len(self.completed_tasks)
        
        return {
            "role": self.role.value,
            "total_tasks": total_tasks,
            "completed_tasks": completed_count,
            "active_tasks": len(self.active_tasks),
            "completion_rate": completed_count / total_tasks if total_tasks > 0 else 0,
            "expertise_areas": self.expertise_areas,
            "average_complexity": self._calculate_average_complexity()
        }
    
    def _calculate_average_complexity(self) -> str:
        """Calculate average complexity of completed tasks"""
        if not self.completed_tasks:
            return "unknown"
        
        complexity_scores = {
            "simple": 1,
            "moderate": 2,
            "complex": 3,
            "expert": 4
        }
        
        total_score = 0
        count = 0
        
        for task in self.completed_tasks:
            torch = task.get("torch")
            if torch and torch.data.get("developer_analysis"):
                complexity = torch.data["developer_analysis"].get("complexity", "moderate")
                total_score += complexity_scores.get(complexity, 2)
                count += 1
        
        if count == 0:
            return "unknown"
        
        avg_score = total_score / count
        
        # Convert back to complexity level
        if avg_score <= 1.5:
            return "simple"
        elif avg_score <= 2.5:
            return "moderate"
        elif avg_score <= 3.5:
            return "complex"
        else:
            return "expert"


# Factory functions for creating specialized developer campfires
def create_backend_developer(config: CampfireConfig, mcp_broker: IMCPBroker, llm_config) -> DeveloperCampfire:
    """Create a backend developer campfire"""
    return DeveloperCampfire(config, mcp_broker, llm_config, DeveloperRole.BACKEND)


def create_frontend_developer(config: CampfireConfig, mcp_broker: IMCPBroker, llm_config) -> DeveloperCampfire:
    """Create a frontend developer campfire"""
    return DeveloperCampfire(config, mcp_broker, llm_config, DeveloperRole.FRONTEND)


def create_testing_specialist(config: CampfireConfig, mcp_broker: IMCPBroker, llm_config) -> DeveloperCampfire:
    """Create a testing specialist campfire"""
    return DeveloperCampfire(config, mcp_broker, llm_config, DeveloperRole.TESTING)


def create_devops_engineer(config: CampfireConfig, mcp_broker: IMCPBroker, llm_config) -> DeveloperCampfire:
    """Create a DevOps engineer campfire"""
    return DeveloperCampfire(config, mcp_broker, llm_config, DeveloperRole.DEVOPS)


def create_development_team(valley_name: str, mcp_broker: IMCPBroker, llm_config) -> Dict[str, DeveloperCampfire]:
    """
    Create a complete development team with all specialized roles.
    
    Args:
        valley_name: Name of the valley
        mcp_broker: MCP broker for communication
        llm_config: LLM configuration to use for all developers
        
    Returns:
        Dictionary of developer campfires by role
    """
    team = {}
    
    roles = [
        (DeveloperRole.BACKEND, "backend-dev"),
        (DeveloperRole.FRONTEND, "frontend-dev"),
        (DeveloperRole.TESTING, "testing-specialist"),
        (DeveloperRole.DEVOPS, "devops-engineer")
    ]
    
    for role, name in roles:
        config = CampfireConfig(
            name=f"{valley_name}-{name}",
            channels=[f"dev-{role.value}", "dev-team", "auditor-review"]
        )
        
        team[role.value] = DeveloperCampfire(config, mcp_broker, llm_config, role)
    
    return team
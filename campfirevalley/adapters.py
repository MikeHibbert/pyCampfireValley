from typing import Any, Dict, Optional
from campfires.core.security_hooks import SecurityHooks, SecurityHookResult
from campfires.core.routing_strategy import RoutingStrategy, TargetDecision
from campfires.core.torch import Torch as BaseTorch


class ValleySecurityHooks(SecurityHooks):
    async def pre_receive_torch(self, torch: BaseTorch, context: Dict[str, Any]) -> SecurityHookResult:
        return SecurityHookResult(action="allow", torch=torch)

    async def pre_send_torch(self, torch: BaseTorch, context: Dict[str, Any]) -> SecurityHookResult:
        return SecurityHookResult(action="allow", torch=torch)


class ValleyRoutingStrategy(RoutingStrategy):
    async def choose_target(self, torch: BaseTorch, session: Optional[Dict[str, Any]] = None) -> Optional[TargetDecision]:
        return None

    async def update_health(self, target: str, status: str) -> None:
        return None

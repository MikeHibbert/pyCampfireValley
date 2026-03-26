from typing import Any, Dict, Optional

try:
    from campfires.core.security_hooks import SecurityHooks, SecurityHookResult
except Exception:
    class SecurityHooks:
        pass

    class SecurityHookResult:
        def __init__(self, action: str, torch: Any):
            self.action = action
            self.torch = torch

try:
    from campfires.core.routing_strategy import RoutingStrategy, TargetDecision
except Exception:
    class RoutingStrategy:
        pass

    class TargetDecision:
        def __init__(self, target: str, confidence: float = 1.0):
            self.target = target
            self.confidence = confidence

try:
    from campfires.core.torch import Torch as BaseTorch
except Exception:
    from campfires import Torch as BaseTorch


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

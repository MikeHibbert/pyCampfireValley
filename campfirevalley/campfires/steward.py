"""
Timberwolf Steward Campfire — the caretaker campfire for a valley.

The Timberwolf drives action on the ground: it watches the valley's health,
keeps the grounds tidy, reports to the queen bee (the Golden Eagle's valley)
over the authenticated federation channel, and heals what it can heal. The
Golden Eagle sees everything from above and classifies; the Timberwolf acts
on what can be acted on — a predator pair, not a duplicate.

Four camper capabilities (user direction, Sep 4, m1554/m4012 — "the full system"):
- MonitorCamper: health & job monitoring (HealthChecker foundation)
- HousekeeperCamper: housekeeping (prune stale artifacts, rotate, clean)
- ReportCamper: report to the queen bee via Pip (authenticated federation torch)
- SelfHealCamper: self-healing (retry failed jobs, restart stuck ceremonies)

Division line (binding): the steward is deterministic care. It holds NO
persona, NO lessons, NO introspection, NO self-editing surface. It records
facts and performs mechanical recovery; interpretation stays with Andrew
and the human.
"""

import asyncio
import logging
from typing import Optional, Dict, Any, List, Callable
from datetime import datetime, timezone

from ..interfaces import ICampfire, IMCPBroker
from ..models import Torch, CampfireConfig
from ..campfire import Campfire, ICamper

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class MonitorCamper(ICamper):
    """
    Health and job monitoring.

    Registers named health checks (sync or async callables returning
    (healthy: bool, detail: str)) and sweeps them on demand. Facts only —
    an unhealthy check is a fact to report and act on, never an
    interpretation of the valley's worth.
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self._checks: Dict[str, Callable] = {}
        self._running = False
        self.last_sweep: Optional[Dict[str, Any]] = None
        logger.debug("MonitorCamper initialized")

    def add_health_check(self, name: str, check_func: Callable) -> None:
        """Register a health check. check_func() -> (healthy, detail)."""
        self._checks[name] = check_func

    async def start(self) -> None:
        self._running = True
        logger.info("MonitorCamper started")

    async def stop(self) -> None:
        self._running = False
        logger.info("MonitorCamper stopped")

    async def process(self, data: Any = None) -> Dict[str, Any]:
        """Run every registered health check; record facts."""
        if not self._running:
            raise RuntimeError("MonitorCamper is not running")

        results: Dict[str, Dict[str, Any]] = {}
        healthy = 0
        for name, fn in self._checks.items():
            try:
                out = fn()
                if asyncio.iscoroutine(out):
                    out = await out
                if isinstance(out, tuple) and len(out) == 2:
                    ok, detail = bool(out[0]), str(out[1])
                else:
                    ok, detail = bool(out), ""
            except Exception as e:  # noqa: BLE001
                ok, detail = False, f"check raised: {type(e).__name__}: {e}"
            results[name] = {"healthy": ok, "detail": detail, "checked_at": _now_iso()}
            if ok:
                healthy += 1

        self.last_sweep = {
            "swept_at": _now_iso(),
            "total": len(self._checks),
            "healthy": healthy,
            "unhealthy": len(self._checks) - healthy,
            "checks": results,
        }
        return dict(self.last_sweep)


class HousekeeperCamper(ICamper):
    """
    Housekeeping: prune stale artifacts, rotate logs, clean old attachments.

    Each task is a named callable returning a small fact dict
    (e.g. {"pruned": 12}). The camper never deletes anything it was not
    explicitly given a task for — predictability over cleverness.
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self._tasks: Dict[str, Callable] = {}
        self._running = False
        logger.debug("HousekeeperCamper initialized")

    def add_task(self, name: str, task_func: Callable) -> None:
        """Register a housekeeping task. task_func() -> dict of facts."""
        self._tasks[name] = task_func

    async def start(self) -> None:
        self._running = True
        logger.info("HousekeeperCamper started")

    async def stop(self) -> None:
        self._running = False
        logger.info("HousekeeperCamper stopped")

    async def process(self, data: Any = None) -> Dict[str, Any]:
        """Run every registered housekeeping task; collect facts."""
        if not self._running:
            raise RuntimeError("HousekeeperCamper is not running")

        results: Dict[str, Dict[str, Any]] = {}
        for name, fn in self._tasks.items():
            try:
                out = fn()
                if asyncio.iscoroutine(out):
                    out = await out
                results[name] = out if isinstance(out, dict) else {"result": out}
            except Exception as e:  # noqa: BLE001
                results[name] = {"error": f"{type(e).__name__}: {e}"}

        return {"swept_at": _now_iso(), "tasks": results}


class ReportCamper(ICamper):
    """
    Report to the queen bee via Pip — an authenticated federation torch.

    Builds a status report from the facts other campers produced (monitor
    sweep, housekeeping results, self-heal actions) and hands it to a
    caller-supplied send function (the valley's federation transport).
    The channel is authenticated by the federation layer, not by this
    camper — the steward never handles credentials itself.
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.send_fn: Optional[Callable] = config.get("send_fn")
        self.target_valley: str = config.get("target_valley", "")
        self._running = False
        self.last_report: Optional[Dict[str, Any]] = None
        logger.debug("ReportCamper initialized (target=%s)", self.target_valley)

    async def start(self) -> None:
        self._running = True
        logger.info("ReportCamper started")

    async def stop(self) -> None:
        self._running = False
        logger.info("ReportCamper stopped")

    async def process(self, data: Any = None) -> Dict[str, Any]:
        """
        Compose the status report from ``data`` (a dict of camper facts)
        and dispatch it through send_fn if one is wired.
        """
        if not self._running:
            raise RuntimeError("ReportCamper is not running")

        facts = data if isinstance(data, dict) else {}
        report = {
            "type": "steward_status_report",
            "valley": self.config.get("valley_name", ""),
            "steward": "timberwolf",
            "sent_at": _now_iso(),
            "facts": facts,
        }
        self.last_report = report

        dispatched = False
        detail = "no send channel wired; report recorded locally"
        if self.send_fn is not None and self.target_valley:
            try:
                await self.send_fn(self.target_valley, report)
                dispatched = True
                detail = f"report sent to {self.target_valley}"
            except Exception as e:  # noqa: BLE001
                detail = f"send failed: {type(e).__name__}: {e}"

        return {"reported_at": report["sent_at"], "dispatched": dispatched, "detail": detail}


class SelfHealCamper(ICamper):
    """
    Self-healing: mechanical recovery for known failure shapes.

    Each remedy is a named callable returning a fact dict
    (e.g. {"retried": 2, "recovered": 1}). Remedies are registered by the
    valley — the camper decides nothing, it only applies what it was
    given and records what happened. Deterministic care, no improvisation.
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self._remedies: Dict[str, Callable] = {}
        self._running = False
        self.actions: List[Dict[str, Any]] = []
        logger.debug("SelfHealCamper initialized")

    def add_remedy(self, name: str, remedy_func: Callable) -> None:
        """Register a remedy. remedy_func() -> dict of action facts."""
        self._remedies[name] = remedy_func

    async def start(self) -> None:
        self._running = True
        logger.info("SelfHealCamper started")

    async def stop(self) -> None:
        self._running = False
        logger.info("SelfHealCamper stopped")

    async def process(self, data: Any = None) -> Dict[str, Any]:
        """
        Apply remedies. If ``data`` names specific remedies, only those run;
        otherwise every registered remedy is applied once and the action log
        records the outcome.
        """
        if not self._running:
            raise RuntimeError("SelfHealCamper is not running")

        only = None
        if isinstance(data, dict) and data.get("remedies"):
            only = list(data["remedies"])

        results: Dict[str, Dict[str, Any]] = {}
        for name, fn in self._remedies.items():
            if only is not None and name not in only:
                continue
            try:
                out = fn()
                if asyncio.iscoroutine(out):
                    out = await out
                results[name] = out if isinstance(out, dict) else {"result": out}
                self.actions.append({"remedy": name, "at": _now_iso(), **results[name]})
            except Exception as e:  # noqa: BLE001
                results[name] = {"error": f"{type(e).__name__}: {e}"}
                self.actions.append({"remedy": name, "at": _now_iso(), "error": results[name]["error"]})

        return {"healed_at": _now_iso(), "remedies": results}


class StewardCampfire(Campfire):
    """
    The Timberwolf steward campfire: monitor, keep, report, heal.

    Deterministic care for a valley. Wiring pattern matches DockmasterCampfire:
    four campers, each independently start/stop-able, each configurable
    through the campfire config steps.
    """

    def __init__(self, mcp_broker: Optional[IMCPBroker] = None, config: Optional[CampfireConfig] = None):
        if config is None:
            config = self._create_default_config()

        super().__init__(config, mcp_broker)

        step_cfg = lambda name: self._get_camper_config(name)  # noqa: E731

        self.monitor = MonitorCamper(step_cfg("monitor"))
        self.housekeeper = HousekeeperCamper(step_cfg("housekeeper"))
        self.report = ReportCamper(step_cfg("report"))
        self.self_heal = SelfHealCamper(step_cfg("self_heal"))

        self._campers = {
            "monitor": self.monitor,
            "housekeeper": self.housekeeper,
            "report": self.report,
            "self_heal": self.self_heal,
        }

        logger.info("StewardCampfire (Timberwolf) initialized")

    async def start(self) -> None:
        await super().start()
        for name, camper in self._campers.items():
            await camper.start()
            logger.debug("Started %s camper", name)
        logger.info("StewardCampfire started — the Timberwolf is on the ground")

    async def stop(self) -> None:
        for name, camper in self._campers.items():
            await camper.stop()
            logger.debug("Stopped %s camper", name)
        await super().stop()
        logger.info("StewardCampfire stopped")

    async def patrol(self) -> Dict[str, Any]:
        """
        One steward round: monitor, housekeep, self-heal, report.

        Order matters: observe first, then tidy, then heal what is known,
        then report the facts of the round. Facts flow downstream; the
        report carries everything the round produced.
        """
        for camper in (self.monitor, self.housekeeper, self.report, self.self_heal):
            if not camper._running:
                await camper.start()
        monitor = await self.monitor.process()
        housekeeping = await self.housekeeper.process()
        healing = await self.self_heal.process()
        report_result = await self.report.process(
            {"monitor": monitor, "housekeeping": housekeeping, "self_heal": healing}
        )
        return {
            "patrolled_at": _now_iso(),
            "monitor": monitor,
            "housekeeping": housekeeping,
            "self_heal": healing,
            "report": report_result,
        }

    async def process_torch(self, torch: Torch) -> Optional[Torch]:
        """A torch addressed to the steward triggers a patrol round."""
        if not self._running:
            logger.warning("StewardCampfire is not running, cannot process torch")
            return None
        await self.patrol()
        return None

    def _create_default_config(self) -> CampfireConfig:
        """Default configuration for the Timberwolf steward campfire."""
        return CampfireConfig(
            name="steward",
            runs_on="valley",
            env={
                "STEWARD_MODE": "timberwolf",
            },
            steps=[
                {
                    "name": "Monitor valley health",
                    "uses": "camper/monitor@v1",
                    "with": {},
                },
                {
                    "name": "Housekeep the valley",
                    "uses": "camper/housekeeper@v1",
                    "with": {},
                },
                {
                    "name": "Self-heal known failure shapes",
                    "uses": "camper/self_heal@v1",
                    "with": {},
                },
                {
                    "name": "Report to the queen bee",
                    "uses": "camper/report@v1",
                    "with": {
                        "target_valley": "",
                    },
                },
            ],
            channels=["steward-control", "pip-reports"],
            auditor_enabled=True,
        )

    def _get_camper_config(self, camper_name: str) -> Dict[str, Any]:
        """Extract configuration for a specific camper from campfire steps."""
        for step in self.config.steps:
            uses = step.get("uses", "")
            if f"camper/{camper_name}@" in uses:
                return step.get("with", {})
        return {}
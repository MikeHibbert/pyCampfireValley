"""
Valley manager implementation.
"""

import asyncio
import json
import logging
import os
import re
import uuid
from pathlib import Path
from typing import Optional, Dict, List, Any
from datetime import datetime
import yaml
from .interfaces import IValley, IDock, IPartyBox, IMCPBroker, IFederationManager, IKeyManager
from .models import ValleyConfig, CampfireConfig, CommunityMembership, FederationMembership
from .config import ConfigManager
from .config_manager import (
    get_config_manager, ConfigSource, ConfigFormat, 
    ConfigScope, ConfigEnvironment
)
from .monitoring import get_monitoring_system, LogLevel
from .voice import make_voice_torch


logger = logging.getLogger(__name__)


class Valley(IValley):
    """
    Valley manager that coordinates dock, campfires, and infrastructure components.
    """
    
    def __init__(
        self, 
        name: str, 
        manifest_path: str = './manifest.yaml',
        party_box: Optional[IPartyBox] = None,
        mcp_broker: str = 'redis://localhost:6379',
        config_dir: str = './config'
    ):
        """
        Initialize a Valley instance.
        
        Args:
            name: Name of the valley
            manifest_path: Path to the manifest.yaml configuration file
            party_box: Optional Party Box storage system instance
            mcp_broker: MCP broker connection string
            config_dir: Directory containing configuration files
        """
        self.name = name
        self.manifest_path = manifest_path
        self.mcp_broker_url = mcp_broker
        self.party_box = party_box
        self.config_dir = config_dir
        self._workflow_cache: Dict[str, Any] = {}
        self._schedule_tasks: Dict[str, asyncio.Task] = {}
        self._schedule_locks: Dict[str, asyncio.Lock] = {}
        self._last_schedule_run: Dict[str, Dict[str, Any]] = {}
        
        # Initialize configuration management
        self.config_manager = get_config_manager()
        self.monitoring = get_monitoring_system()
        
        # Load configuration
        try:
            self.config = ConfigManager.load_valley_config(manifest_path)
        except FileNotFoundError:
            logger.warning(f"Manifest file not found at {manifest_path}, creating default config")
            self.config = ConfigManager.create_default_valley_config(name)
            ConfigManager.save_valley_config(self.config, manifest_path)
        self.config.name = name
        
        # Initialize components (will be set during start())
        self.dock: Optional[IDock] = None
        self.mcp_broker: Optional[IMCPBroker] = None
        self.campfires: Dict[str, 'ICampfire'] = {}
        self.communities: Dict[str, CommunityMembership] = {}
        
        # Federation components
        self.federation_manager: Optional[IFederationManager] = None
        self.key_manager: Optional[IKeyManager] = None
        self.vali_coordinator: Optional['VALICoordinator'] = None
        self.federations: Dict[str, FederationMembership] = {}
        
        # Runtime state
        self._running = False
        self._tasks: List[asyncio.Task] = []
        
        logger.info(f"Valley '{name}' initialized with config from {manifest_path}")
    
    async def start(self) -> None:
        """Start the valley and all its components"""
        if self._running:
            logger.warning(f"Valley '{self.name}' is already running")
            return
        
        logger.info(f"Starting valley '{self.name}'...")
        
        try:
            # Load advanced configuration
            await self._load_advanced_config()
            
            # Log configuration loaded
            await self.monitoring.log(LogLevel.INFO, f"Configuration loaded for valley '{self.name}'", "valley")
            
        except Exception as e:
            logger.error(f"Failed to load configuration: {e}")
            # Continue with basic config
        
        try:
            # Initialize MCP broker only if URL is provided
            if not self.mcp_broker and self.mcp_broker_url:
                from .mcp import RedisMCPBroker  # Import here to avoid circular imports
                self.mcp_broker = RedisMCPBroker(self.mcp_broker_url)
            
            # Try to connect to MCP broker, but continue if it fails (for demo purposes)
            if self.mcp_broker:
                try:
                    broker_connected = await asyncio.wait_for(self.mcp_broker.connect(), timeout=6)
                    if broker_connected:
                        logger.info("MCP broker connected successfully")
                    else:
                        logger.warning("MCP broker connection failed, continuing without it")
                except Exception as e:
                    logger.warning(f"MCP broker connection failed: {e}, continuing without it")
            else:
                logger.info("No MCP broker configured, running in standalone mode")
            
            # Initialize Party Box if not provided
            if not self.party_box:
                from .party_box import FileSystemPartyBox  # Import here to avoid circular imports
                self.party_box = FileSystemPartyBox(f"./party_box_{self.name}")
            
            # Initialize key manager
            from .key_manager import CampfireKeyManager
            self.key_manager = CampfireKeyManager(valley_name=self.name)
            try:
                await asyncio.wait_for(self.key_manager.initialize_valley_keys(), timeout=8)
                logger.info("Key manager initialized")
            except Exception as e:
                logger.warning(f"Key manager initialization failed: {e}")
                self.key_manager = None
            
            # Initialize federation manager
            federation_config = await self.get_config_value("federation", {})
            if federation_config.get("enabled", False) and self.mcp_broker:
                from .federation import FederationManager
                self.federation_manager = FederationManager(
                    valley_name=self.name,
                    mcp_broker=self.mcp_broker,
                    key_manager=self.key_manager
                )
                await self.federation_manager.start()
                logger.info("Federation manager started")
            
            # Initialize VALI coordinator
            if self.mcp_broker:
                from .vali import VALICoordinator, VALIServiceRegistry
                registry = VALIServiceRegistry()
                self.vali_coordinator = VALICoordinator(
                    mcp_broker=self.mcp_broker,
                    registry=registry,
                    federation_manager=self.federation_manager,
                    valley_name=self.name
                )
                try:
                    await asyncio.wait_for(self.vali_coordinator.start(), timeout=6)
                    logger.info("VALI coordinator started")
                except Exception as e:
                    logger.warning(f"VALI coordinator start failed: {e}")
                    self.vali_coordinator = None
            
            # Create and start dock if auto_create_dock is enabled and MCP broker is connected
            if self.config.env.get("auto_create_dock", True) and self.mcp_broker and self.mcp_broker.is_connected():
                from .dock import Dock  # Import here to avoid circular imports
                self.dock = Dock(
                    valley=self,
                    mcp_broker=self.mcp_broker,
                    party_box=self.party_box,
                    federation_manager=self.federation_manager,
                    vali_coordinator=self.vali_coordinator
                )
                try:
                    await asyncio.wait_for(self.dock.start_gateway(), timeout=6)
                except Exception as e:
                    logger.warning(f"Dock start failed: {e}")
                    self.dock = None
            elif self.config.env.get("auto_create_dock", True):
                logger.warning("Dock creation skipped - MCP broker not connected")
            
            self._running = True
            logger.info(f"Valley '{self.name}' started successfully")
            self._start_schedules_from_disk()
            
        except Exception as e:
            logger.error(f"Failed to start valley '{self.name}': {e}")
            await self.stop()
            raise
    
    async def stop(self) -> None:
        """Stop the valley and cleanup resources"""
        if not self._running:
            return
        
        logger.info(f"Stopping valley '{self.name}'...")
        
        # Cancel all running tasks
        for task in self._tasks:
            if not task.done():
                task.cancel()
        for t in list(self._schedule_tasks.values()):
            if t and not t.done():
                t.cancel()
        
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        if self._schedule_tasks:
            await asyncio.gather(*self._schedule_tasks.values(), return_exceptions=True)
        self._schedule_tasks.clear()
        
        # Stop dock
        if self.dock:
            await self.dock.stop_gateway()
        
        # Stop VALI coordinator
        if self.vali_coordinator:
            await self.vali_coordinator.stop()
        
        # Stop federation manager
        if self.federation_manager:
            await self.federation_manager.stop()
        
        # Stop all campfires
        for campfire in self.campfires.values():
            await campfire.stop()
        
        # Disconnect MCP broker
        if self.mcp_broker:
            await self.mcp_broker.disconnect()
        
        self._running = False
        logger.info(f"Valley '{self.name}' stopped")
    
    async def join_community(self, community_name: str, key: str) -> bool:
        """Join a community with the given name and key"""
        if not self._running:
            raise RuntimeError("Valley must be started before joining communities")
        
        logger.info(f"Joining community '{community_name}'...")
        
        try:
            # Create community membership record
            membership = CommunityMembership(
                community_name=community_name,
                alias=self.name,
                key_hash=self._hash_key(key)  # This would use proper hashing
            )
            
            self.communities[community_name] = membership
            
            # TODO: Implement actual handshake with trusted neighbor
            # This would involve:
            # 1. Send handshake torch with join flag, alias, and key hash
            # 2. Wait for confirmation from trusted neighbor
            # 3. Exchange keys and update community membership
            
            logger.info(f"Successfully joined community '{community_name}'")
            return True
            
        except Exception as e:
            logger.error(f"Failed to join community '{community_name}': {e}")
            return False
    
    async def leave_community(self, community_name: str) -> bool:
        """Leave a community"""
        if community_name not in self.communities:
            logger.warning(f"Not a member of community '{community_name}'")
            return False
        
        logger.info(f"Leaving community '{community_name}'...")
        
        try:
            # TODO: Implement proper community leaving process
            # This would involve:
            # 1. Notify community members
            # 2. Revoke keys
            # 3. Clean up community-specific resources
            
            del self.communities[community_name]
            
            logger.info(f"Successfully left community '{community_name}'")
            return True
            
        except Exception as e:
            logger.error(f"Failed to leave community '{community_name}': {e}")
            return False
    
    async def join_federation(self, federation_id: str, discovery_endpoint: str = None) -> bool:
        """Join a federation"""
        if not self.federation_manager:
            logger.error("Federation manager not initialized")
            return False
        
        try:
            success = await self.federation_manager.join_federation(federation_id, discovery_endpoint)
            if success:
                # Create federation membership record
                membership = FederationMembership(
                    federation_id=federation_id,
                    valley_name=self.name,
                    joined_at=datetime.now(),
                    status="active",
                    capabilities=await self._get_valley_capabilities(),
                    discovery_endpoint=discovery_endpoint
                )
                self.federations[federation_id] = membership
                await self.monitoring.log(LogLevel.INFO, f"Joined federation: {federation_id}", "valley")
                logger.info(f"Successfully joined federation: {federation_id}")
            return success
        except Exception as e:
            logger.error(f"Error joining federation {federation_id}: {e}")
            return False
    
    async def leave_federation(self, federation_id: str) -> bool:
        """Leave a federation"""
        if not self.federation_manager:
            logger.error("Federation manager not initialized")
            return False
        
        try:
            success = await self.federation_manager.leave_federation(federation_id)
            if success and federation_id in self.federations:
                del self.federations[federation_id]
                await self.monitoring.log(LogLevel.INFO, f"Left federation: {federation_id}", "valley")
                logger.info(f"Successfully left federation: {federation_id}")
            return success
        except Exception as e:
            logger.error(f"Error leaving federation {federation_id}: {e}")
            return False
    
    async def discover_federation_valleys(self, federation_id: str = None) -> List[Dict]:
        """Discover valleys in federation(s)"""
        if not self.federation_manager:
            logger.error("Federation manager not initialized")
            return []
        
        try:
            return await self.federation_manager.discover_valleys(federation_id)
        except Exception as e:
            logger.error(f"Error discovering federation valleys: {e}")
            return []
    
    async def get_federation_memberships(self) -> Dict[str, FederationMembership]:
        """Get current federation memberships"""
        return self.federations.copy()
    
    async def _get_valley_capabilities(self) -> List[str]:
        """Get valley capabilities for federation announcement"""
        capabilities = ["torch_processing", "campfire_hosting"]
        
        if self.dock:
            capabilities.extend(["gateway", "routing", "discovery"])
        
        if self.vali_coordinator:
            capabilities.append("vali_services")
        
        # Add campfire-specific capabilities
        for campfire_name in self.campfires.keys():
            capabilities.append(f"campfire:{campfire_name}")
        
        return capabilities
    
    async def provision_campfire(self, campfire_config: CampfireConfig) -> bool:
        """Provision a new campfire from configuration"""
        if not self._running:
            raise RuntimeError("Valley must be started before provisioning campfires")
        
        campfire_name = campfire_config.name
        
        if campfire_name in self.campfires:
            logger.warning(f"Campfire '{campfire_name}' already exists")
            return False
        
        logger.info(f"Provisioning campfire '{campfire_name}' of type '{campfire_config.type}'...")
        
        try:
            try:
                if isinstance(campfire_config.config, dict):
                    ident = (campfire_config.config.get("identity") or {})
                    if not isinstance(ident, dict):
                        ident = {}
                    uid = (ident.get("uuid") or "").strip()
                    if not uid:
                        uid = uuid.uuid4().hex
                        ident["uuid"] = uid
                        campfire_config.config["identity"] = ident
            except Exception:
                pass
            # Create the appropriate campfire type based on configuration
            campfire = None
            
            if campfire_config.type == "LLMCampfire":
                llm_config = campfire_config.config.get('llm', {}) if isinstance(campfire_config.config, dict) else {}
                provider = (llm_config.get("provider") or os.getenv("LLM_PROVIDER") or "").strip().lower()
                if not provider:
                    provider = "ollama" if not os.getenv("OPENROUTER_API_KEY") else "openrouter"
                model = llm_config.get('model', 'gemma3:4b')

                if provider == "openrouter":
                    from .llm_campfire import create_openrouter_campfire
                    api_key = llm_config.get('api_key') or os.getenv('OPENROUTER_API_KEY') or 'demo_key_placeholder'
                    campfire = create_openrouter_campfire(
                        campfire_config,
                        self.mcp_broker,
                        api_key=api_key,
                        default_model=model
                    )
                    logger.info(f"Created LLMCampfire '{campfire_name}' via OpenRouter with model '{model}'")
                else:
                    from .llm_campfire import create_ollama_campfire
                    base_url = llm_config.get("base_url") or os.getenv("OLLAMA_HOST", "http://host.docker.internal:11434")
                    campfire = create_ollama_campfire(
                        campfire_config,
                        self.mcp_broker,
                        base_url=base_url,
                        default_model=model
                    )
                    logger.info(f"Created LLMCampfire '{campfire_name}' via Ollama with model '{model}'")
                
            elif campfire_config.type == "dockmaster":
                from .campfires.dockmaster import DockmasterCampfire
                campfire = DockmasterCampfire(
                    name=campfire_name,
                    valley_name=self.name,
                    federation_manager=self.federation_manager
                )
            elif campfire_config.type == "sanitizer":
                from .security_scanner import SanitizerCampfire
                campfire = SanitizerCampfire(
                    name=campfire_name,
                    valley_name=self.name
                )
            elif campfire_config.type == "justice":
                from .justice import JusticeCampfire
                campfire = JusticeCampfire(
                    name=campfire_name,
                    valley_name=self.name
                )
            else:
                # Default to basic campfire
                from .campfire import Campfire
                campfire = Campfire(campfire_config, self.mcp_broker, self.party_box)
                logger.info(f"Created basic Campfire '{campfire_name}'")
            
            # Start the campfire
            await campfire.start()
            
            self.campfires[campfire_name] = campfire

            lower_name = campfire_name.strip().lower()
            is_auditor_name = lower_name == "auditor" or lower_name.endswith(" auditor")
            if not is_auditor_name:
                auditor_name = f"{campfire_name} Auditor"
                if auditor_name not in self.campfires:
                    llm_cfg = {}
                    if isinstance(campfire_config.config, dict):
                        llm_cfg = (campfire_config.config.get("llm") or {}) if isinstance(campfire_config.config.get("llm"), dict) else {}
                    provider = (llm_cfg.get("provider") or os.getenv("LLM_PROVIDER") or "ollama").strip().lower()
                    if provider not in {"ollama", "openrouter"}:
                        provider = "ollama"
                    model = llm_cfg.get("model") or "gemma3:4b"
                    base_url = llm_cfg.get("base_url") or os.getenv("OLLAMA_HOST", "http://host.docker.internal:11434")
                    system_prompt = (
                        "You are the Auditor and Orchestrator for this Campfire. You do not solve the user's domain problem. "
                        "You identify which campers are needed, create them, assign them ordered tasks, and coordinate their outputs. "
                        "Ask clarifying questions when needed and confirm actions."
                    )
                    auditor_cfg = CampfireConfig(
                        name=auditor_name,
                        type="LLMCampfire",
                        config={
                            "llm": {
                                "provider": provider,
                                "base_url": base_url,
                                "model": model,
                            },
                            "prompts": {"system": system_prompt},
                        },
                    )
                    await self.provision_campfire(auditor_cfg)
            
            # Register with VALI if available
            if self.vali_coordinator and hasattr(campfire, 'get_service_type'):
                try:
                    await self.vali_coordinator.register_service(campfire)
                    logger.info(f"Registered campfire '{campfire_name}' with VALI")
                except Exception as e:
                    logger.warning(f"Failed to register campfire '{campfire_name}' with VALI: {e}")
            
            logger.info(f"Successfully provisioned campfire '{campfire_name}'")
            return True
            
        except Exception as e:
            logger.error(f"Failed to provision campfire '{campfire_name}': {e}")
            return False
    
    async def deprovision_campfire(self, campfire_name: str) -> bool:
        """Remove and stop a campfire"""
        try:
            if campfire_name not in self.campfires:
                logger.warning(f"Campfire '{campfire_name}' not found")
                return False
            
            campfire = self.campfires[campfire_name]
            
            # Unregister from VALI if available
            if self.vali_coordinator and hasattr(campfire, 'get_service_type'):
                try:
                    await self.vali_coordinator.unregister_service(campfire_name)
                    logger.info(f"Unregistered campfire '{campfire_name}' from VALI")
                except Exception as e:
                    logger.warning(f"Failed to unregister campfire '{campfire_name}' from VALI: {e}")
            
            # Stop the campfire
            await campfire.stop()
            del self.campfires[campfire_name]
            
            await self.monitoring.log(LogLevel.INFO, f"Deprovisioned campfire: {campfire_name}", "valley")
            logger.info(f"Successfully deprovisioned campfire: {campfire_name}")
            return True
            
        except Exception as e:
            logger.error(f"Error deprovisioning campfire '{campfire_name}': {e}")
            return False
    
    def get_config(self) -> ValleyConfig:
        """Get the valley configuration"""
        return self.config
    
    def is_running(self) -> bool:
        """Check if the valley is currently running"""
        return self._running
    
    def get_communities(self) -> Dict[str, CommunityMembership]:
        """Get all community memberships"""
        return self.communities.copy()
    
    def get_campfires(self) -> Dict[str, 'ICampfire']:
        """Get all active campfires"""
        return self.campfires.copy()

    def _workflow_dir(self) -> Path:
        p = Path(os.getenv("CONFIG_DIR", "/app/data/configs"))
        p.mkdir(parents=True, exist_ok=True)
        return p

    def _slugify_workflow_key(self, name: str) -> str:
        s = (name or "").strip().lower()
        s = re.sub(r"[^a-z0-9]+", "_", s)
        s = re.sub(r"_+", "_", s).strip("_")
        return s or "campfire"

    def _workflow_path_for(self, campfire_name: str) -> Path:
        return self._workflow_dir() / f"workflow_{self._slugify_workflow_key(campfire_name)}.yaml"

    def get_workflow(self, campfire_name: str) -> Optional[Dict[str, Any]]:
        if not campfire_name:
            return None
        path = self._workflow_path_for(campfire_name)
        try:
            mtime = path.stat().st_mtime if path.exists() else None
        except Exception:
            mtime = None
        cached = self._workflow_cache.get(campfire_name)
        if cached and cached.get("mtime") == mtime:
            return cached.get("data")
        if not path.exists():
            self._workflow_cache[campfire_name] = {"mtime": mtime, "data": None}
            return None
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or None
        except Exception:
            data = None
        self._workflow_cache[campfire_name] = {"mtime": mtime, "data": data}
        return data

    def set_workflow(self, campfire_name: str, steps: List[Dict[str, Any]]) -> bool:
        if not campfire_name:
            return False
        clean_steps: List[Dict[str, Any]] = []
        for s in steps or []:
            if not isinstance(s, dict):
                continue
            camper = (s.get("camper") or "").strip()
            task = (s.get("task") or "").strip()
            if not camper or not task:
                continue
            cid = (s.get("camper_id") or "").strip()
            if not cid:
                try:
                    cf = self.campfires.get(camper)
                    cfg = getattr(cf, "config", None)
                    raw_conf = {}
                    if isinstance(cfg, CampfireConfig):
                        raw_conf = cfg.config or {}
                    elif isinstance(cfg, dict):
                        raw_conf = cfg.get("config") if isinstance(cfg.get("config"), dict) else cfg
                    ident = raw_conf.get("identity") if isinstance(raw_conf.get("identity"), dict) else {}
                    uid = (ident.get("uuid") or "").strip()
                    if uid:
                        cid = uid
                except Exception:
                    cid = ""
            out_step = {"camper": camper, "task": task}
            if cid:
                out_step["camper_id"] = cid
            clean_steps.append(out_step)
        existing = self.get_workflow(campfire_name) or {}
        schedule = existing.get("schedule") if isinstance(existing, dict) else None
        payload = {"version": 1, "campfire": campfire_name, "steps": clean_steps, "updated_at": datetime.utcnow().isoformat()}
        if isinstance(schedule, dict):
            payload["schedule"] = schedule
        path = self._workflow_path_for(campfire_name)
        try:
            path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
            try:
                mtime = path.stat().st_mtime
            except Exception:
                mtime = None
            self._workflow_cache[campfire_name] = {"mtime": mtime, "data": payload}
            return True
        except Exception:
            return False

    def get_schedule(self, campfire_name: str) -> Optional[Dict[str, Any]]:
        wf = self.get_workflow(campfire_name) or {}
        schedule = wf.get("schedule") if isinstance(wf, dict) else None
        return schedule if isinstance(schedule, dict) else None

    def set_schedule(self, campfire_name: str, interval_seconds: int, input_text: Optional[str] = None) -> bool:
        if not campfire_name:
            return False
        try:
            interval_seconds = int(interval_seconds)
        except Exception:
            return False
        if interval_seconds < 5:
            interval_seconds = 5
        wf = self.get_workflow(campfire_name) or {}
        if not isinstance(wf, dict):
            wf = {"version": 1, "campfire": campfire_name, "steps": []}
        schedule = {
            "enabled": True,
            "interval_seconds": interval_seconds,
            "input": (input_text or "").strip(),
            "updated_at": datetime.utcnow().isoformat(),
        }
        wf["schedule"] = schedule
        wf["updated_at"] = datetime.utcnow().isoformat()
        path = self._workflow_path_for(campfire_name)
        try:
            path.write_text(yaml.safe_dump(wf, sort_keys=False), encoding="utf-8")
            try:
                mtime = path.stat().st_mtime
            except Exception:
                mtime = None
            self._workflow_cache[campfire_name] = {"mtime": mtime, "data": wf}
        except Exception:
            return False
        self.refresh_schedule(campfire_name)
        return True

    def clear_schedule(self, campfire_name: str) -> bool:
        if not campfire_name:
            return False
        wf = self.get_workflow(campfire_name) or {}
        if not isinstance(wf, dict):
            wf = {"version": 1, "campfire": campfire_name, "steps": []}
        if "schedule" in wf:
            wf.pop("schedule", None)
            wf["updated_at"] = datetime.utcnow().isoformat()
            path = self._workflow_path_for(campfire_name)
            try:
                path.write_text(yaml.safe_dump(wf, sort_keys=False), encoding="utf-8")
                try:
                    mtime = path.stat().st_mtime
                except Exception:
                    mtime = None
                self._workflow_cache[campfire_name] = {"mtime": mtime, "data": wf}
            except Exception:
                return False
        self.refresh_schedule(campfire_name)
        return True

    def refresh_schedule(self, campfire_name: str) -> None:
        t = self._schedule_tasks.get(campfire_name)
        if t and not t.done():
            t.cancel()
        self._schedule_tasks.pop(campfire_name, None)
        if not self._running:
            return
        schedule = self.get_schedule(campfire_name)
        if not schedule or not schedule.get("enabled"):
            return
        task = asyncio.create_task(self._schedule_loop(campfire_name))
        self._schedule_tasks[campfire_name] = task
        self._tasks.append(task)

    def _start_schedules_from_disk(self) -> None:
        try:
            cfg_dir = self._workflow_dir()
            paths = list(cfg_dir.glob("workflow_*.yaml"))
        except Exception:
            paths = []
        for p in paths:
            try:
                data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
            except Exception:
                continue
            campfire_name = data.get("campfire") if isinstance(data, dict) else None
            if not isinstance(campfire_name, str) or not campfire_name.strip():
                continue
            schedule = data.get("schedule") if isinstance(data, dict) else None
            if isinstance(schedule, dict) and schedule.get("enabled"):
                self.refresh_schedule(campfire_name.strip())

    async def _schedule_loop(self, campfire_name: str) -> None:
        lock = self._schedule_locks.get(campfire_name)
        if lock is None:
            lock = asyncio.Lock()
            self._schedule_locks[campfire_name] = lock
        while self._running:
            schedule = self.get_schedule(campfire_name) or {}
            if not schedule.get("enabled"):
                return
            try:
                interval = int(schedule.get("interval_seconds") or 0)
            except Exception:
                interval = 0
            if interval < 5:
                interval = 5
            await asyncio.sleep(interval)
            if not self._running:
                return
            if campfire_name not in self.campfires:
                continue
            async with lock:
                schedule = self.get_schedule(campfire_name) or {}
                if not schedule.get("enabled"):
                    return
                input_text = (schedule.get("input") or "").strip()
                if not input_text:
                    input_text = f"Scheduled run at {datetime.utcnow().isoformat()}"
                try:
                    from .models import Torch
                    torch = Torch(
                        claim="scheduled_request",
                        source_campfire="scheduler",
                        channel="schedule",
                        torch_id=f"schedule_{uuid.uuid4().hex}",
                        sender_valley=self.name,
                        target_address=f"valley:{self.name}/{campfire_name}",
                        data={"text": input_text},
                        signature="schedule_placeholder",
                    )
                    resp = await self.process_torch(torch)
                    self._last_schedule_run[campfire_name] = {"at": datetime.utcnow().isoformat(), "ok": bool(resp), "response": getattr(resp, "data", None)}
                except Exception as e:
                    self._last_schedule_run[campfire_name] = {"at": datetime.utcnow().isoformat(), "ok": False, "error": str(e)}

    def clear_workflow(self, campfire_name: str) -> bool:
        if not campfire_name:
            return False
        path = self._workflow_path_for(campfire_name)
        try:
            if path.exists():
                path.unlink()
        except Exception:
            return False
        self._workflow_cache.pop(campfire_name, None)
        return True

    def _torch_text(self, torch: 'Torch') -> str:
        try:
            if isinstance(torch.data, dict):
                return (torch.data.get("content") or torch.data.get("text") or "").strip() or json.dumps(torch.data)
        except Exception:
            pass
        return str(getattr(torch, "data", "") or "")

    def _is_service_torch(self, torch: 'Torch') -> bool:
        if getattr(torch, "claim", None) == "voice_text":
            return False
        if getattr(torch, "source_campfire", None) == "voice":
            return False
        if isinstance(getattr(torch, "data", None), dict) and torch.data.get("admin") is True:
            return False
        return True

    async def process_service_call(self, campfire_name: str, torch: 'Torch') -> Optional['Torch']:
        if not self._is_service_torch(torch):
            return None
        workflow = self.get_workflow(campfire_name) or {}
        steps = workflow.get("steps") if isinstance(workflow, dict) else None
        if not isinstance(steps, list) or not steps:
            return None
        corr = None
        try:
            if hasattr(torch, "metadata") and isinstance(torch.metadata, dict):
                corr = (torch.metadata.get("correlation_id") or "").strip() or None
        except Exception:
            corr = None
        corr = corr or getattr(torch, "torch_id", None) or getattr(torch, "id", None)
        user_input = self._torch_text(torch)
        outputs: List[Dict[str, Any]] = []
        for idx, step in enumerate(steps[:20]):
            if not isinstance(step, dict):
                continue
            camper = (step.get("camper") or "").strip()
            camper_id = (step.get("camper_id") or "").strip()
            task_tmpl = (step.get("task") or "").strip()
            if not camper or not task_tmpl:
                continue
            campfire = None
            if camper_id:
                for n, cf in self.campfires.items():
                    try:
                        cfg = getattr(cf, "config", None)
                        raw = {}
                        if isinstance(cfg, CampfireConfig):
                            raw = cfg.config or {}
                        elif isinstance(cfg, dict):
                            raw = cfg.get("config") if isinstance(cfg.get("config"), dict) else cfg
                        ident = raw.get("identity") if isinstance(raw.get("identity"), dict) else {}
                        uid = (ident.get("uuid") or "").strip()
                        if uid and uid == camper_id:
                            campfire = cf
                            camper = n  # normalize to resolved name
                            break
                    except Exception:
                        continue
            if campfire is None:
                campfire = self.campfires.get(camper)
            if not campfire:
                outputs.append({"step": idx + 1, "camper": camper, "ok": False, "error": "missing_camper"})
                continue
            prior_blocks = []
            for o in outputs:
                if not isinstance(o, dict):
                    continue
                if not o.get("response"):
                    continue
                prior_blocks.append(f"Step {o.get('step')}: {o.get('camper')}\n{o.get('response')}")
            prior_text = "\n\n---\n\n".join(prior_blocks)
            if "{input}" in task_tmpl or "{previous}" in task_tmpl:
                prompt = task_tmpl.replace("{input}", user_input).replace("{previous}", prior_text)
            else:
                prompt = (
                    f"{task_tmpl}\n\n"
                    f"Input:\n{user_input}\n\n"
                    f"Previous step outputs:\n{prior_text if prior_text else '(none)'}\n\n"
                    f"Return a non-empty response."
                )
            is_last = True
            try:
                for nxt in (steps[idx + 1 : 20] if isinstance(steps, list) else []):
                    if not isinstance(nxt, dict):
                        continue
                    n_camper = (nxt.get("camper") or "").strip()
                    n_task = (nxt.get("task") or "").strip()
                    if n_camper and n_task:
                        is_last = False
                        break
            except Exception:
                is_last = False
            if is_last:
                prompt = (
                    prompt
                    + "\n\n"
                    + "You are the final report author. Produce the final report based on the Input and the Previous step outputs.\n\n"
                    + "Requirements:\n"
                    + "1) Produce a cohesive, client-facing report (not a step-by-step trace).\n"
                    + "2) Include a section titled 'Role Contributions' that proves synthesis.\n"
                    + "3) In 'Role Contributions', for each prior step output, include 2–3 bullet points that:\n"
                    + "   - Cite the originating step number and camper name.\n"
                    + "   - Include a short direct quote (<= 12 words) from that step output.\n"
                    + "   - Explain how that contribution affected the final recommendations.\n"
                    + "4) If any prior step output contradicts another, call it out and resolve it.\n"
                    + "5) Do not ask the user what to do next; deliver the report."
                )
            step_torch = type(torch)(
                claim="workflow_step",
                source_campfire=f"{campfire_name} Auditor",
                channel="workflow",
                torch_id=f"workflow_{uuid.uuid4().hex}",
                sender_valley=self.name,
                target_address=f"valley:{self.name}/{camper}",
                data={"text": prompt, "service_mode": True, "parent": campfire_name, "step": idx + 1},
                signature="workflow_placeholder",
                metadata={"correlation_id": corr, "parent": campfire_name, "step": idx + 1, "camper": camper},
            )
            resp = await campfire.process_torch(step_torch)
            text = None
            if resp is not None and hasattr(resp, "data") and isinstance(resp.data, dict):
                text = (resp.data.get("llm_response") or resp.data.get("text") or "").strip() or None
            if text is None:
                retry_torch = type(torch)(
                    claim="workflow_step",
                    source_campfire=f"{campfire_name} Auditor",
                    channel="workflow",
                    torch_id=f"workflow_{uuid.uuid4().hex}",
                    sender_valley=self.name,
                    target_address=f"valley:{self.name}/{camper}",
                    data={
                        "text": prompt + "\n\nIMPORTANT: You must return a non-empty response. If unsure, return a concise best-effort answer.",
                        "service_mode": True,
                        "parent": campfire_name,
                        "step": idx + 1,
                        "retry": True,
                    },
                    signature="workflow_placeholder",
                    metadata={"correlation_id": corr, "parent": campfire_name, "step": idx + 1, "camper": camper, "retry": True},
                )
                resp = await campfire.process_torch(retry_torch)
                if resp is not None and hasattr(resp, "data") and isinstance(resp.data, dict):
                    text = (resp.data.get("llm_response") or resp.data.get("text") or "").strip() or None
            if is_last and prior_text and text is not None:
                try:
                    if "role contributions" not in text.lower():
                        forced = (
                            prompt
                            + "\n\n"
                            + "IMPORTANT: Your previous response did not include the required 'Role Contributions' section.\n"
                            + "You MUST include it exactly with that title.\n\n"
                            + "Use this template:\n"
                            + "## Final Report\n"
                            + "(client-facing report)\n\n"
                            + "## Role Contributions\n"
                            + "- Step 1 (Camper Name): \"short quote\" — how it changed the final report\n"
                            + "- Step 2 (Camper Name): \"short quote\" — how it changed the final report\n"
                            + "(repeat for every prior step)\n"
                        )
                        retry_torch = type(torch)(
                            claim="workflow_step",
                            source_campfire=f"{campfire_name} Auditor",
                            channel="workflow",
                            torch_id=f"workflow_{uuid.uuid4().hex}",
                            sender_valley=self.name,
                            target_address=f"valley:{self.name}/{camper}",
                            data={"text": forced, "service_mode": True, "parent": campfire_name, "step": idx + 1, "retry": True, "retry_reason": "missing_role_contributions"},
                            signature="workflow_placeholder",
                            metadata={"correlation_id": corr, "parent": campfire_name, "step": idx + 1, "camper": camper, "retry": True, "retry_reason": "missing_role_contributions"},
                        )
                        resp = await campfire.process_torch(retry_torch)
                        if resp is not None and hasattr(resp, "data") and isinstance(resp.data, dict):
                            text = (resp.data.get("llm_response") or resp.data.get("text") or "").strip() or None
                except Exception:
                    pass
            step_ok = bool(text)
            outputs.append({"step": idx + 1, "camper": camper, "ok": step_ok, "response": text, "data": getattr(resp, "data", None)})
            if not step_ok:
                result = {
                    "ok": False,
                    "error": "no_response",
                    "text": f"Workflow halted: step {idx + 1} ({camper}) returned no response.",
                    "campfire": campfire_name,
                    "results": outputs,
                }
                try:
                    await self.monitoring.log(
                        LogLevel.WARNING,
                        f"Workflow halted for '{campfire_name}'",
                        f"workflow.{campfire_name}",
                        context={"steps_total": len(steps or []), "steps_ok": len([o for o in outputs if isinstance(o, dict) and o.get('ok')]), "halted_at": idx + 1, "halted_camper": camper},
                        correlation_id=corr,
                    )
                except Exception:
                    pass
                return type(torch)(
                    claim="service_response",
                    source_campfire=f"{campfire_name} Auditor",
                    channel="service",
                    torch_id=f"service_{uuid.uuid4().hex}",
                    sender_valley=self.name,
                    target_address=f"valley:{torch.sender_valley}",
                    data=result,
                    signature="service_placeholder",
                    metadata={"correlation_id": corr, "parent": campfire_name},
                )
        final_text = ""
        for o in reversed(outputs):
            if o.get("response"):
                final_text = str(o["response"])
                break
        report_lines = []
        for o in outputs:
            if not isinstance(o, dict):
                continue
            title = f"Step {o.get('step')}: {o.get('camper')}"
            body = (o.get("response") or "").strip()
            report_lines.append(title + "\n" + (body if body else "(no response)"))
        report = "\n\n---\n\n".join(report_lines)
        editor_text = None
        try:
            for o in reversed(outputs):
                if not isinstance(o, dict):
                    continue
                nm = str(o.get("camper") or "").strip().lower()
                if "editor" in nm or "reporter" in nm:
                    t = (o.get("response") or "").strip()
                    if t:
                        editor_text = t
                        break
        except Exception:
            editor_text = None
        result = {"ok": True, "text": editor_text or (final_text or report or "Workflow completed."), "campfire": campfire_name, "results": outputs}
        try:
            total_steps = len([s for s in (steps or []) if isinstance(s, dict) and (s.get("camper") or "").strip() and (s.get("task") or "").strip()])
            ok_steps = len([o for o in outputs if isinstance(o, dict) and o.get("ok")])
            missing = [o.get("camper") for o in outputs if isinstance(o, dict) and o.get("error") == "missing_camper" and o.get("camper")]
            await self.monitoring.log(
                LogLevel.INFO,
                f"Workflow completed for '{campfire_name}'",
                f"workflow.{campfire_name}",
                context={"steps_total": total_steps, "steps_ok": ok_steps, "missing": missing},
                correlation_id=corr,
            )
        except Exception:
            pass
        return type(torch)(
            claim="service_response",
            source_campfire=f"{campfire_name} Auditor",
            channel="service",
            torch_id=f"service_{uuid.uuid4().hex}",
            sender_valley=self.name,
            target_address=f"valley:{torch.sender_valley}",
            data=result,
            signature="service_placeholder",
            metadata={"correlation_id": corr, "parent": campfire_name},
        )
    
    async def process_torch(self, torch: 'Torch') -> Optional['Torch']:
        """Process a torch by routing it to the appropriate campfire"""
        if not self._running:
            raise RuntimeError("Valley must be started before processing torches")
        
        logger.info(f"Processing torch {torch.torch_id} from {torch.sender_valley}")
        
        try:
            # Parse target address to find the campfire
            # Format: valley:campfire or valley:name/campfire/camper or just campfire_name
            campfire_name = torch.target_address
            
            # Handle valley:campfire format
            if ':' in campfire_name:
                parts = campfire_name.split(':', 1)
                if len(parts) == 2:
                    valley_name, campfire_part = parts
                    # If it's for this valley, extract the campfire name
                    if valley_name == self.name:
                        campfire_name = campfire_part
                    else:
                        # Different valley - this shouldn't happen in local processing
                        logger.warning(f"Torch target valley '{valley_name}' doesn't match current valley '{self.name}'")
                        campfire_name = campfire_part
            
            # Handle path-based format: valley:name/campfire/camper
            target_parts = campfire_name.split('/')
            if len(target_parts) >= 2:
                campfire_name = target_parts[1]
            
            # Remove any "campfire:" prefix if present
            if campfire_name.startswith("campfire:"):
                campfire_name = campfire_name[9:]
            
            # Get the campfire
            resolved_name = campfire_name
            if resolved_name not in self.campfires:
                resolved_name = self._resolve_campfire_by_identifier(campfire_name) or campfire_name
            if resolved_name in self.campfires:
                campfire = self.campfires[resolved_name]
                logger.info(f"Routing torch {torch.torch_id} to campfire '{resolved_name}'")
                service_resp = await self.process_service_call(resolved_name, torch)
                if service_resp is not None:
                    return service_resp
                return await campfire.process_torch(torch)
            else:
                # If no specific campfire found, try to route through dock if available
                if self.dock:
                    logger.info(f"Routing torch {torch.torch_id} through dock")
                    await self.dock.handle_incoming_torch(torch)
                    return None
                else:
                    available_campfires = list(self.campfires.keys())
                    logger.error(f"Campfire '{campfire_name}' not found. Available campfires: {available_campfires}")
                    raise ValueError(f"Campfire '{campfire_name}' not found in valley '{self.name}'")
                    
        except Exception as e:
            logger.error(f"Error processing torch {torch.torch_id}: {e}")
            raise

    def _resolve_campfire_by_identifier(self, identifier: str) -> Optional[str]:
        ident = (identifier or "").strip()
        if not ident:
            return None
        matches: List[str] = []
        for name, cf in (self.campfires or {}).items():
            cfg = getattr(cf, "config", None)
            conf: Dict[str, Any] = {}
            if isinstance(cfg, CampfireConfig):
                conf = cfg.config or {}
            elif isinstance(cfg, dict):
                conf = cfg.get("config") if isinstance(cfg.get("config"), dict) else cfg
            dock = conf.get("dock") if isinstance(conf.get("dock"), dict) else {}
            v = dock.get("identifier") if isinstance(dock, dict) else None
            v = (str(v).strip() if v is not None else "")
            if v and v == ident:
                matches.append(str(name))
        if not matches:
            return None
        if len(matches) > 1:
            logger.warning(f"Multiple campfires share identifier '{ident}': {matches}. Using '{matches[0]}'.")
        return matches[0]
    
    async def _load_advanced_config(self) -> None:
        """Load advanced configuration from config directory"""
        config_path = Path(self.config_dir)
        
        if not config_path.exists():
            logger.warning(f"Config directory not found: {config_path}")
            return
        
        # Determine current environment
        import os
        env_name = os.environ.get("CAMPFIRE_ENV", "development").lower()
        try:
            current_env = ConfigEnvironment(env_name)
        except ValueError:
            current_env = ConfigEnvironment.DEVELOPMENT
            logger.warning(f"Unknown environment '{env_name}', using development")
        
        # Minimal validation rules for core fields
        try:
            from .config_manager import ConfigValidationRule
            self.config_manager.add_validation_rule(
                ConfigValidationRule(field_path="env.dock_mode", rule_type="required")
            )
            self.config_manager.add_validation_rule(
                ConfigValidationRule(field_path="campfires.visible", rule_type="type", parameters={"type": list})
            )
        except Exception as e:
            logger.debug(f"Skipping validation rule setup: {e}")
        
        # Load default configuration first (lowest priority)
        default_config = config_path / "default.yaml"
        if default_config.exists():
            source = ConfigSource(
                path=str(default_config),
                format=ConfigFormat.YAML,
                scope=ConfigScope.VALLEY,
                priority=0
            )
            self.config_manager.add_source(source)
        
        # Load environment-specific configuration (higher priority)
        env_config = config_path / f"{current_env.value}.yaml"
        if env_config.exists():
            source = ConfigSource(
                path=str(env_config),
                format=ConfigFormat.YAML,
                scope=ConfigScope.VALLEY,
                environment=current_env,
                priority=10
            )
            self.config_manager.add_source(source)
        
        # Load valley-specific configuration (highest priority)
        valley_config = config_path / f"{self.name.lower()}.yaml"
        if valley_config.exists():
            source = ConfigSource(
                path=str(valley_config),
                format=ConfigFormat.YAML,
                scope=ConfigScope.VALLEY,
                priority=20
            )
            self.config_manager.add_source(source)
        
        # Load all configurations
        await self.config_manager.load_all_configs()
        
        # Add change callback to monitor config changes
        self.config_manager.add_change_callback(self._on_config_changed)
        
        logger.info(f"Advanced configuration loaded for environment: {current_env.value}")
    
    async def _on_config_changed(self, new_config: Dict) -> None:
        """Handle configuration changes"""
        logger.info("Configuration changed, applying updates...")
        await self.monitoring.log(LogLevel.INFO, "Configuration updated", "valley")
        
        # Here you could implement hot-reloading of specific components
        # For now, just log the change
        
    async def get_config_value(self, path: str, default=None):
        """Get a configuration value using the advanced config system"""
        try:
            return await self.config_manager.get_config(path, default)
        except Exception as e:
            logger.error(f"Error getting config value '{path}': {e}")
            return default
    
    async def set_config_value(self, path: str, value) -> None:
        """Set a configuration value using the advanced config system"""
        try:
            await self.config_manager.set_config(path, value)
        except Exception as e:
            logger.error(f"Error setting config value '{path}': {e}")
    
    def _hash_key(self, key: str) -> str:
        """Hash a key for secure storage"""
        import hashlib
        return hashlib.sha256(key.encode()).hexdigest()
    
    async def get_valley_status(self) -> Dict:
        """Get comprehensive valley status"""
        status = {
            "name": self.name,
            "running": self._running,
            "components": {
                "mcp_broker": self.mcp_broker is not None and getattr(self.mcp_broker, 'is_connected', lambda: False)(),
                "dock": self.dock is not None,
                "federation_manager": self.federation_manager is not None,
                "vali_coordinator": self.vali_coordinator is not None,
                "key_manager": self.key_manager is not None
            },
            "campfires": {
                "count": len(self.campfires),
                "names": list(self.campfires.keys())
            },
            "communities": {
                "count": len(self.communities),
                "names": list(self.communities.keys())
            },
            "federations": {
                "count": len(self.federations),
                "names": list(self.federations.keys())
            }
        }
        
        # Add federation-specific status if available
        if self.federation_manager:
            try:
                fed_status = await self.federation_manager.get_status()
                status["federation_status"] = fed_status
            except Exception as e:
                status["federation_status"] = {"error": str(e)}
        
        return status
    
    async def health_check(self) -> Dict:
        """Perform health check on valley components"""
        health = {
            "overall": "healthy",
            "components": {},
            "issues": []
        }
        
        # Check MCP broker
        if self.mcp_broker:
            try:
                connected = getattr(self.mcp_broker, 'is_connected', lambda: False)()
                health["components"]["mcp_broker"] = "healthy" if connected else "unhealthy"
                if not connected:
                    health["issues"].append("MCP broker not connected")
            except Exception as e:
                health["components"]["mcp_broker"] = "error"
                health["issues"].append(f"MCP broker error: {e}")
        else:
            health["components"]["mcp_broker"] = "missing"
            health["issues"].append("MCP broker not initialized")
        
        # Check dock
        if self.dock:
            health["components"]["dock"] = "healthy"
        else:
            health["components"]["dock"] = "missing"
        
        # Check federation manager
        if self.federation_manager:
            health["components"]["federation_manager"] = "healthy"
        else:
            health["components"]["federation_manager"] = "missing"
        
        # Check campfires
        campfire_issues = []
        for name, campfire in self.campfires.items():
            try:
                # Basic health check - campfire should be responsive
                health["components"][f"campfire_{name}"] = "healthy"
            except Exception as e:
                health["components"][f"campfire_{name}"] = "error"
                campfire_issues.append(f"Campfire {name}: {e}")
        
        if campfire_issues:
            health["issues"].extend(campfire_issues)
        
        # Determine overall health
        if health["issues"]:
            health["overall"] = "degraded" if len(health["issues"]) < 3 else "unhealthy"
        
        return health
    
    async def send_voice_text(self, campfire: Optional[str], text: str, admin: bool = False) -> Dict[str, Any]:
        """Send a voice-transcribed text message into a campfire"""
        if not self._running:
            raise RuntimeError("Valley must be started")
        target = campfire or (next(iter(self.campfires)) if self.campfires else None)
        if not target:
            raise ValueError("No campfire available")
        torch_dict = make_voice_torch(self.name, target, text, admin)
        from .models import Torch
        torch = Torch(**torch_dict)
        resp = await self.process_torch(torch)
        if resp and hasattr(resp, "data"):
            return {"status": "ok", "campfire": target, "response": resp.data}
        return {"status": "ok", "campfire": target, "response": None}
    
    def __repr__(self) -> str:
        return f"Valley(name='{self.name}', running={self._running}, campfires={len(self.campfires)}, federations={len(self.federations)})"

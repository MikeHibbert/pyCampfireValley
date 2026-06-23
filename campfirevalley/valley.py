"""
Valley manager implementation.
"""

import asyncio
import html
import json
import logging
import os
import re
import uuid
from pathlib import Path
from typing import Optional, Dict, List, Any, Tuple
from datetime import datetime
import yaml
from .interfaces import IValley, IDock, IPartyBox, IMCPBroker, IFederationManager, IKeyManager
from .llm_defaults import get_default_ollama_model
from .models import Torch, ValleyConfig, CampfireConfig, CommunityMembership, FederationMembership
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
        self._watch_runs: Dict[str, Dict[str, Any]] = {}
        self._watch_learnings: Dict[str, Dict[str, Any]] = {}
        
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
                from .llm_service import AIInferenceService, get_llm_timeout_seconds
                registry = VALIServiceRegistry()
                self.vali_coordinator = VALICoordinator(
                    mcp_broker=self.mcp_broker,
                    registry=registry,
                    federation_manager=self.federation_manager,
                    valley_name=self.name
                )
                try:
                    await asyncio.wait_for(self.vali_coordinator.start(), timeout=6)
                    await self.vali_coordinator.register_service(
                        AIInferenceService(
                            default_ollama_host=os.getenv("OLLAMA_HOST", "http://host.docker.internal:11434"),
                            default_timeout_seconds=get_llm_timeout_seconds(),
                        )
                    )
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
                model = llm_config.get('model', get_default_ollama_model())

                if provider == "openrouter":
                    from .llm_campfire import create_openrouter_campfire
                    api_key = llm_config.get('api_key') or os.getenv('OPENROUTER_API_KEY') or 'demo_key_placeholder'
                    campfire = create_openrouter_campfire(
                        campfire_config,
                        self.mcp_broker,
                        vali_coordinator=self.vali_coordinator,
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
                        vali_coordinator=self.vali_coordinator,
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
                    model = llm_cfg.get("model") or get_default_ollama_model()
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

    def _extract_torch_response_text(self, resp: Optional['Torch']) -> Optional[str]:
        if resp is None:
            return None
        try:
            data = getattr(resp, "data", None)
            if isinstance(data, dict):
                text = (data.get("llm_response") or data.get("text") or "").strip()
                return text or None
        except Exception:
            pass
        return None

    def _extract_first_json_object(self, text: str) -> Optional[Dict[str, Any]]:
        if not text or not isinstance(text, str):
            return None
        s = text.strip()
        if not s:
            return None
        try:
            parsed = json.loads(s)
            return parsed if isinstance(parsed, dict) else None
        except Exception:
            pass
        start = s.find("{")
        end = s.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        try:
            parsed = json.loads(s[start : end + 1])
            return parsed if isinstance(parsed, dict) else None
        except Exception:
            return None

    def _campfire_config_dict(self, campfire_name: str) -> Dict[str, Any]:
        cf = (self.campfires or {}).get(campfire_name)
        if not cf:
            return {}
        cfg = getattr(cf, "config", None)
        if isinstance(cfg, CampfireConfig):
            return cfg.config or {}
        if isinstance(cfg, dict):
            inner = cfg.get("config")
            return inner if isinstance(inner, dict) else cfg
        return {}

    def _watch_settings_for(self, campfire_name: str) -> Dict[str, Any]:
        raw = self._campfire_config_dict(campfire_name)
        behavior = raw.get("behavior") if isinstance(raw.get("behavior"), dict) else {}
        watch = behavior.get("watch") if isinstance(behavior.get("watch"), dict) else {}
        settings = {
            "enabled": True,
            "round_order": ["discover", "plan", "execute", "verify", "improve"],
            "max_retries": 2,
            "default_fail_reroute": "plan",
            "save_trace": True,
            "save_learning": True,
        }
        if isinstance(watch, dict):
            settings.update(watch)
        try:
            settings["max_retries"] = max(0, int(settings.get("max_retries") or 0))
        except Exception:
            settings["max_retries"] = 2
        order = settings.get("round_order")
        if not isinstance(order, list) or not order:
            settings["round_order"] = ["discover", "plan", "execute", "verify", "improve"]
        return settings

    def _is_watch_generated_torch(self, torch: 'Torch') -> bool:
        try:
            metadata = getattr(torch, "metadata", None)
            if isinstance(metadata, dict) and metadata.get("watch_generated"):
                return True
        except Exception:
            pass
        claim = str(getattr(torch, "claim", "") or "").strip().lower()
        return claim.startswith("watch_")

    def _watch_enabled_for_torch(self, campfire_name: str, torch: 'Torch') -> bool:
        if not campfire_name or campfire_name not in (self.campfires or {}):
            return False
        if str(campfire_name).endswith(" Auditor"):
            return False
        if self._is_watch_generated_torch(torch):
            return False
        claim = str(getattr(torch, "claim", "") or "").strip().lower()
        if claim in {"round_chain", "workflow_step", "service_response"}:
            return False
        try:
            metadata = getattr(torch, "metadata", None)
            if isinstance(metadata, dict) and metadata.get("watch_bypass"):
                return False
        except Exception:
            pass
        settings = self._watch_settings_for(campfire_name)
        return bool(settings.get("enabled", True))

    def _available_watch_campers(self, campfire_name: str) -> List[str]:
        available: List[str] = []
        if campfire_name in self.campfires:
            available.append(campfire_name)
        auditor_name = f"{campfire_name} Auditor"
        if auditor_name in self.campfires:
            available.append(auditor_name)
        wf = self.get_workflow(campfire_name) or {}
        for step in (wf.get("steps") if isinstance(wf, dict) else []) or []:
            if not isinstance(step, dict):
                continue
            camper = str(step.get("camper") or "").strip()
            if camper and camper in self.campfires and camper not in available:
                available.append(camper)
        return available

    def _is_watch_auditor_camper(self, camper_name: str) -> bool:
        lower_name = str(camper_name or "").strip().lower()
        return lower_name == "auditor" or lower_name.endswith(" auditor")

    def _watch_camper_profile_text(self, camper_name: str) -> str:
        campfire = self.campfires.get(camper_name)
        config = getattr(campfire, "config", None)
        if config is None and hasattr(campfire, "get_config"):
            try:
                config = campfire.get_config()
            except Exception:
                config = None

        parts: List[str] = [str(camper_name or "").strip()]

        def add_value(value: Any) -> None:
            if isinstance(value, str):
                text = value.strip()
                if text:
                    parts.append(text)
            elif isinstance(value, list):
                for item in value:
                    add_value(item)
            elif isinstance(value, dict):
                for key in (
                    "role",
                    "description",
                    "specialty",
                    "specialization",
                    "type",
                    "role_tags",
                    "capabilities",
                    "channels",
                    "tags",
                ):
                    add_value(value.get(key))

        if isinstance(config, dict):
            add_value(config)
        elif config is not None:
            for attr in ("name", "type", "description", "channels", "behavior"):
                add_value(getattr(config, attr, None))
            add_value(getattr(config, "config", None))

        return " ".join(parts).lower()

    def _preferred_watch_specialist_campers(self, campfire_name: str) -> List[str]:
        available = self._available_watch_campers(campfire_name)
        workflow = self.get_workflow(campfire_name) or {}
        workflow_order: List[str] = []
        for step in (workflow.get("steps") if isinstance(workflow, dict) else []) or []:
            if not isinstance(step, dict):
                continue
            camper = str(step.get("camper") or "").strip()
            if (
                camper
                and camper in self.campfires
                and camper not in workflow_order
                and not self._is_watch_auditor_camper(camper)
            ):
                workflow_order.append(camper)

        learning_bucket = self._watch_learnings.get(campfire_name) if isinstance(self._watch_learnings, dict) else {}
        camper_effectiveness = (
            learning_bucket.get("camper_effectiveness")
            if isinstance(learning_bucket, dict) and isinstance(learning_bucket.get("camper_effectiveness"), dict)
            else {}
        )
        specialization_keywords = (
            "backend",
            "frontend",
            "testing",
            "devops",
            "research",
            "researcher",
            "specialist",
            "developer",
            "engineer",
            "strategist",
            "decomposer",
            "validator",
            "sanitizer",
            "mcp",
            "design",
            "ux",
        )

        ranked: List[Tuple[int, int, str]] = []
        for index, camper_name in enumerate(available):
            if self._is_watch_auditor_camper(camper_name) or camper_name == campfire_name:
                continue
            score = 0
            score += 25
            if camper_name in workflow_order:
                score += 50 - min(20, workflow_order.index(camper_name) * 5)
            stats = camper_effectiveness.get(camper_name) if isinstance(camper_effectiveness, dict) else {}
            if isinstance(stats, dict):
                score += int(stats.get("helpful") or 0) * 6
                score -= int(stats.get("harmful") or 0) * 8
            profile = self._watch_camper_profile_text(camper_name)
            if any(keyword in profile for keyword in specialization_keywords):
                score += 12
            ranked.append((-score, index, camper_name))

        ranked.sort()
        ordered: List[str] = []
        for _, _, camper_name in ranked:
            if camper_name not in ordered:
                ordered.append(camper_name)
        return ordered

    def _normalize_watch_campers(
        self,
        campfire_name: str,
        campers: Any,
        default: Optional[List[str]] = None,
    ) -> List[str]:
        available = set(self._available_watch_campers(campfire_name))
        out: List[str] = []
        for raw in campers or []:
            name = str(raw or "").strip()
            if not name or name not in available or name in out:
                continue
            out.append(name)
        if out:
            return out
        fallback = default or [campfire_name]
        normalized: List[str] = []
        for raw in fallback:
            name = str(raw or "").strip()
            if name and name in self.campfires and name not in normalized:
                normalized.append(name)
        return normalized or ([campfire_name] if campfire_name in self.campfires else [])

    def _strict_watch_campers(self, campfire_name: str, campers: Any) -> List[str]:
        available = set(self._available_watch_campers(campfire_name))
        out: List[str] = []
        for raw in campers or []:
            name = str(raw or "").strip()
            if not name or name not in available or name in out:
                continue
            out.append(name)
        return out

    def _is_authoritative_watch_plan_usable(self, campfire_name: str, plan: Optional[Dict[str, Any]]) -> Tuple[bool, str]:
        if not isinstance(plan, dict):
            return False, "planner_response_not_json"
        rounds = plan.get("rounds")
        if not isinstance(rounds, dict):
            return False, "planner_missing_rounds"
        for stage in ("discover", "plan", "execute", "verify", "improve"):
            spec = rounds.get(stage)
            if not isinstance(spec, dict):
                return False, f"planner_missing_{stage}_round"
            campers = self._strict_watch_campers(campfire_name, spec.get("campers"))
            if not campers:
                return False, f"planner_missing_{stage}_campers"
            if stage == "execute":
                steps = []
                for raw in spec.get("steps") or []:
                    if not isinstance(raw, dict):
                        continue
                    camper = str(raw.get("camper") or "").strip()
                    task = str(raw.get("task") or "").strip()
                    if camper and task and camper in self.campfires:
                        steps.append({"camper": camper, "task": task})
                if not steps:
                    return False, "planner_missing_execute_steps"
        return True, ""

    def _default_watch_plan(self, campfire_name: str) -> Dict[str, Any]:
        auditor_name = f"{campfire_name} Auditor"
        workflow = self.get_workflow(campfire_name) or {}
        workflow_steps = []
        for raw in (workflow.get("steps") if isinstance(workflow, dict) else []) or []:
            if not isinstance(raw, dict):
                continue
            camper = str(raw.get("camper") or "").strip()
            task = str(raw.get("task") or "").strip()
            if camper and task and camper in self.campfires:
                workflow_steps.append({"camper": camper, "task": task})
        preferred_specialists = self._preferred_watch_specialist_campers(campfire_name)
        execute_steps = workflow_steps or [
            {
                "camper": preferred_specialists[0] if preferred_specialists else campfire_name,
                "task": "Answer the torch request using the discovered context and provide a complete user-facing result.",
            }
        ]
        execute_campers = []
        for step in execute_steps:
            camper = str(step.get("camper") or "").strip()
            if camper and not self._is_watch_auditor_camper(camper) and camper not in execute_campers:
                execute_campers.append(camper)
        for camper in preferred_specialists:
            if camper not in execute_campers:
                execute_campers.append(camper)
        planner = auditor_name if auditor_name in self.campfires else campfire_name
        discover_default = preferred_specialists[:2] or execute_campers[:2] or [campfire_name]
        return {
            "rounds": {
                "discover": {
                    "goal": "Gather relevant context and source material for this torch.",
                    "campers": self._normalize_watch_campers(campfire_name, discover_default, discover_default or [campfire_name]),
                },
                "plan": {
                    "goal": "Choose the campers and tasks needed for this torch.",
                    "campers": self._normalize_watch_campers(campfire_name, [planner], [campfire_name]),
                },
                "execute": {
                    "goal": "Carry out the work and produce a candidate final result.",
                    "campers": self._normalize_watch_campers(campfire_name, execute_campers, [campfire_name]),
                    "steps": execute_steps,
                },
                "verify": {
                    "goal": "Check the result and decide whether to ship or reroute.",
                    "campers": self._normalize_watch_campers(campfire_name, [planner], [campfire_name]),
                    "pass_criteria": [
                        "The result answers the torch request.",
                        "Important context is included.",
                        "The output is ready to send to the requester.",
                    ],
                },
                "improve": {
                    "goal": "Capture learning signals that improve future watch runs for similar torches.",
                    "campers": self._normalize_watch_campers(campfire_name, [planner], [campfire_name]),
                    "focus_areas": [
                        "camper selection",
                        "task wording",
                        "reroute policy",
                        "workflow ordering",
                    ],
                },
            },
            "failure_policy": {
                "default_reroute_to": "plan",
                "rules": {
                    "missing_context": "discover",
                    "bad_plan": "plan",
                    "weak_result": "execute",
                },
            },
        }

    def _normalize_watch_plan(self, campfire_name: str, plan: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        default_plan = self._default_watch_plan(campfire_name)
        usable, reason = self._is_authoritative_watch_plan_usable(campfire_name, plan)
        if not usable:
            normalized = dict(default_plan)
            normalized["_planner_source"] = "fallback"
            normalized["_planner_fallback_reason"] = reason or "planner_unusable"
            return normalized
        rounds = plan.get("rounds") if isinstance(plan, dict) and isinstance(plan.get("rounds"), dict) else {}
        failure_policy = plan.get("failure_policy") if isinstance(plan, dict) and isinstance(plan.get("failure_policy"), dict) else {}
        normalized = {"rounds": {}, "failure_policy": dict(default_plan["failure_policy"])}
        normalized["failure_policy"].update(failure_policy or {})
        for stage in ("discover", "plan", "execute", "verify", "improve"):
            spec = rounds.get(stage) if isinstance(rounds.get(stage), dict) else {}
            default_stage = dict(default_plan["rounds"][stage])
            current = {"goal": str(spec.get("goal") or default_stage.get("goal") or "").strip()}
            current["campers"] = self._strict_watch_campers(campfire_name, spec.get("campers"))
            if stage == "execute":
                steps = []
                for raw in spec.get("steps") or []:
                    if not isinstance(raw, dict):
                        continue
                    camper = str(raw.get("camper") or "").strip()
                    task = str(raw.get("task") or "").strip()
                    if camper and task and camper in self.campfires:
                        steps.append({"camper": camper, "task": task})
                current["steps"] = steps
            if stage == "verify":
                criteria = spec.get("pass_criteria")
                if isinstance(criteria, list):
                    clean = [str(item).strip() for item in criteria if str(item or "").strip()]
                    if clean:
                        current["pass_criteria"] = clean[:8]
                if "pass_criteria" not in current:
                    current["pass_criteria"] = list(default_stage.get("pass_criteria") or [])
            if stage == "improve":
                focus = spec.get("focus_areas")
                if isinstance(focus, list):
                    clean = [str(item).strip() for item in focus if str(item or "").strip()]
                    if clean:
                        current["focus_areas"] = clean[:8]
                if "focus_areas" not in current:
                    current["focus_areas"] = list(default_stage.get("focus_areas") or [])
            normalized["rounds"][stage] = current
        reroute = str(normalized["failure_policy"].get("default_reroute_to") or "").strip().lower()
        if reroute not in {"discover", "plan", "execute"}:
            normalized["failure_policy"]["default_reroute_to"] = "plan"
        rules = normalized["failure_policy"].get("rules")
        if not isinstance(rules, dict):
            normalized["failure_policy"]["rules"] = default_plan["failure_policy"]["rules"]
        return normalized

    async def _request_watch_plan(
        self,
        campfire_name: str,
        torch: 'Torch',
        correlation_id: str,
        discover_context: str = "",
        feedback: str = "",
        retry_count: int = 0,
    ) -> Dict[str, Any]:
        default_plan = self._default_watch_plan(campfire_name)
        auditor_name = f"{campfire_name} Auditor"
        if auditor_name not in self.campfires:
            default_plan["_planner"] = auditor_name
            default_plan["_planner_source"] = "fallback"
            default_plan["_planner_fallback_reason"] = "auditor_missing"
            return default_plan
        available = self._available_watch_campers(campfire_name)
        preferred_specialists = self._preferred_watch_specialist_campers(campfire_name)
        workflow = self.get_workflow(campfire_name) or {}
        workflow_steps = workflow.get("steps") if isinstance(workflow, dict) else []
        prompt = (
            f"You are {auditor_name}. Create a watch plan for the campfire '{campfire_name}'.\n\n"
            "This is orchestration metadata for the runtime, not a user-facing document.\n"
            "Do not answer the user's task directly.\n"
            "Do not ask clarifying questions.\n"
            "Do not describe what you might do.\n"
            "Do not return markdown, code fences, prose, or explanations.\n"
            "Return exactly one JSON object and nothing else.\n\n"
            f"Original torch request:\n{self._torch_text(torch)}\n\n"
            f"Discovered context:\n{discover_context or '(none yet)'}\n\n"
            f"Retry count: {retry_count}\n"
            f"Verifier feedback:\n{feedback or '(none)'}\n\n"
            f"Available campers:\n- " + "\n- ".join(available) + "\n\n"
            f"Preferred non-auditor campers for discover/execute:\n- "
            + ("\n- ".join(preferred_specialists) if preferred_specialists else "(none)")
            + "\n\n"
            f"Existing workflow steps:\n{json.dumps(workflow_steps or [], ensure_ascii=True)}\n\n"
            "Interpret \"watch plan\" to mean the machine-readable watch execution plan.\n"
            "It is not a report, checklist, explanation, or deliverable for the requester.\n"
            "Use the torch request only to decide orchestration: which rounds run, who participates, and what the execute steps do.\n"
            "If the request is ambiguous, still produce the best usable plan instead of asking a question.\n\n"
            "Return ONLY valid JSON with this schema:\n"
            "{"
            "\"rounds\": {"
            "\"discover\": {\"goal\": \"...\", \"campers\": [\"...\"]},"
            "\"plan\": {\"goal\": \"...\", \"campers\": [\"...\"]},"
            "\"execute\": {\"goal\": \"...\", \"campers\": [\"...\"], \"steps\": [{\"camper\": \"...\", \"task\": \"...\"}]},"
            "\"verify\": {\"goal\": \"...\", \"campers\": [\"...\"], \"pass_criteria\": [\"...\"]},"
            "\"improve\": {\"goal\": \"...\", \"campers\": [\"...\"], \"focus_areas\": [\"...\"]}"
            "},"
            "\"failure_policy\": {\"default_reroute_to\": \"discover|plan|execute\", \"rules\": {\"missing_context\": \"discover\", \"bad_plan\": \"plan\", \"weak_result\": \"execute\"}}"
            "}\n"
            "Rules:\n"
            "- Only use camper names from the available campers list.\n"
            "- Every round must include at least one camper.\n"
            "- The execute round must include at least one step.\n"
            "- Prefer the auditor for plan, verify, and improve.\n"
            "- Keep the auditor out of discover and execute unless there is no usable non-auditor option.\n"
            "- For discover and execute, choose preferred non-auditor campers before the parent campfire whenever they are available.\n"
            "- Prefer domain or specialist campers for discover and execute when possible.\n"
            "- Do not invent new campers.\n"
            "- Do not include comments or trailing text outside the JSON object."
        )
        plan_torch = type(torch)(
            claim="watch_plan",
            source_campfire=f"{campfire_name} Watch",
            channel="watch",
            torch_id=f"watch_{uuid.uuid4().hex}",
            sender_valley=self.name,
            target_address=f"valley:{self.name}/{auditor_name}",
            data={"text": prompt, "service_mode": True, "parent": campfire_name},
            signature="watch_placeholder",
            metadata={
                "correlation_id": correlation_id,
                "parent": campfire_name,
                "watch_generated": True,
                "watch_round": "plan",
            },
        )
        resp = await self.campfires[auditor_name].process_torch(plan_torch)
        raw = self._extract_torch_response_text(resp) or ""
        parsed = self._extract_first_json_object(raw)
        normalized = self._normalize_watch_plan(campfire_name, parsed)
        normalized["_planner_raw"] = raw
        normalized["_planner"] = auditor_name
        if not normalized.get("_planner_source"):
            normalized["_planner_source"] = "auditor"
        return normalized

    def _watch_round_prompt(
        self,
        campfire_name: str,
        round_name: str,
        goal: str,
        original_text: str,
        current_input: str,
        prior_rounds: List[Dict[str, Any]],
    ) -> str:
        prior_lines: List[str] = []
        for item in prior_rounds[-6:]:
            if not isinstance(item, dict):
                continue
            label = str(item.get("round") or "").strip()
            summary = str(item.get("summary") or item.get("output") or "").strip()
            if label and summary:
                prior_lines.append(f"{label}:\n{summary}")
        prior_text = "\n\n---\n\n".join(prior_lines) if prior_lines else "(none)"
        return (
            f"You are helping campfire '{campfire_name}' in the '{round_name}' watch round.\n\n"
            f"Round goal:\n{goal}\n\n"
            f"Original torch request:\n{original_text}\n\n"
            f"Current working context:\n{current_input or '(none)'}\n\n"
            f"Prior watch round summaries:\n{prior_text}\n\n"
            "Return a concise, useful contribution for this round only."
        )

    async def _run_watch_round_with_campers(
        self,
        campfire_name: str,
        round_name: str,
        campers: List[str],
        goal: str,
        original_text: str,
        current_input: str,
        correlation_id: str,
        watch_id: str,
        prior_rounds: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        outputs: List[Dict[str, Any]] = []
        prompt = self._watch_round_prompt(campfire_name, round_name, goal, original_text, current_input, prior_rounds)
        for camper in campers:
            cf = self.campfires.get(camper)
            if not cf:
                continue
            round_torch = Torch(
                claim=f"watch_{round_name}",
                source_campfire=f"{campfire_name} Watch",
                channel="watch",
                torch_id=f"watch_{uuid.uuid4().hex}",
                sender_valley=self.name,
                target_address=f"valley:{self.name}/{camper}",
                data={"text": prompt, "service_mode": True, "parent": campfire_name, "watch_round": round_name},
                signature="watch_placeholder",
                metadata={
                    "correlation_id": correlation_id,
                    "parent": campfire_name,
                    "watch_generated": True,
                    "watch_run_id": watch_id,
                    "watch_round": round_name,
                },
            )
            resp = await cf.process_torch(round_torch)
            text = self._extract_torch_response_text(resp)
            outputs.append({"camper": camper, "ok": bool(text), "text": text or ""})
        summary = "\n\n---\n\n".join(
            [f"{item['camper']}:\n{item['text']}" for item in outputs if item.get("text")]
        ).strip()
        return {
            "round": round_name,
            "status": "completed" if summary else "empty",
            "campers_used": list(campers),
            "summary": summary,
            "details": outputs,
        }

    async def _run_watch_execute_round(
        self,
        campfire_name: str,
        torch: 'Torch',
        execute_steps: List[Dict[str, Any]],
        discover_summary: str,
        correlation_id: str,
        watch_id: str,
    ) -> Dict[str, Any]:
        original_text = self._torch_text(torch)
        execute_input = original_text
        if discover_summary:
            execute_input = (
                f"Original request:\n{original_text}\n\n"
                f"Discovered context:\n{discover_summary}"
            )
        execute_torch = Torch(
            claim="service_request",
            source_campfire=f"{campfire_name} Watch",
            channel="service",
            torch_id=f"watch_{uuid.uuid4().hex}",
            sender_valley=self.name,
            target_address=f"valley:{self.name}/{campfire_name}",
            data={"text": execute_input, "service_mode": True, "watch_round": "execute"},
            signature="watch_placeholder",
            metadata={
                "correlation_id": correlation_id,
                "parent": campfire_name,
                "watch_generated": True,
                "watch_run_id": watch_id,
                "watch_round": "execute",
                "workflow_override_steps": execute_steps,
            },
        )
        resp = await self.process_service_call(campfire_name, execute_torch)
        text = self._extract_torch_response_text(resp) or ""
        return {
            "round": "execute",
            "status": "completed" if text else "empty",
            "campers_used": [str(step.get("camper") or "").strip() for step in execute_steps if str(step.get("camper") or "").strip()],
            "summary": text,
            "details": getattr(resp, "data", None),
        }

    async def _run_watch_verify_round(
        self,
        campfire_name: str,
        torch: 'Torch',
        verify_spec: Dict[str, Any],
        discover_summary: str,
        execute_summary: str,
        correlation_id: str,
        watch_id: str,
        prior_rounds: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        campers = list(verify_spec.get("campers") or [])
        criteria = list(verify_spec.get("pass_criteria") or [])
        original_text = self._torch_text(torch)
        if not campers:
            return {
                "round": "verify",
                "status": "completed",
                "campers_used": [],
                "summary": execute_summary,
                "decision": {
                    "pass": bool(execute_summary),
                    "reason": "weak_result" if not execute_summary else "pass",
                    "feedback": "" if execute_summary else "The execute round returned no response.",
                    "reroute_to": "execute",
                },
            }
        verifier = campers[0]
        cf = self.campfires.get(verifier)
        if not cf:
            return {
                "round": "verify",
                "status": "empty",
                "campers_used": campers,
                "summary": "",
                "decision": {"pass": bool(execute_summary), "reason": "pass" if execute_summary else "weak_result", "feedback": "", "reroute_to": "execute"},
            }
        prior_lines = []
        for item in prior_rounds[-6:]:
            if not isinstance(item, dict):
                continue
            label = str(item.get("round") or "").strip()
            summary = str(item.get("summary") or "").strip()
            if label and summary:
                prior_lines.append(f"{label}:\n{summary}")
        prompt = (
            f"You are verifying a watch run for campfire '{campfire_name}'.\n\n"
            f"Original torch request:\n{original_text}\n\n"
            f"Discovered context:\n{discover_summary or '(none)'}\n\n"
            f"Execute round result:\n{execute_summary or '(none)'}\n\n"
            f"Pass criteria:\n- " + "\n- ".join(criteria or ["Result answers the request", "Result is ready to ship"]) + "\n\n"
            f"Prior round summaries:\n{chr(10).join(prior_lines) if prior_lines else '(none)'}\n\n"
            "Return ONLY valid JSON with keys: pass (boolean), reason (string), feedback (string), reroute_to (discover|plan|execute)."
        )
        verify_torch = Torch(
            claim="watch_verify",
            source_campfire=f"{campfire_name} Watch",
            channel="watch",
            torch_id=f"watch_{uuid.uuid4().hex}",
            sender_valley=self.name,
            target_address=f"valley:{self.name}/{verifier}",
            data={"text": prompt, "service_mode": True, "parent": campfire_name},
            signature="watch_placeholder",
            metadata={
                "correlation_id": correlation_id,
                "parent": campfire_name,
                "watch_generated": True,
                "watch_run_id": watch_id,
                "watch_round": "verify",
            },
        )
        resp = await cf.process_torch(verify_torch)
        raw = self._extract_torch_response_text(resp) or ""
        parsed = self._extract_first_json_object(raw) or {}
        decision = {
            "pass": bool(parsed.get("pass")) if isinstance(parsed.get("pass"), bool) else bool(execute_summary),
            "reason": str(parsed.get("reason") or ("pass" if execute_summary else "weak_result")).strip(),
            "feedback": str(parsed.get("feedback") or "").strip(),
            "reroute_to": str(parsed.get("reroute_to") or "execute").strip().lower(),
        }
        if decision["reroute_to"] not in {"discover", "plan", "execute"}:
            decision["reroute_to"] = "execute"
        return {
            "round": "verify",
            "status": "completed",
            "campers_used": campers,
            "summary": raw or decision["feedback"] or ("pass" if decision["pass"] else "fail"),
            "decision": decision,
        }

    def _heuristic_watch_learning(
        self,
        campfire_name: str,
        verify_result: Dict[str, Any],
        execute_result: Dict[str, Any],
        retry_count: int,
        history: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        decision = verify_result.get("decision") if isinstance(verify_result.get("decision"), dict) else {}
        passed = bool(decision.get("pass"))
        execute_summary = str(execute_result.get("summary") or "").strip()
        strengths: List[str] = []
        weaknesses: List[str] = []
        recommendations: List[str] = []
        if passed:
            strengths.append("The watch completed with a verifier-approved result.")
        else:
            weaknesses.append("The watch ended without a verifier-approved result.")
        if retry_count:
            weaknesses.append(f"The watch needed {retry_count} retry cycle(s) before finishing.")
            recommendations.append("Tighten plan quality and reroute hints for similar torches.")
        else:
            strengths.append("The watch completed without retries.")
        if execute_summary:
            strengths.append("The execute round returned a non-empty final candidate.")
        else:
            weaknesses.append("The execute round returned an empty result.")
            recommendations.append("Add stronger execute tasks or richer discovered context.")
        feedback = str(decision.get("feedback") or "").strip()
        if feedback:
            recommendations.append(feedback)
        camper_feedback: List[Dict[str, Any]] = []
        for item in history:
            if not isinstance(item, dict):
                continue
            round_name = str(item.get("round") or "").strip()
            if not round_name or round_name == "improve":
                continue
            status = str(item.get("status") or "").strip().lower()
            for camper in item.get("campers_used") or []:
                name = str(camper or "").strip()
                if not name:
                    continue
                rating = "helpful" if status == "completed" else "neutral"
                note = f"Contributed during the {round_name} round."
                camper_feedback.append({"campfire": name, "rating": rating, "notes": note})
        if not recommendations:
            recommendations.append("Keep the current watch shape, but keep monitoring verify feedback trends.")
        return {
            "outcome_summary": (
                f"Watch {'passed' if passed else 'failed'} after {retry_count} retr{'y' if retry_count == 1 else 'ies'}."
            ),
            "effectiveness": {
                "task_fit": 4 if passed else 2,
                "quality": 4 if passed and execute_summary else 2,
                "efficiency": 4 if retry_count == 0 else max(1, 4 - retry_count),
                "coordination": 4 if passed else 2,
            },
            "strengths": strengths[:6],
            "weaknesses": weaknesses[:6],
            "recommendations": recommendations[:8],
            "camper_feedback": camper_feedback[:12],
            "learned_policy": {
                "prefer_campers": [],
                "avoid_campers": [],
                "reroute_hints": {},
                "workflow_suggestions": recommendations[:4],
            },
        }

    def _normalize_watch_learning(
        self,
        campfire_name: str,
        learning: Optional[Dict[str, Any]],
        verify_result: Dict[str, Any],
        execute_result: Dict[str, Any],
        retry_count: int,
        history: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        normalized = self._heuristic_watch_learning(campfire_name, verify_result, execute_result, retry_count, history)
        if not isinstance(learning, dict):
            return normalized
        summary = str(learning.get("outcome_summary") or "").strip()
        if summary:
            normalized["outcome_summary"] = summary
        effectiveness = learning.get("effectiveness")
        if isinstance(effectiveness, dict):
            clean_scores: Dict[str, int] = {}
            for key in ("task_fit", "quality", "efficiency", "coordination"):
                try:
                    score = int(effectiveness.get(key))
                except Exception:
                    continue
                clean_scores[key] = max(1, min(5, score))
            normalized["effectiveness"].update(clean_scores)
        for key in ("strengths", "weaknesses", "recommendations"):
            value = learning.get(key)
            if isinstance(value, list):
                clean = [str(item).strip() for item in value if str(item or "").strip()]
                if clean:
                    normalized[key] = clean[:8]
        available = set(self._available_watch_campers(campfire_name))
        camper_feedback = []
        for raw in learning.get("camper_feedback") or []:
            if not isinstance(raw, dict):
                continue
            name = str(raw.get("campfire") or raw.get("camper") or "").strip()
            if not name or (available and name not in available):
                continue
            rating = str(raw.get("rating") or "").strip().lower()
            if rating not in {"helpful", "neutral", "harmful"}:
                rating = "neutral"
            notes = str(raw.get("notes") or "").strip()
            camper_feedback.append({"campfire": name, "rating": rating, "notes": notes})
        if camper_feedback:
            normalized["camper_feedback"] = camper_feedback[:12]
        learned_policy = learning.get("learned_policy")
        if isinstance(learned_policy, dict):
            policy = dict(normalized["learned_policy"])
            for field in ("prefer_campers", "avoid_campers"):
                clean_names = []
                for raw in learned_policy.get(field) or []:
                    name = str(raw or "").strip()
                    if not name or (available and name not in available) or name in clean_names:
                        continue
                    clean_names.append(name)
                if clean_names:
                    policy[field] = clean_names[:8]
            hints = {}
            raw_hints = learned_policy.get("reroute_hints")
            if isinstance(raw_hints, dict):
                for key, value in raw_hints.items():
                    reason = str(key or "").strip()
                    stage = str(value or "").strip().lower()
                    if reason and stage in {"discover", "plan", "execute"}:
                        hints[reason] = stage
            if hints:
                policy["reroute_hints"] = hints
            suggestions = [str(item).strip() for item in learned_policy.get("workflow_suggestions") or [] if str(item or "").strip()]
            if suggestions:
                policy["workflow_suggestions"] = suggestions[:8]
            normalized["learned_policy"] = policy
        return normalized

    async def _run_watch_improve_round(
        self,
        campfire_name: str,
        torch: 'Torch',
        improve_spec: Dict[str, Any],
        verify_result: Dict[str, Any],
        execute_result: Dict[str, Any],
        correlation_id: str,
        watch_id: str,
        prior_rounds: List[Dict[str, Any]],
        retry_count: int,
    ) -> Dict[str, Any]:
        campers = list(improve_spec.get("campers") or [])
        focus_areas = list(improve_spec.get("focus_areas") or [])
        heuristic = self._heuristic_watch_learning(campfire_name, verify_result, execute_result, retry_count, prior_rounds)
        original_text = self._torch_text(torch)
        decision = verify_result.get("decision") if isinstance(verify_result.get("decision"), dict) else {}
        prior_lines = []
        for item in prior_rounds[-8:]:
            if not isinstance(item, dict):
                continue
            label = str(item.get("round") or "").strip()
            summary = str(item.get("summary") or "").strip()
            if label and summary:
                prior_lines.append(f"{label}:\n{summary}")
        prompt = (
            f"You are capturing self-improvement signals for campfire '{campfire_name}'.\n\n"
            f"Original torch request:\n{original_text}\n\n"
            f"Retry count: {retry_count}\n\n"
            f"Verify decision:\n{json.dumps(decision or {}, ensure_ascii=True)}\n\n"
            f"Execute result:\n{str(execute_result.get('summary') or '(none)')}\n\n"
            f"Focus areas:\n- " + "\n- ".join(focus_areas or ["camper selection", "task wording", "reroute policy", "workflow ordering"]) + "\n\n"
            f"Prior watch round summaries:\n{chr(10).join(prior_lines) if prior_lines else '(none)'}\n\n"
            "Return ONLY valid JSON with keys: outcome_summary (string), effectiveness "
            "({task_fit:1-5, quality:1-5, efficiency:1-5, coordination:1-5}), strengths "
            "([string]), weaknesses ([string]), recommendations ([string]), camper_feedback "
            "([{campfire:string, rating:helpful|neutral|harmful, notes:string}]), learned_policy "
            "({prefer_campers:[string], avoid_campers:[string], reroute_hints:{reason:stage}, "
            "workflow_suggestions:[string]}). Do not apply changes; recommend them only."
        )
        raw = ""
        if campers:
            improver = str(campers[0] or "").strip()
            cf = self.campfires.get(improver)
            if cf is not None:
                improve_torch = Torch(
                    claim="watch_improve",
                    source_campfire=f"{campfire_name} Watch",
                    channel="watch",
                    torch_id=f"watch_{uuid.uuid4().hex}",
                    sender_valley=self.name,
                    target_address=f"valley:{self.name}/{improver}",
                    data={"text": prompt, "service_mode": True, "parent": campfire_name},
                    signature="watch_placeholder",
                    metadata={
                        "correlation_id": correlation_id,
                        "parent": campfire_name,
                        "watch_generated": True,
                        "watch_run_id": watch_id,
                        "watch_round": "improve",
                    },
                )
                resp = await cf.process_torch(improve_torch)
                raw = self._extract_torch_response_text(resp) or ""
        parsed = self._extract_first_json_object(raw)
        normalized = self._normalize_watch_learning(
            campfire_name,
            parsed,
            verify_result,
            execute_result,
            retry_count,
            prior_rounds,
        )
        return {
            "round": "improve",
            "status": "completed" if (raw or normalized) else "empty",
            "campers_used": campers[:1],
            "summary": raw or normalized.get("outcome_summary") or "Improvement signals captured.",
            "learning": normalized,
        }

    def _record_watch_learning(
        self,
        campfire_name: str,
        watch_id: str,
        correlation_id: str,
        learning: Dict[str, Any],
        passed: bool,
        retry_count: int,
    ) -> Dict[str, Any]:
        bucket = self._watch_learnings.setdefault(
            campfire_name,
            {
                "campfire": campfire_name,
                "runs": 0,
                "passes": 0,
                "failures": 0,
                "total_retries": 0,
                "effectiveness_totals": {"task_fit": 0, "quality": 0, "efficiency": 0, "coordination": 0},
                "average_effectiveness": {"task_fit": 0.0, "quality": 0.0, "efficiency": 0.0, "coordination": 0.0},
                "camper_effectiveness": {},
                "recommendation_counts": {},
                "recent_runs": [],
            },
        )
        bucket["runs"] = int(bucket.get("runs") or 0) + 1
        bucket["passes"] = int(bucket.get("passes") or 0) + (1 if passed else 0)
        bucket["failures"] = int(bucket.get("failures") or 0) + (0 if passed else 1)
        bucket["total_retries"] = int(bucket.get("total_retries") or 0) + max(0, retry_count)
        totals = bucket.get("effectiveness_totals") if isinstance(bucket.get("effectiveness_totals"), dict) else {}
        averages = bucket.get("average_effectiveness") if isinstance(bucket.get("average_effectiveness"), dict) else {}
        scores = learning.get("effectiveness") if isinstance(learning.get("effectiveness"), dict) else {}
        for key in ("task_fit", "quality", "efficiency", "coordination"):
            try:
                score = int(scores.get(key))
            except Exception:
                score = 0
            totals[key] = int(totals.get(key) or 0) + max(0, score)
            averages[key] = round(float(totals[key]) / max(1, int(bucket["runs"])), 2)
        bucket["effectiveness_totals"] = totals
        bucket["average_effectiveness"] = averages
        recommendation_counts = bucket.get("recommendation_counts") if isinstance(bucket.get("recommendation_counts"), dict) else {}
        for item in learning.get("recommendations") or []:
            rec = str(item or "").strip()
            if not rec:
                continue
            recommendation_counts[rec] = int(recommendation_counts.get(rec) or 0) + 1
        bucket["recommendation_counts"] = recommendation_counts
        camper_effectiveness = bucket.get("camper_effectiveness") if isinstance(bucket.get("camper_effectiveness"), dict) else {}
        for entry in learning.get("camper_feedback") or []:
            if not isinstance(entry, dict):
                continue
            camper = str(entry.get("campfire") or "").strip()
            if not camper:
                continue
            stats = camper_effectiveness.setdefault(camper, {"helpful": 0, "neutral": 0, "harmful": 0, "notes": []})
            rating = str(entry.get("rating") or "neutral").strip().lower()
            if rating not in {"helpful", "neutral", "harmful"}:
                rating = "neutral"
            stats[rating] = int(stats.get(rating) or 0) + 1
            notes = stats.get("notes") if isinstance(stats.get("notes"), list) else []
            note = str(entry.get("notes") or "").strip()
            if note:
                notes.append(note)
            stats["notes"] = notes[-5:]
        bucket["camper_effectiveness"] = camper_effectiveness
        recent_runs = bucket.get("recent_runs") if isinstance(bucket.get("recent_runs"), list) else []
        recent_runs.append(
            {
                "watch_id": watch_id,
                "correlation_id": correlation_id,
                "passed": passed,
                "retry_count": retry_count,
                "outcome_summary": str(learning.get("outcome_summary") or "").strip(),
                "recommendations": list(learning.get("recommendations") or [])[:4],
            }
        )
        bucket["recent_runs"] = recent_runs[-20:]
        return {
            "runs": bucket["runs"],
            "passes": bucket["passes"],
            "failures": bucket["failures"],
            "average_effectiveness": dict(bucket["average_effectiveness"]),
            "recent_recommendations": list((learning.get("recommendations") or []))[:4],
        }

    def _watch_reports_dir(self) -> Path:
        reports_dir = Path(os.getenv("REPORTS_DIR") or "./reports")
        reports_dir.mkdir(parents=True, exist_ok=True)
        return reports_dir

    def _watch_report_path(self, watch_id: str) -> Path:
        safe_id = re.sub(r"[^a-zA-Z0-9_\-]+", "_", str(watch_id or "").strip()) or "watch"
        return self._watch_reports_dir() / f"{safe_id}.html"

    def _watch_report_json(self, value: Any) -> str:
        try:
            return json.dumps(value, ensure_ascii=False, indent=2)
        except Exception:
            return str(value)

    def get_watch_run(self, watch_id: str) -> Optional[Dict[str, Any]]:
        run = self._watch_runs.get(str(watch_id or "").strip())
        return dict(run) if isinstance(run, dict) else None

    def render_watch_report_html(self, watch_id: str) -> Optional[str]:
        run = self._watch_runs.get(str(watch_id or "").strip())
        if not isinstance(run, dict):
            return None
        watch = run.get("watch") if isinstance(run.get("watch"), dict) else {}
        history = watch.get("history") if isinstance(watch.get("history"), list) else []
        learning = watch.get("learning") if isinstance(watch.get("learning"), dict) else {}
        learning_summary = watch.get("learning_summary") if isinstance(watch.get("learning_summary"), dict) else {}
        esc = html.escape

        round_cards: List[str] = []
        for idx, item in enumerate(history, start=1):
            if not isinstance(item, dict):
                continue
            round_name = str(item.get("round") or f"round_{idx}").strip()
            status = str(item.get("status") or "").strip() or "unknown"
            campers = [str(raw).strip() for raw in (item.get("campers_used") or []) if str(raw or "").strip()]
            summary = str(item.get("summary") or "").strip()
            details = item.get("details")
            decision = item.get("decision") if isinstance(item.get("decision"), dict) else {}
            learning_block = item.get("learning") if isinstance(item.get("learning"), dict) else {}
            detail_html = ""
            if isinstance(details, list):
                rows = []
                for raw in details:
                    if not isinstance(raw, dict):
                        continue
                    rows.append(
                        "<tr>"
                        f"<td>{esc(str(raw.get('camper') or ''))}</td>"
                        f"<td>{esc(str(raw.get('ok') or ''))}</td>"
                        f"<td><pre>{esc(str(raw.get('text') or ''))}</pre></td>"
                        "</tr>"
                    )
                if rows:
                    detail_html = (
                        "<h4>Round Contributions</h4>"
                        "<table><thead><tr><th>Camper</th><th>OK</th><th>Output</th></tr></thead>"
                        f"<tbody>{''.join(rows)}</tbody></table>"
                    )
            elif details:
                detail_html = "<h4>Round Details</h4><pre>" + esc(self._watch_report_json(details)) + "</pre>"
            decision_html = ""
            if decision:
                decision_html = "<h4>Verify Decision</h4><pre>" + esc(self._watch_report_json(decision)) + "</pre>"
            learning_html = ""
            if learning_block:
                learning_html = "<h4>Improve Output</h4><pre>" + esc(self._watch_report_json(learning_block)) + "</pre>"
            round_cards.append(
                "<section class='round-card'>"
                f"<div class='round-head'><span class='round-index'>Round {idx}</span><span class='round-name'>{esc(round_name.title())}</span><span class='round-status status-{esc(status.lower())}'>{esc(status)}</span></div>"
                f"<div class='round-meta'><strong>Participants:</strong> {esc(', '.join(campers) if campers else '(none recorded)')}</div>"
                f"<div class='round-summary'><strong>Summary</strong><pre>{esc(summary or '(no summary)')}</pre></div>"
                f"{detail_html}{decision_html}{learning_html}"
                "</section>"
            )

        recommendations = "".join(
            f"<li>{esc(str(item))}</li>" for item in (learning.get("recommendations") or []) if str(item or "").strip()
        ) or "<li>(none)</li>"
        strengths = "".join(
            f"<li>{esc(str(item))}</li>" for item in (learning.get("strengths") or []) if str(item or "").strip()
        ) or "<li>(none)</li>"
        weaknesses = "".join(
            f"<li>{esc(str(item))}</li>" for item in (learning.get("weaknesses") or []) if str(item or "").strip()
        ) or "<li>(none)</li>"
        camper_feedback_rows = []
        for raw in learning.get("camper_feedback") or []:
            if not isinstance(raw, dict):
                continue
            camper_feedback_rows.append(
                "<tr>"
                f"<td>{esc(str(raw.get('campfire') or ''))}</td>"
                f"<td>{esc(str(raw.get('rating') or ''))}</td>"
                f"<td>{esc(str(raw.get('notes') or ''))}</td>"
                "</tr>"
            )
        camper_feedback_html = (
            "<table><thead><tr><th>Camper</th><th>Rating</th><th>Notes</th></tr></thead>"
            f"<tbody>{''.join(camper_feedback_rows)}</tbody></table>"
            if camper_feedback_rows
            else "<p>(none)</p>"
        )

        html_doc = (
            "<!doctype html><html><head><meta charset='utf-8'>"
            f"<title>Watch Report {esc(str(watch.get('watch_id') or watch_id))}</title>"
            "<style>"
            "body{font-family:Arial,sans-serif;background:#f5f1e8;color:#2d2418;margin:0;padding:24px;line-height:1.45;}"
            ".wrap{max-width:1200px;margin:0 auto;}"
            ".hero,.card,.round-card{background:#fff;border:1px solid #d9c9a8;border-radius:12px;padding:18px 20px;margin-bottom:16px;box-shadow:0 2px 8px rgba(0,0,0,0.05);}"
            ".hero h1{margin:0 0 8px;font-size:28px;}.meta{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px;margin-top:14px;}"
            ".meta div,.grid div{background:#fbf8f0;border:1px solid #eadfc8;border-radius:10px;padding:10px 12px;}"
            ".round-head{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-bottom:10px;}.round-index{font-size:12px;text-transform:uppercase;color:#7d6641;}"
            ".round-name{font-size:20px;font-weight:700;}.round-status{padding:3px 10px;border-radius:999px;font-size:12px;font-weight:700;background:#eee;}"
            ".status-completed{background:#dff2df;color:#1d6b2e;}.status-empty{background:#f8e0e0;color:#8a2d2d;}.status-unknown{background:#ececec;color:#555;}"
            ".grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px;}"
            "pre{white-space:pre-wrap;word-break:break-word;background:#f7f4ee;border:1px solid #e8dcc8;border-radius:10px;padding:12px;overflow:auto;}"
            "table{width:100%;border-collapse:collapse;margin-top:10px;}th,td{border:1px solid #e6d6bd;padding:8px 10px;text-align:left;vertical-align:top;}th{background:#f3ebdc;}"
            "h2,h3,h4{margin:0 0 10px;}ul{margin:8px 0 0 20px;padding:0;}a{color:#7a4d00;text-decoration:none;}"
            "</style></head><body><div class='wrap'>"
            "<section class='hero'>"
            "<h1>Watch Report</h1>"
            f"<p><strong>Campfire:</strong> {esc(str(run.get('campfire') or ''))}</p>"
            f"<p><strong>Final Output:</strong></p><pre>{esc(str(run.get('text') or ''))}</pre>"
            "<div class='meta'>"
            f"<div><strong>Watch ID</strong><br>{esc(str(watch.get('watch_id') or watch_id))}</div>"
            f"<div><strong>Correlation ID</strong><br>{esc(str(run.get('correlation_id') or ''))}</div>"
            f"<div><strong>Torch ID</strong><br>{esc(str(watch.get('torch_id') or ''))}</div>"
            f"<div><strong>Retry Count</strong><br>{esc(str(watch.get('retry_count') if watch.get('retry_count') is not None else 0))}</div>"
            f"<div><strong>Outcome</strong><br>{esc('passed' if bool(run.get('ok')) else 'failed')}</div>"
            f"<div><strong>Rounds Recorded</strong><br>{esc(str(len(history)))}</div>"
            "</div></section>"
            "<section class='card'><h2>Round Overview</h2>"
            + ("".join(round_cards) if round_cards else "<p>No watch rounds were recorded.</p>")
            + "</section>"
            "<section class='card'><h2>Learning Summary</h2><div class='grid'>"
            f"<div><strong>Outcome Summary</strong><pre>{esc(str(learning.get('outcome_summary') or '(none)'))}</pre></div>"
            f"<div><strong>Effectiveness</strong><pre>{esc(self._watch_report_json(learning.get('effectiveness') or {}))}</pre></div>"
            f"<div><strong>Aggregate Learning</strong><pre>{esc(self._watch_report_json(learning_summary or {}))}</pre></div>"
            f"<div><strong>Learned Policy</strong><pre>{esc(self._watch_report_json(learning.get('learned_policy') or {}))}</pre></div>"
            "</div>"
            f"<h3>Strengths</h3><ul>{strengths}</ul>"
            f"<h3>Weaknesses</h3><ul>{weaknesses}</ul>"
            f"<h3>Recommendations</h3><ul>{recommendations}</ul>"
            f"<h3>Camper Feedback</h3>{camper_feedback_html}"
            "</section></div></body></html>"
        )
        return html_doc

    def save_watch_report(self, watch_id: str) -> Optional[str]:
        html_doc = self.render_watch_report_html(watch_id)
        if not html_doc:
            return None
        path = self._watch_report_path(watch_id)
        path.write_text(html_doc, encoding="utf-8")
        return str(path)

    async def _run_watch_for_torch(self, campfire_name: str, torch: 'Torch') -> Optional['Torch']:
        settings = self._watch_settings_for(campfire_name)
        original_text = self._torch_text(torch)
        if not original_text.strip():
            return None
        corr = None
        try:
            if isinstance(getattr(torch, "metadata", None), dict):
                corr = (torch.metadata.get("correlation_id") or "").strip() or None
        except Exception:
            corr = None
        corr = corr or getattr(torch, "torch_id", None) or getattr(torch, "id", None)
        watch_id = f"watch_{uuid.uuid4().hex}"
        max_retries = max(0, int(settings.get("max_retries") or 0))
        retry_count = 0
        reroute_to = "discover"
        verifier_feedback = ""
        discover_result: Dict[str, Any] = {"summary": ""}
        plan_result: Dict[str, Any] = {}
        execute_result: Dict[str, Any] = {"summary": ""}
        history: List[Dict[str, Any]] = []

        while True:
            if reroute_to == "discover":
                plan_result = await self._request_watch_plan(
                    campfire_name,
                    torch,
                    corr,
                    discover_context="",
                    feedback=verifier_feedback,
                    retry_count=retry_count,
                )
                discover_spec = plan_result.get("rounds", {}).get("discover", {})
                discover_result = await self._run_watch_round_with_campers(
                    campfire_name,
                    "discover",
                    list(discover_spec.get("campers") or [campfire_name]),
                    str(discover_spec.get("goal") or "Gather context."),
                    original_text,
                    original_text,
                    corr,
                    watch_id,
                    history,
                )
                if not discover_result.get("summary"):
                    discover_result["summary"] = original_text
                history.append(dict(discover_result))
                reroute_to = "plan"

            if reroute_to == "plan":
                plan_result = await self._request_watch_plan(
                    campfire_name,
                    torch,
                    corr,
                    discover_context=str(discover_result.get("summary") or original_text),
                    feedback=verifier_feedback,
                    retry_count=retry_count,
                )
                plan_spec = dict(plan_result.get("rounds", {}).get("plan", {}) or {})
                plan_input = (
                    f"Discovered context:\n{str(discover_result.get('summary') or original_text)}\n\n"
                    f"Verifier feedback:\n{verifier_feedback or '(none)'}"
                )
                plan_round = await self._run_watch_round_with_campers(
                    campfire_name,
                    "plan",
                    list(plan_spec.get("campers") or [f"{campfire_name} Auditor"]),
                    str(plan_spec.get("goal") or "Refine the watch plan and assign campers to the next rounds."),
                    original_text,
                    plan_input,
                    corr,
                    watch_id,
                    history,
                )
                plan_round["planner"] = str(plan_result.get("_planner") or "")
                plan_round["planner_source"] = str(plan_result.get("_planner_source") or "")
                if plan_result.get("_planner_fallback_reason"):
                    plan_round["planner_fallback_reason"] = str(plan_result.get("_planner_fallback_reason") or "")
                if not str(plan_round.get("summary") or "").strip():
                    plan_round["summary"] = str(plan_result.get("_planner_raw") or "Watch plan refreshed.")
                history.append(plan_round)
                reroute_to = "execute"

            if reroute_to == "execute":
                execute_steps = list(plan_result.get("rounds", {}).get("execute", {}).get("steps") or [])
                execute_result = await self._run_watch_execute_round(
                    campfire_name,
                    torch,
                    execute_steps,
                    str(discover_result.get("summary") or original_text),
                    corr,
                    watch_id,
                )
                history.append(dict(execute_result))
                reroute_to = "verify"

            verify_spec = dict(plan_result.get("rounds", {}).get("verify", {}) or {})
            verify_result = await self._run_watch_verify_round(
                campfire_name,
                torch,
                verify_spec,
                str(discover_result.get("summary") or original_text),
                str(execute_result.get("summary") or ""),
                corr,
                watch_id,
                history,
            )
            history.append(dict(verify_result))
            decision = verify_result.get("decision") if isinstance(verify_result.get("decision"), dict) else {}
            watch_payload = {
                "watch_id": watch_id,
                "campfire": campfire_name,
                "torch_id": getattr(torch, "torch_id", ""),
                "retry_count": retry_count,
                "history": history,
                "report_url": f"/api/watch/runs/{watch_id}/report",
            }
            if decision.get("pass"):
                improve_spec = dict(plan_result.get("rounds", {}).get("improve", {}) or {})
                improve_result = await self._run_watch_improve_round(
                    campfire_name,
                    torch,
                    improve_spec,
                    verify_result,
                    execute_result,
                    corr,
                    watch_id,
                    history,
                    retry_count,
                )
                history.append(dict(improve_result))
                learning = dict(improve_result.get("learning") or {})
                learning_summary = None
                if bool(settings.get("save_learning", True)):
                    learning_summary = self._record_watch_learning(campfire_name, watch_id, str(corr or ""), learning, True, retry_count)
                result = {
                    "ok": True,
                    "text": str(execute_result.get("summary") or original_text or "Watch completed."),
                    "campfire": campfire_name,
                    "watch": {
                        **watch_payload,
                        "learning": learning,
                        "learning_summary": learning_summary,
                    },
                    "correlation_id": corr,
                }
                if bool(settings.get("save_trace", True)):
                    self._watch_runs[watch_id] = result
                    report_path = self.save_watch_report(watch_id)
                    if report_path:
                        result["watch"]["report_path"] = report_path
                        self._watch_runs[watch_id] = result
                return Torch(
                    claim="service_response",
                    source_campfire=f"{campfire_name} Watch",
                    channel="service",
                    torch_id=f"service_{uuid.uuid4().hex}",
                    sender_valley=self.name,
                    target_address=f"valley:{torch.sender_valley}",
                    data=result,
                    signature="service_placeholder",
                    metadata={"correlation_id": corr, "parent": campfire_name, "watch_run_id": watch_id},
                )
            if retry_count >= max_retries:
                improve_spec = dict(plan_result.get("rounds", {}).get("improve", {}) or {})
                improve_result = await self._run_watch_improve_round(
                    campfire_name,
                    torch,
                    improve_spec,
                    verify_result,
                    execute_result,
                    corr,
                    watch_id,
                    history,
                    retry_count,
                )
                history.append(dict(improve_result))
                learning = dict(improve_result.get("learning") or {})
                learning_summary = None
                if bool(settings.get("save_learning", True)):
                    learning_summary = self._record_watch_learning(campfire_name, watch_id, str(corr or ""), learning, False, retry_count)
                result = {
                    "ok": False,
                    "text": str(decision.get("feedback") or execute_result.get("summary") or "Watch verification failed."),
                    "campfire": campfire_name,
                    "watch": {
                        **watch_payload,
                        "learning": learning,
                        "learning_summary": learning_summary,
                    },
                    "correlation_id": corr,
                }
                if bool(settings.get("save_trace", True)):
                    self._watch_runs[watch_id] = result
                    report_path = self.save_watch_report(watch_id)
                    if report_path:
                        result["watch"]["report_path"] = report_path
                        self._watch_runs[watch_id] = result
                return Torch(
                    claim="service_response",
                    source_campfire=f"{campfire_name} Watch",
                    channel="service",
                    torch_id=f"service_{uuid.uuid4().hex}",
                    sender_valley=self.name,
                    target_address=f"valley:{torch.sender_valley}",
                    data=result,
                    signature="service_placeholder",
                    metadata={"correlation_id": corr, "parent": campfire_name, "watch_run_id": watch_id},
                )
            retry_count += 1
            verifier_feedback = str(decision.get("feedback") or "").strip()
            reroute_to = str(
                decision.get("reroute_to")
                or plan_result.get("failure_policy", {}).get("default_reroute_to")
                or settings.get("default_fail_reroute")
                or "plan"
            ).strip().lower()
            if reroute_to not in {"discover", "plan", "execute"}:
                reroute_to = "plan"

    def _normalize_rounds(self, rounds: Any) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for raw in rounds or []:
            if isinstance(raw, str):
                campfire = raw.strip()
                if not campfire:
                    continue
                out.append({"campfire": campfire, "label": campfire, "mode": "replace", "instruction": ""})
                continue
            if not isinstance(raw, dict):
                continue
            campfire = (
                raw.get("resolved_name")
                or raw.get("campfire")
                or raw.get("label")
                or raw.get("campfire")
                or raw.get("name")
                or raw.get("target")
                or raw.get("address")
                or raw.get("target_address")
                or ""
            ).strip()
            if not campfire:
                continue
            mode = (raw.get("mode") or "replace").strip().lower()
            if mode not in {"replace", "augment", "merge", "final"}:
                mode = "replace"
            instruction = (
                raw.get("instruction")
                or raw.get("task")
                or raw.get("prompt")
                or ""
            ).strip()
            spec: Dict[str, Any] = {
                "campfire": campfire,
                "mode": mode,
                "instruction": instruction,
            }
            for key in (
                "label",
                "target_address",
                "address",
                "target_valley",
                "source",
                "service_id",
                "task_type",
                "service_kind",
                "resolved_name",
                "role_tags",
            ):
                value = raw.get(key)
                if value is not None and value != "":
                    spec[key] = value
            out.append(spec)
        return out[:20]

    def _round_prompt(
        self,
        original_text: str,
        current_text: str,
        history: List[Dict[str, Any]],
        round_spec: Dict[str, str],
        round_number: int,
    ) -> str:
        mode = (round_spec.get("mode") or "replace").strip().lower()
        instruction = (round_spec.get("instruction") or "").strip()
        history_lines: List[str] = []
        for item in history[-8:]:
            if not isinstance(item, dict):
                continue
            rn = item.get("round")
            nm = item.get("campfire")
            summary = item.get("summary") or item.get("output") or ""
            summary = str(summary).strip()
            if not summary:
                continue
            history_lines.append(f"Round {rn}: {nm}\n{summary}")
        history_text = "\n\n---\n\n".join(history_lines) if history_lines else "(none)"
        instruction_block = f"\n\nRound instruction:\n{instruction}" if instruction else ""
        label = str(round_spec.get("label") or round_spec.get("campfire") or "").strip()
        service_id = str(round_spec.get("service_id") or "").strip()
        task_type = str(round_spec.get("task_type") or "").strip()
        target_address = str(round_spec.get("target_address") or "").strip()
        target_context_lines: List[str] = []
        if label:
            target_context_lines.append(f"Selected service: {label}")
        if service_id:
            target_context_lines.append(f"Service ID: {service_id}")
        if task_type:
            target_context_lines.append(f"Declared task type: {task_type}")
        if target_address:
            target_context_lines.append(f"Target address: {target_address}")
        target_context = ""
        if target_context_lines:
            target_context = "Round target:\n" + "\n".join(target_context_lines) + "\n\n"
        if mode == "augment":
            return (
                f"You are working in round {round_number} of a campfire chain.\n\n"
                f"{target_context}"
                f"Original request:\n{original_text}\n\n"
                f"Previous round output:\n{current_text or '(none)'}"
                f"{instruction_block}\n\n"
                f"Return the next improved output for the following campfire."
            )
        if mode in {"merge", "final"}:
            final_hint = ""
            if mode == "final":
                final_hint = (
                    "\n\nThis is the final round. Return the final client-facing response. "
                    "Do not describe internal routing or ask the user what to do next."
                )
            return (
                f"You are working in round {round_number} of a campfire chain.\n\n"
                f"{target_context}"
                f"Original request:\n{original_text}\n\n"
                f"Current input:\n{current_text or '(none)'}\n\n"
                f"Prior round history:\n{history_text}"
                f"{instruction_block}{final_hint}"
            )
        return (
            f"You are working in round {round_number} of a campfire chain.\n\n"
            f"{target_context}"
            f"Original request:\n{original_text}\n\n"
            f"Current input:\n{current_text or original_text or '(none)'}"
            f"{instruction_block}\n\n"
            "Use the selected service context when producing this round's output."
        )

    async def _process_target_campfire(self, campfire_name: str, torch: 'Torch') -> Optional['Torch']:
        campfire = self.campfires[campfire_name]
        if self._watch_enabled_for_torch(campfire_name, torch):
            watch_resp = await self._run_watch_for_torch(campfire_name, torch)
            if watch_resp is not None:
                return watch_resp
        service_resp = await self.process_service_call(campfire_name, torch)
        if service_resp is not None:
            return service_resp
        return await campfire.process_torch(torch)

    async def _process_remote_round_target(self, target_address: str, torch: 'Torch') -> Optional['Torch']:
        dock = getattr(self, "dock", None)
        broker = getattr(self, "mcp_broker", None)
        if not dock or not getattr(dock, "is_running", None) or not dock.is_running():
            raise RuntimeError("Dock is not running for remote rounds")
        if not broker or not getattr(broker, "is_connected", None) or not broker.is_connected():
            raise RuntimeError("MCP broker is not connected for remote rounds")

        reply_channel = f"reply:{self.name}:{uuid.uuid4().hex}"
        future = asyncio.get_running_loop().create_future()

        async def _reply_cb(_channel: str, msg: dict):
            if not future.done():
                future.set_result(msg)

        await broker.subscribe(reply_channel, _reply_cb)
        try:
            if not isinstance(torch.metadata, dict):
                torch.metadata = {}
            torch.metadata["reply_channel"] = reply_channel
            ok = await dock.send_torch(target_address, torch)
            if not ok:
                raise RuntimeError(f"Failed to send round torch to remote target '{target_address}'")
            try:
                msg = await asyncio.wait_for(future, timeout=45)
            except asyncio.TimeoutError as e:
                raise RuntimeError(f"Timed out waiting for remote round response from '{target_address}'") from e
        finally:
            try:
                await broker.unsubscribe(reply_channel)
            except Exception:
                pass

        target_valley = ""
        try:
            target_valley = target_address.split(":", 1)[1].split("/", 1)[0]
        except Exception:
            target_valley = ""
        return type(torch)(
            claim="service_response",
            source_campfire=target_valley or "Remote Round",
            channel="service",
            torch_id=f"service_{uuid.uuid4().hex}",
            sender_valley=target_valley or self.name,
            target_address=f"valley:{self.name}",
            data=msg if isinstance(msg, dict) else {"text": str(msg or "")},
            signature="service_placeholder",
            metadata={"correlation_id": (torch.metadata or {}).get("correlation_id", "")},
        )

    async def process_round_chain(self, torch: 'Torch') -> Optional['Torch']:
        metadata = getattr(torch, "metadata", None)
        if not isinstance(metadata, dict):
            return None
        rounds = self._normalize_rounds(metadata.get("rounds"))
        if getattr(torch, "claim", None) != "round_chain" and not rounds:
            return None
        if not rounds:
            return None

        corr = (metadata.get("correlation_id") or "").strip() or getattr(torch, "torch_id", None) or getattr(torch, "id", None)
        original_text = ""
        if isinstance(getattr(torch, "data", None), dict):
            original_text = str(torch.data.get("original_text") or torch.data.get("text") or "").strip()
        original_text = original_text or self._torch_text(torch)
        current_text = ""
        if isinstance(getattr(torch, "data", None), dict):
            current_text = str(torch.data.get("text") or "").strip()
        current_text = current_text or original_text
        history = metadata.get("round_history") if isinstance(metadata.get("round_history"), list) else []
        try:
            start_index = int(metadata.get("round_index") or 0)
        except Exception:
            start_index = 0
        start_index = max(0, min(start_index, len(rounds) - 1))

        for idx in range(start_index, len(rounds)):
            spec = rounds[idx]
            raw_target = str(spec.get("target_address") or spec.get("address") or spec.get("campfire") or "").strip()
            if not raw_target:
                continue
            target_name = raw_target
            target_address = raw_target if raw_target.lower().startswith("valley:") else str(spec.get("target_address") or "").strip()
            target_valley = str(spec.get("target_valley") or "").strip()
            local_aliases = {self.name}
            try:
                env = getattr(self.config, "env", None) or {}
                local_id = (env.get("valley_id") or "").strip() if isinstance(env, dict) else ""
                if local_id:
                    local_aliases.add(local_id)
            except Exception:
                pass
            if raw_target.lower().startswith("valley:"):
                rest = raw_target.split(":", 1)[1].strip()
                parts = [p.strip() for p in rest.split("/") if p.strip()]
                target_valley = parts[0] if parts else target_valley
                if len(parts) >= 2:
                    target_name = parts[1]
                elif target_valley:
                    target_name = target_valley
            if not target_address:
                target_address = f"valley:{self.name}/{target_name}"
            is_remote = bool(target_valley and target_valley not in local_aliases)
            if not is_remote:
                target_name = self._resolve_campfire_by_identifier(target_name) or target_name
            if not is_remote and target_name not in self.campfires:
                result = {
                    "ok": False,
                    "text": f"Round {idx + 1} failed: campfire '{raw_target}' was not found.",
                    "rounds": history,
                    "correlation_id": corr,
                }
                return type(torch)(
                    claim="service_response",
                    source_campfire="Round Chain",
                    channel="service",
                    torch_id=f"service_{uuid.uuid4().hex}",
                    sender_valley=self.name,
                    target_address=f"valley:{torch.sender_valley}",
                    data=result,
                    signature="service_placeholder",
                    metadata={"correlation_id": corr},
                )

            prompt = self._round_prompt(original_text, current_text, history, spec, idx + 1)
            round_torch = type(torch)(
                claim="service_request",
                source_campfire=f"Round {idx + 1}",
                channel="service",
                torch_id=f"round_{uuid.uuid4().hex}",
                sender_valley=self.name,
                target_address=target_address if target_address else f"valley:{self.name}/{target_name}",
                data={
                    "text": prompt,
                    "original_text": original_text,
                    "round_input": current_text,
                    "round_history": history,
                    "service_mode": True,
                },
                signature="service_placeholder",
                metadata={
                    "correlation_id": corr,
                    "round_number": idx + 1,
                    "round_mode": spec.get("mode") or "replace",
                    "round_instruction": spec.get("instruction") or "",
                    "round_service_id": spec.get("service_id") or "",
                    "round_task_type": spec.get("task_type") or "",
                    "round_target_address": target_address or "",
                },
            )
            if is_remote:
                try:
                    resp = await self._process_remote_round_target(target_address, round_torch)
                except Exception as e:
                    result = {
                        "ok": False,
                        "text": f"Round {idx + 1} failed for remote target '{raw_target}': {e}",
                        "rounds": history,
                        "correlation_id": corr,
                    }
                    return type(torch)(
                        claim="service_response",
                        source_campfire="Round Chain",
                        channel="service",
                        torch_id=f"service_{uuid.uuid4().hex}",
                        sender_valley=self.name,
                        target_address=f"valley:{torch.sender_valley}",
                        data=result,
                        signature="service_placeholder",
                        metadata={"correlation_id": corr},
                    )
            else:
                resp = await self._process_target_campfire(target_name, round_torch)
            text = self._extract_torch_response_text(resp)
            if not text:
                result = {
                    "ok": False,
                    "text": f"Round {idx + 1} ({spec.get('label') or target_name}) returned no response.",
                    "rounds": history,
                    "correlation_id": corr,
                }
                return type(torch)(
                    claim="service_response",
                    source_campfire="Round Chain",
                    channel="service",
                    torch_id=f"service_{uuid.uuid4().hex}",
                    sender_valley=self.name,
                    target_address=f"valley:{torch.sender_valley}",
                    data=result,
                    signature="service_placeholder",
                    metadata={"correlation_id": corr},
                )
            history.append(
                {
                    "round": idx + 1,
                    "campfire": spec.get("label") or target_name,
                    "mode": spec.get("mode") or "replace",
                    "instruction": spec.get("instruction") or "",
                    "service_id": spec.get("service_id") or "",
                    "task_type": spec.get("task_type") or "",
                    "target_address": target_address or "",
                    "output": text,
                    "summary": text[:400],
                }
            )
            current_text = text

        result = {
            "ok": True,
            "text": current_text or original_text or "Round chain completed.",
            "rounds": history,
            "correlation_id": corr,
            "campfire": history[-1]["campfire"] if history else "",
        }
        try:
            await self.monitoring.log(
                LogLevel.INFO,
                "Round chain completed",
                "rounds",
                context={"rounds_total": len(rounds), "completed": len(history)},
                correlation_id=corr,
            )
        except Exception:
            pass
        return type(torch)(
            claim="service_response",
            source_campfire="Round Chain",
            channel="service",
            torch_id=f"service_{uuid.uuid4().hex}",
            sender_valley=self.name,
            target_address=f"valley:{torch.sender_valley}",
            data=result,
            signature="service_placeholder",
            metadata={"correlation_id": corr},
        )

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
        override_steps = None
        try:
            if hasattr(torch, "metadata") and isinstance(torch.metadata, dict):
                v = torch.metadata.get("workflow_override_steps")
                if isinstance(v, list) and v:
                    override_steps = v
        except Exception:
            override_steps = None
        workflow = self.get_workflow(campfire_name) or {}
        steps = override_steps if override_steps is not None else (workflow.get("steps") if isinstance(workflow, dict) else None)
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
            raw_target = str(campfire_name or "")

            # Prefer an exact local campfire name before interpreting ":" or "/"
            # as routing syntax. Campfire names can legitimately contain URLs.
            if raw_target in self.campfires:
                logger.info(f"Routing torch {torch.torch_id} to campfire '{raw_target}' via exact target match")
                return await self._process_target_campfire(raw_target, torch)
            
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

            round_resp = await self.process_round_chain(torch)
            if round_resp is not None:
                return round_resp
            
            # Remove any "campfire:" prefix if present
            if campfire_name.startswith("campfire:"):
                campfire_name = campfire_name[9:]
            
            # Get the campfire
            resolved_name = campfire_name
            if resolved_name not in self.campfires:
                resolved_name = self._resolve_campfire_by_identifier(campfire_name) or campfire_name
            if resolved_name in self.campfires:
                logger.info(f"Routing torch {torch.torch_id} to campfire '{resolved_name}'")
                return await self._process_target_campfire(resolved_name, torch)
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

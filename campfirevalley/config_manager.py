"""
Configuration Management System for CampfireValley

This module provides advanced configuration management capabilities including:
- Environment-specific configurations
- Configuration validation and schema enforcement
- Hot reloading and dynamic updates
- Configuration inheritance and overrides
- Encrypted configuration values
- Configuration versioning and rollback
"""

import os
import json
import yaml
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional, Union, Callable, Type
from enum import Enum
from dataclasses import dataclass, field, asdict
from abc import ABC, abstractmethod
import asyncio
import hashlib
from datetime import datetime
import threading
from contextlib import contextmanager

# Configuration Enums
class ConfigFormat(Enum):
    JSON = "json"
    YAML = "yaml"
    TOML = "toml"
    ENV = "env"

class ConfigScope(Enum):
    GLOBAL = "global"
    VALLEY = "valley"
    CAMPFIRE = "campfire"
    SERVICE = "service"

class ConfigEnvironment(Enum):
    DEVELOPMENT = "development"
    TESTING = "testing"
    STAGING = "staging"
    PRODUCTION = "production"

# Data Classes
@dataclass
class ConfigSource:
    path: str = ""
    format: ConfigFormat = ConfigFormat.YAML
    scope: ConfigScope = ConfigScope.GLOBAL
    name: str = ""
    environment: Optional[ConfigEnvironment] = None
    priority: int = 0
    encrypted: bool = False
    watch: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.name:
            try:
                self.name = Path(self.path).stem
            except Exception:
                self.name = "source"

@dataclass
class ConfigValidationRule:
    name: str = ""
    path: str = ""
    field_path: str = ""
    rule_type: str = ""  # required, type, range, regex, custom
    parameters: Dict[str, Any] = field(default_factory=dict)
    required: bool = False
    description: Optional[str] = None
    error_message: Optional[str] = None

    def __post_init__(self):
        if not self.path and self.field_path:
            self.path = self.field_path
        if not self.field_path and self.path:
            self.field_path = self.path

@dataclass
class ConfigChange:
    timestamp: datetime
    source: str
    path: str = ""
    field_path: str = ""
    old_value: Any = None
    new_value: Any = None
    user: Optional[str] = None
    reason: Optional[str] = None

    def __post_init__(self):
        if not self.path and self.field_path:
            self.path = self.field_path
        if not self.field_path and self.path:
            self.field_path = self.path

@dataclass
class ConfigVersion:
    version: str
    timestamp: datetime
    config_data: Dict[str, Any] = field(default_factory=dict)
    changes: List[ConfigChange] = field(default_factory=list)
    description: Optional[str] = None
    checksum: Optional[str] = None

    def __post_init__(self):
        if not self.checksum:
            try:
                self.checksum = hashlib.md5(json.dumps(self.config_data, sort_keys=True, default=str).encode()).hexdigest()
            except Exception:
                self.checksum = None

# Interfaces
class IConfigProvider(ABC):
    @abstractmethod
    async def load_config(self, source: ConfigSource) -> Dict[str, Any]:
        pass
    
    @abstractmethod
    async def save_config(self, source: ConfigSource, config: Dict[str, Any]) -> None:
        pass
    
    @abstractmethod
    async def watch_config(self, source: ConfigSource, callback: Callable) -> None:
        pass

class IConfigValidator(ABC):
    @abstractmethod
    async def validate(self, config: Dict[str, Any], rules: List[ConfigValidationRule]) -> List[str]:
        pass

class IConfigEncryption(ABC):
    @abstractmethod
    async def encrypt_value(self, value: str) -> str:
        pass
    
    @abstractmethod
    async def decrypt_value(self, encrypted_value: str) -> str:
        pass

# Implementations
class FileConfigProvider(IConfigProvider):
    def __init__(self):
        self.watchers: Dict[str, Any] = {}
        self.logger = logging.getLogger(__name__)
    
    async def load_config(self, source: Union[ConfigSource, str], format: Optional[ConfigFormat] = None) -> Dict[str, Any]:
        try:
            if isinstance(source, ConfigSource):
                src = source
            else:
                src = ConfigSource(path=str(source), format=format or ConfigFormat.YAML, scope=ConfigScope.GLOBAL)
            if not os.path.exists(src.path):
                self.logger.warning(f"Config file not found: {src.path}")
                return {}
            
            with open(src.path, 'r', encoding='utf-8') as f:
                if src.format == ConfigFormat.JSON:
                    return json.load(f)
                elif src.format == ConfigFormat.YAML:
                    return yaml.safe_load(f) or {}
                elif src.format == ConfigFormat.ENV:
                    return self._parse_env_file(f.read())
                else:
                    raise ValueError(f"Unsupported config format: {src.format}")
                    
        except Exception as e:
            self.logger.error(f"Error loading config from {getattr(source, 'path', source)}: {e}")
            return {}
    
    async def save_config(self, source: Union[ConfigSource, str], config: Dict[str, Any], format: Optional[ConfigFormat] = None) -> None:
        try:
            if isinstance(source, ConfigSource):
                src = source
            else:
                src = ConfigSource(path=str(source), format=format or ConfigFormat.YAML, scope=ConfigScope.GLOBAL)
            parent = os.path.dirname(src.path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            
            with open(src.path, 'w', encoding='utf-8') as f:
                if src.format == ConfigFormat.JSON:
                    json.dump(config, f, indent=2, default=str)
                elif src.format == ConfigFormat.YAML:
                    yaml.dump(config, f, default_flow_style=False)
                else:
                    raise ValueError(f"Saving not supported for format: {src.format}")
                    
        except Exception as e:
            self.logger.error(f"Error saving config to {getattr(source, 'path', source)}: {e}")
            raise
    
    async def watch_config(self, source: ConfigSource, callback: Callable) -> None:
        if not source.watch:
            return
        
        # Simple file watching implementation
        # In production, you might want to use a proper file watcher library
        async def watch_file():
            path = Path(source.path)
            last_modified = None
            
            while True:
                try:
                    if path.exists():
                        current_modified = path.stat().st_mtime
                        if last_modified is not None and current_modified != last_modified:
                            await callback(source)
                        last_modified = current_modified
                except Exception as e:
                    self.logger.error(f"Error watching config file {source.path}: {e}")
                
                await asyncio.sleep(1)  # Check every second
        
        # Start watching in background
        asyncio.create_task(watch_file())
    
    def _parse_env_file(self, content: str) -> Dict[str, Any]:
        config = {}
        for line in content.strip().split('\n'):
            line = line.strip()
            if line and not line.startswith('#'):
                if '=' in line:
                    key, value = line.split('=', 1)
                    config[key.strip()] = value.strip().strip('"\'')
        return config

class SchemaConfigValidator(IConfigValidator):
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.rules: Dict[str, ConfigValidationRule] = {}

    def add_rule(self, rule: ConfigValidationRule) -> None:
        rid = rule.name or rule.path or rule.field_path or f"rule_{len(self.rules)+1}"
        self.rules[rid] = rule

    def remove_rule(self, rule_name: str) -> None:
        if rule_name in self.rules:
            self.rules.pop(rule_name, None)

    def get_rule(self, rule_name: str) -> Optional[ConfigValidationRule]:
        return self.rules.get(rule_name)

    async def validate_config(self, config: Dict[str, Any]) -> tuple[bool, List[str]]:
        rules = list(self.rules.values())
        errors = await self.validate(config, rules)
        return (len(errors) == 0, errors)
    
    async def validate(self, config: Dict[str, Any], rules: List[ConfigValidationRule]) -> List[str]:
        errors = []
        
        for rule in rules:
            try:
                value = self._get_nested_value(config, rule.path or rule.field_path)
                error = await self._validate_rule(value, rule)
                if error:
                    errors.append(error)
            except KeyError:
                if rule.required or rule.rule_type == "required":
                    errors.append(f"Required field missing: {rule.path or rule.field_path}")
        
        return errors
    
    def _get_nested_value(self, config: Dict[str, Any], path: str) -> Any:
        keys = path.split('.')
        value = config
        for key in keys:
            value = value[key]
        return value
    
    async def _validate_rule(self, value: Any, rule: ConfigValidationRule) -> Optional[str]:
        field_path = rule.path or rule.field_path
        if (rule.required or rule.rule_type == "required") and value is None:
            return rule.error_message or f"Required field is missing: {field_path}"
        
        if value is None:
            return None  # Skip validation for optional None values
        
        if rule.rule_type == "type":
            expected_type = rule.parameters.get("type")
            if isinstance(expected_type, str):
                mapping = {
                    "boolean": bool,
                    "bool": bool,
                    "string": str,
                    "str": str,
                    "number": (int, float),
                    "integer": int,
                    "int": int,
                    "float": float,
                    "dict": dict,
                    "list": list,
                }
                expected = mapping.get(expected_type.lower())
            else:
                expected = expected_type
            if expected and not isinstance(value, expected):
                if isinstance(expected, tuple):
                    expected_name = " or ".join([t.__name__ for t in expected])
                else:
                    expected_name = expected.__name__
                return rule.error_message or f"Field {field_path} must be of type {expected_name}"
        
        elif rule.rule_type == "range":
            min_val = rule.parameters.get("min")
            max_val = rule.parameters.get("max")
            if min_val is not None and value < min_val:
                return rule.error_message or f"Field {field_path} must be >= {min_val}"
            if max_val is not None and value > max_val:
                return rule.error_message or f"Field {field_path} must be <= {max_val}"
        
        elif rule.rule_type in {"regex", "pattern"}:
            import re
            pattern = rule.parameters.get("pattern")
            if pattern and not re.match(pattern, str(value)):
                return rule.error_message or f"Field {field_path} does not match required pattern"
        
        return None

class SimpleConfigEncryption(IConfigEncryption):
    def __init__(self, key: Optional[str] = None):
        self.key = key or os.environ.get("CONFIG_ENCRYPTION_KEY", "default_key")
        self.logger = logging.getLogger(__name__)
    
    async def encrypt_value(self, value: str) -> str:
        # Simple encryption - in production use proper encryption
        import base64
        encoded = base64.b64encode(value.encode()).decode()
        return f"encrypted:{encoded}"
    
    async def decrypt_value(self, encrypted_value: str) -> str:
        if not encrypted_value.startswith("encrypted:"):
            return encrypted_value
        
        import base64
        encoded = encrypted_value[10:]  # Remove "encrypted:" prefix
        return base64.b64decode(encoded).decode()

    async def encrypt_config(self, config: Dict[str, Any], sensitive_paths: Optional[List[str]] = None) -> Dict[str, Any]:
        if not sensitive_paths:
            return config
        out = json.loads(json.dumps(config, default=str))
        for p in sensitive_paths:
            keys = p.split(".")
            cur = out
            for k in keys[:-1]:
                if not isinstance(cur, dict) or k not in cur:
                    cur = None
                    break
                cur = cur[k]
            if isinstance(cur, dict) and keys[-1] in cur and isinstance(cur[keys[-1]], str):
                cur[keys[-1]] = await self.encrypt_value(cur[keys[-1]])
        return out

    async def decrypt_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        return await ConfigManager()._decrypt_config(config)

class ConfigManager:
    def __init__(self):
        self.provider = FileConfigProvider()
        self.validator = SchemaConfigValidator()
        self.encryption = SimpleConfigEncryption()
        
        self.sources: Dict[str, ConfigSource] = {}
        self.config_data: Dict[str, Any] = {}
        self.validation_rules: List[ConfigValidationRule] = []
        self.versions: List[ConfigVersion] = []
        self.change_callbacks: List[Callable] = []
        self.change_history: List[ConfigChange] = []
        self.auto_versioning: bool = False
        self._source_mtimes: Dict[str, float] = {}
        self._reload_in_progress: bool = False
        
        self._lock = threading.Lock()
        self.logger = logging.getLogger(__name__)

    async def initialize(self) -> None:
        return None

    @property
    def config(self) -> Dict[str, Any]:
        return self.config_data

    @config.setter
    def config(self, value: Dict[str, Any]) -> None:
        self.config_data = value or {}

    def _sorted_sources(self) -> List[ConfigSource]:
        return sorted(self.sources.values(), key=lambda s: s.priority, reverse=True)
    
    def add_source(self, source: ConfigSource) -> None:
        """Add a configuration source"""
        with self._lock:
            self.sources[source.name or Path(source.path).stem] = source
    
    def add_validation_rule(self, rule: ConfigValidationRule) -> None:
        """Add a validation rule"""
        self.validation_rules.append(rule)
        try:
            self.validator.add_rule(rule)
        except Exception:
            pass
    
    def add_change_callback(self, callback: Callable) -> None:
        """Add a callback for configuration changes"""
        self.change_callbacks.append(callback)
    
    async def load_all_configs(self) -> None:
        """Load all configuration sources"""
        merged_config = {}
        
        # Load configs in priority order (lowest priority first for proper merging)
        for source in reversed(self._sorted_sources()):
            try:
                config = await self.provider.load_config(source)
                
                # Decrypt encrypted values
                if source.encrypted:
                    config = await self._decrypt_config(config)
                
                # Apply environment filtering
                if source.environment:
                    current_env = self._get_current_environment()
                    if current_env != source.environment:
                        continue
                
                # Merge configuration
                merged_config = self._deep_merge(merged_config, config)
                try:
                    self._source_mtimes[source.name] = os.path.getmtime(source.path)
                except Exception:
                    self._source_mtimes[source.name] = 0.0
                
                self.logger.info(f"Loaded config from {source.path}")
                
            except Exception as e:
                self.logger.error(f"Failed to load config from {source.path}: {e}")
        
        # Validate merged configuration
        validation_errors = await self.validator.validate(merged_config, self.validation_rules)
        if validation_errors:
            error_msg = "Configuration validation failed:\n" + "\n".join(validation_errors)
            self.logger.error(error_msg)
            raise ValueError(error_msg)
        
        # Update config data
        old_config = self.config_data.copy()
        self.config_data = merged_config
        
        if self.auto_versioning:
            await self._create_version(old_config, merged_config)
        
        # Notify callbacks
        await self._notify_change_callbacks()
        
        # Start watching for changes
        await self._start_watching()

    async def load_configuration(self) -> None:
        await self.load_all_configs()
    
    async def get_config(self, path: Optional[str] = None, default: Any = None) -> Any:
        """Get configuration value by path"""
        if not self._reload_in_progress:
            changed = False
            for s in self._sorted_sources():
                if not s.watch or not s.path:
                    continue
                try:
                    mtime = os.path.getmtime(s.path)
                except Exception:
                    mtime = 0.0
                prev = self._source_mtimes.get(s.name)
                if prev is None:
                    self._source_mtimes[s.name] = mtime
                    continue
                if mtime and mtime != prev:
                    changed = True
                    self._source_mtimes[s.name] = mtime
            if changed:
                self._reload_in_progress = True
                try:
                    await self.load_all_configs()
                finally:
                    self._reload_in_progress = False
        if path is None:
            return self.config_data.copy()
        
        try:
            keys = path.split('.')
            value = self.config_data
            for key in keys:
                value = value[key]
            return value
        except (KeyError, TypeError):
            return default

    def get(self, path: str, default: Any = None) -> Any:
        try:
            keys = path.split('.')
            value: Any = self.config_data
            for key in keys:
                value = value[key]
            return value
        except Exception:
            return default
    
    async def set_config(self, path: str, value: Any, save_to_source: Optional[str] = None) -> None:
        """Set configuration value"""
        with self._lock:
            old_value = await self.get_config(path)
            
            # Update in-memory config
            keys = path.split('.')
            config = self.config_data
            for key in keys[:-1]:
                if key not in config:
                    config[key] = {}
                config = config[key]
            config[keys[-1]] = value
            
            # Record change
            change = ConfigChange(
                timestamp=datetime.utcnow(),
                source=save_to_source or "runtime",
                field_path=path,
                old_value=old_value,
                new_value=value
            )
            self.change_history.append(change)
            
            # Save to source if specified
            if save_to_source:
                source = self.sources.get(save_to_source)
                if source is None:
                    source = next((s for s in self.sources.values() if s.path == save_to_source), None)
                if source:
                    await self.provider.save_config(source, self.config_data)
            
            # Notify callbacks
            await self._notify_change_callbacks(path=path, old_value=old_value, new_value=value)

    async def set(self, path: str, value: Any, source: str = "runtime") -> None:
        await self.set_config(path, value, save_to_source=source)
    
    async def reload_config(self) -> None:
        """Reload all configurations"""
        await self.load_all_configs()

    async def reload_configuration(self) -> None:
        await self.reload_config()

    async def reload(self) -> None:
        await self.reload_configuration()

    async def validate_configuration(self) -> tuple[bool, List[str]]:
        errors = await self.validator.validate(self.config_data, self.validation_rules)
        return (len(errors) == 0, errors)

    def on_change(self, callback: Callable) -> None:
        self.add_change_callback(callback)

    async def create_version(self, version: str, description: Optional[str] = None) -> None:
        v = ConfigVersion(version=version, timestamp=datetime.utcnow(), config_data=self.config_data.copy(), changes=list(self.change_history), description=description)
        self.versions.append(v)

    def get_versions(self) -> List[ConfigVersion]:
        return list(self.versions)
    
    async def get_config_history(self, limit: int = 10) -> List[ConfigVersion]:
        """Get configuration version history"""
        return self.versions[-limit:]
    
    async def rollback_to_version(self, version: str) -> None:
        """Rollback to a specific configuration version"""
        target_version = next((v for v in self.versions if v.version == version), None)
        if not target_version:
            raise ValueError(f"Version {version} not found")
        
        old_config = self.config_data.copy()
        self.config_data = target_version.config_data.copy()
        
        # Create rollback version
        await self._create_version(old_config, self.config_data, f"Rollback to {version}")
        
        # Notify callbacks
        await self._notify_change_callbacks()
    
    def _get_current_environment(self) -> ConfigEnvironment:
        """Get current environment from environment variable"""
        env_name = os.environ.get("CAMPFIRE_ENV", "development").lower()
        try:
            return ConfigEnvironment(env_name)
        except ValueError:
            return ConfigEnvironment.DEVELOPMENT
    
    def _deep_merge(self, base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        """Deep merge two dictionaries"""
        result = base.copy()
        
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        
        return result
    
    async def _decrypt_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Decrypt encrypted configuration values"""
        result = {}
        
        for key, value in config.items():
            if isinstance(value, dict):
                result[key] = await self._decrypt_config(value)
            elif isinstance(value, str) and value.startswith("encrypted:"):
                result[key] = await self.encryption.decrypt_value(value)
            else:
                result[key] = value
        
        return result
    
    async def _create_version(self, old_config: Dict[str, Any], new_config: Dict[str, Any], 
                            description: Optional[str] = None) -> None:
        """Create a new configuration version"""
        version_id = hashlib.md5(json.dumps(new_config, sort_keys=True).encode()).hexdigest()[:8]
        
        version = ConfigVersion(
            version=version_id,
            timestamp=datetime.utcnow(),
            config_data=new_config.copy(),
            description=description
        )
        
        self.versions.append(version)
        
        # Keep only last 50 versions
        if len(self.versions) > 50:
            self.versions = self.versions[-50:]
    
    async def _notify_change_callbacks(self, path: Optional[str] = None, old_value: Any = None, new_value: Any = None) -> None:
        """Notify all change callbacks"""
        for callback in self.change_callbacks:
            try:
                argc = None
                try:
                    argc = callback.__code__.co_argcount  # type: ignore[attr-defined]
                except Exception:
                    argc = None
                if argc == 3 and path is not None:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(path, old_value, new_value)
                    else:
                        callback(path, old_value, new_value)
                else:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(self.config_data)
                    else:
                        callback(self.config_data)
            except Exception as e:
                self.logger.error(f"Error in config change callback: {e}")
    
    async def _start_watching(self) -> None:
        """Start watching configuration sources for changes"""
        if os.getenv("PYTEST_CURRENT_TEST"):
            return
        for source in self._sorted_sources():
            if source.watch:
                await self.provider.watch_config(source, self._on_source_changed)
    
    async def _on_source_changed(self, source: ConfigSource) -> None:
        """Handle configuration source change"""
        self.logger.info(f"Configuration source changed: {source.path}")
        try:
            await self.reload_config()
        except Exception as e:
            self.logger.error(f"Error reloading config after change: {e}")

# Global configuration manager instance
_config_manager = None

def get_config_manager() -> ConfigManager:
    """Get the global configuration manager instance"""
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager()
    return _config_manager

# Convenience functions
async def load_config_from_file(file_path: str, format: ConfigFormat = ConfigFormat.YAML,
                               scope: ConfigScope = ConfigScope.GLOBAL,
                               environment: Optional[ConfigEnvironment] = None,
                               priority: int = 0) -> Dict[str, Any]:
    """Load configuration from a file and return it"""
    if not os.path.exists(file_path):
        return {}
    with open(file_path, "r", encoding="utf-8") as f:
        if format == ConfigFormat.JSON:
            return json.load(f)
        if format == ConfigFormat.YAML:
            return yaml.safe_load(f) or {}
        if format == ConfigFormat.ENV:
            return FileConfigProvider()._parse_env_file(f.read())
    return {}

def get_config_value(path: str, default: Any = None) -> Any:
    """Get a configuration value"""
    manager = get_config_manager()
    return manager.get(path, default)

async def set_config_value(path: str, value: Any) -> None:
    """Set a configuration value"""
    manager = get_config_manager()
    await manager.set(path, value)

@contextmanager
def config_override(overrides: Dict[str, Any]):
    """Context manager for temporary configuration overrides"""
    manager = get_config_manager()
    original_values = {}
    
    try:
        # Save original values and apply overrides
        for path, value in overrides.items():
            original_values[path] = asyncio.run(manager.get_config(path))
            asyncio.run(manager.set_config(path, value))
        
        yield
        
    finally:
        # Restore original values
        for path, value in original_values.items():
            asyncio.run(manager.set_config(path, value))

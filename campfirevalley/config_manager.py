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
    path: str
    format: ConfigFormat
    scope: ConfigScope
    environment: Optional[ConfigEnvironment] = None
    priority: int = 0
    encrypted: bool = False
    watch: bool = True

@dataclass
class ConfigValidationRule:
    field_path: str
    rule_type: str  # required, type, range, regex, custom
    parameters: Dict[str, Any] = field(default_factory=dict)
    error_message: Optional[str] = None

@dataclass
class ConfigChange:
    timestamp: datetime
    source: str
    field_path: str
    old_value: Any
    new_value: Any
    user: Optional[str] = None

@dataclass
class ConfigVersion:
    version: str
    timestamp: datetime
    config_data: Dict[str, Any]
    changes: List[ConfigChange] = field(default_factory=list)
    description: Optional[str] = None

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
    
    async def load_config(self, source: ConfigSource) -> Dict[str, Any]:
        try:
            path = Path(source.path)
            if not path.exists():
                self.logger.warning(f"Config file not found: {source.path}")
                return {}
            
            with open(path, 'r', encoding='utf-8') as f:
                if source.format == ConfigFormat.JSON:
                    return json.load(f)
                elif source.format == ConfigFormat.YAML:
                    return yaml.safe_load(f) or {}
                elif source.format == ConfigFormat.ENV:
                    return self._parse_env_file(f.read())
                else:
                    raise ValueError(f"Unsupported config format: {source.format}")
                    
        except Exception as e:
            self.logger.error(f"Error loading config from {source.path}: {e}")
            return {}
    
    async def save_config(self, source: ConfigSource, config: Dict[str, Any]) -> None:
        try:
            path = Path(source.path)
            path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(path, 'w', encoding='utf-8') as f:
                if source.format == ConfigFormat.JSON:
                    json.dump(config, f, indent=2, default=str)
                elif source.format == ConfigFormat.YAML:
                    yaml.dump(config, f, default_flow_style=False)
                else:
                    raise ValueError(f"Saving not supported for format: {source.format}")
                    
        except Exception as e:
            self.logger.error(f"Error saving config to {source.path}: {e}")
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
    
    async def validate(self, config: Dict[str, Any], rules: List[ConfigValidationRule]) -> List[str]:
        errors = []
        
        for rule in rules:
            try:
                value = self._get_nested_value(config, rule.field_path)
                error = await self._validate_rule(value, rule)
                if error:
                    errors.append(error)
            except KeyError:
                if rule.rule_type == "required":
                    errors.append(f"Required field missing: {rule.field_path}")
        
        return errors
    
    def _get_nested_value(self, config: Dict[str, Any], path: str) -> Any:
        keys = path.split('.')
        value = config
        for key in keys:
            value = value[key]
        return value
    
    async def _validate_rule(self, value: Any, rule: ConfigValidationRule) -> Optional[str]:
        if rule.rule_type == "required" and value is None:
            return rule.error_message or f"Required field is missing: {rule.field_path}"
        
        if value is None:
            return None  # Skip validation for optional None values
        
        if rule.rule_type == "type":
            expected_type = rule.parameters.get("type")
            if expected_type and not isinstance(value, expected_type):
                return rule.error_message or f"Field {rule.field_path} must be of type {expected_type.__name__}"
        
        elif rule.rule_type == "range":
            min_val = rule.parameters.get("min")
            max_val = rule.parameters.get("max")
            if min_val is not None and value < min_val:
                return rule.error_message or f"Field {rule.field_path} must be >= {min_val}"
            if max_val is not None and value > max_val:
                return rule.error_message or f"Field {rule.field_path} must be <= {max_val}"
        
        elif rule.rule_type == "regex":
            import re
            pattern = rule.parameters.get("pattern")
            if pattern and not re.match(pattern, str(value)):
                return rule.error_message or f"Field {rule.field_path} does not match required pattern"
        
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

class ConfigManager:
    def __init__(self):
        self.provider = FileConfigProvider()
        self.validator = SchemaConfigValidator()
        self.encryption = SimpleConfigEncryption()
        
        self.sources: List[ConfigSource] = []
        self.config_data: Dict[str, Any] = {}
        self.validation_rules: List[ConfigValidationRule] = []
        self.versions: List[ConfigVersion] = []
        self.change_callbacks: List[Callable] = []
        
        self._lock = threading.Lock()
        self.logger = logging.getLogger(__name__)
    
    def add_source(self, source: ConfigSource) -> None:
        """Add a configuration source"""
        with self._lock:
            self.sources.append(source)
            # Sort by priority (higher priority first)
            self.sources.sort(key=lambda s: s.priority, reverse=True)
    
    def add_validation_rule(self, rule: ConfigValidationRule) -> None:
        """Add a validation rule"""
        self.validation_rules.append(rule)
    
    def add_change_callback(self, callback: Callable) -> None:
        """Add a callback for configuration changes"""
        self.change_callbacks.append(callback)
    
    async def load_all_configs(self) -> None:
        """Load all configuration sources"""
        merged_config = {}
        
        # Load configs in priority order (lowest priority first for proper merging)
        for source in reversed(self.sources):
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
        
        # Create version
        await self._create_version(old_config, merged_config)
        
        # Notify callbacks
        await self._notify_change_callbacks()
        
        # Start watching for changes
        await self._start_watching()
    
    async def get_config(self, path: Optional[str] = None, default: Any = None) -> Any:
        """Get configuration value by path"""
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
            
            # Save to source if specified
            if save_to_source:
                source = next((s for s in self.sources if s.path == save_to_source), None)
                if source:
                    await self.provider.save_config(source, self.config_data)
            
            # Notify callbacks
            await self._notify_change_callbacks()
    
    async def reload_config(self) -> None:
        """Reload all configurations"""
        await self.load_all_configs()
    
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
    
    async def _notify_change_callbacks(self) -> None:
        """Notify all change callbacks"""
        for callback in self.change_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(self.config_data)
                else:
                    callback(self.config_data)
            except Exception as e:
                self.logger.error(f"Error in config change callback: {e}")
    
    async def _start_watching(self) -> None:
        """Start watching configuration sources for changes"""
        for source in self.sources:
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
                               priority: int = 0) -> None:
    """Load configuration from a file"""
    manager = get_config_manager()
    source = ConfigSource(
        path=file_path,
        format=format,
        scope=scope,
        environment=environment,
        priority=priority
    )
    manager.add_source(source)
    await manager.load_all_configs()

async def get_config_value(path: str, default: Any = None) -> Any:
    """Get a configuration value"""
    manager = get_config_manager()
    return await manager.get_config(path, default)

async def set_config_value(path: str, value: Any) -> None:
    """Set a configuration value"""
    manager = get_config_manager()
    await manager.set_config(path, value)

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
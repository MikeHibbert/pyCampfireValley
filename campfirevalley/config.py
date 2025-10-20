"""
Configuration management using PyYAML for GitHub Actions-style configs.
"""

import yaml
import os
from pathlib import Path
from typing import Dict, Any, Optional
from .models import ValleyConfig, CampfireConfig


class ConfigManager:
    """Manages configuration loading and validation for valleys and campfires"""
    
    @staticmethod
    def load_valley_config(manifest_path: str = "./manifest.yaml") -> ValleyConfig:
        """
        Load valley configuration from manifest.yaml file.
        
        Args:
            manifest_path: Path to the manifest.yaml file
            
        Returns:
            ValleyConfig: Validated valley configuration
            
        Raises:
            FileNotFoundError: If manifest file doesn't exist
            yaml.YAMLError: If YAML parsing fails
            ValueError: If configuration validation fails
        """
        manifest_file = Path(manifest_path)
        
        if not manifest_file.exists():
            raise FileNotFoundError(f"Manifest file not found: {manifest_path}")
        
        try:
            with open(manifest_file, 'r', encoding='utf-8') as f:
                config_data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise yaml.YAMLError(f"Failed to parse YAML file {manifest_path}: {e}")
        
        if not config_data:
            config_data = {}
        
        # Validate and create ValleyConfig
        try:
            return ValleyConfig(**config_data)
        except Exception as e:
            raise ValueError(f"Invalid valley configuration: {e}")
    
    @staticmethod
    def load_campfire_config(config_path: str) -> CampfireConfig:
        """
        Load campfire configuration from YAML file.
        
        Args:
            config_path: Path to the campfire configuration file
            
        Returns:
            CampfireConfig: Validated campfire configuration
            
        Raises:
            FileNotFoundError: If config file doesn't exist
            yaml.YAMLError: If YAML parsing fails
            ValueError: If configuration validation fails
        """
        config_file = Path(config_path)
        
        if not config_file.exists():
            raise FileNotFoundError(f"Campfire config file not found: {config_path}")
        
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                config_data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise yaml.YAMLError(f"Failed to parse YAML file {config_path}: {e}")
        
        if not config_data:
            config_data = {}
        
        # Validate and create CampfireConfig
        try:
            return CampfireConfig(**config_data)
        except Exception as e:
            raise ValueError(f"Invalid campfire configuration: {e}")
    
    @staticmethod
    def save_valley_config(config: ValleyConfig, manifest_path: str = "./manifest.yaml") -> None:
        """
        Save valley configuration to manifest.yaml file.
        
        Args:
            config: Valley configuration to save
            manifest_path: Path where to save the manifest file
        """
        manifest_file = Path(manifest_path)
        manifest_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Convert to dict and clean up None values
        config_dict = config.dict(exclude_none=True)
        
        try:
            with open(manifest_file, 'w', encoding='utf-8') as f:
                yaml.dump(config_dict, f, default_flow_style=False, sort_keys=False)
        except Exception as e:
            raise IOError(f"Failed to save valley config to {manifest_path}: {e}")
    
    @staticmethod
    def save_campfire_config(config: CampfireConfig, config_path: str) -> None:
        """
        Save campfire configuration to YAML file.
        
        Args:
            config: Campfire configuration to save
            config_path: Path where to save the config file
        """
        config_file = Path(config_path)
        config_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Convert to dict and clean up None values
        config_dict = config.dict(exclude_none=True)
        
        try:
            with open(config_file, 'w', encoding='utf-8') as f:
                yaml.dump(config_dict, f, default_flow_style=False, sort_keys=False)
        except Exception as e:
            raise IOError(f"Failed to save campfire config to {config_path}: {e}")
    
    @staticmethod
    def create_default_valley_config(name: str) -> ValleyConfig:
        """
        Create a default valley configuration.
        
        Args:
            name: Name of the valley
            
        Returns:
            ValleyConfig: Default valley configuration
        """
        return ValleyConfig(
            name=name,
            version="1.0",
            env={
                "dock_mode": "private",
                "security_level": "standard", 
                "auto_create_dock": True
            },
            campfires={
                "visible": [],
                "hidden": []
            },
            dock={
                "steps": [
                    {
                        "name": "Initialize gateway",
                        "uses": "dock/gateway@v1",
                        "with": {
                            "port": 6379,
                            "encryption": True
                        }
                    }
                ]
            },
            community={
                "discovery": False,
                "trusted_valleys": []
            }
        )
    
    @staticmethod
    def create_default_campfire_config(name: str) -> CampfireConfig:
        """
        Create a default campfire configuration.
        
        Args:
            name: Name of the campfire
            
        Returns:
            CampfireConfig: Default campfire configuration
        """
        return CampfireConfig(
            name=name,
            runs_on="valley",
            env={},
            strategy={"matrix": {}},
            steps=[
                {
                    "name": "Setup environment",
                    "uses": "camper/loader@v1"
                }
            ],
            needs=[],
            outputs={},
            rag_paths=[],
            auditor_enabled=True,
            channels=[]
        )
    
    @staticmethod
    def validate_config_syntax(config_path: str) -> tuple[bool, Optional[str]]:
        """
        Validate YAML syntax without loading into models.
        
        Args:
            config_path: Path to the configuration file
            
        Returns:
            tuple: (is_valid, error_message)
        """
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                yaml.safe_load(f)
            return True, None
        except FileNotFoundError:
            return False, f"File not found: {config_path}"
        except yaml.YAMLError as e:
            return False, f"YAML syntax error: {e}"
        except Exception as e:
            return False, f"Unexpected error: {e}"
    
    @staticmethod
    def merge_configs(base_config: Dict[str, Any], override_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Merge two configuration dictionaries, with override taking precedence.
        
        Args:
            base_config: Base configuration dictionary
            override_config: Override configuration dictionary
            
        Returns:
            Dict: Merged configuration
        """
        merged = base_config.copy()
        
        for key, value in override_config.items():
            if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
                merged[key] = ConfigManager.merge_configs(merged[key], value)
            else:
                merged[key] = value
        
        return merged
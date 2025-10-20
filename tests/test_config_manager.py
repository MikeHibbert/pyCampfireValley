"""
Tests for the Configuration Management System components.
"""

import pytest
import asyncio
import tempfile
import os
import yaml
import json
from datetime import datetime
from unittest.mock import Mock, AsyncMock, patch, mock_open
from pathlib import Path

from campfirevalley.config_manager import (
    ConfigManager, ConfigFormat, ConfigScope, ConfigEnvironment,
    ConfigSource, ConfigValidationRule, ConfigChange, ConfigVersion,
    IConfigProvider, IConfigValidator, IConfigEncryption,
    FileConfigProvider, SchemaConfigValidator, SimpleConfigEncryption,
    get_config_manager, load_config_from_file, get_config_value, set_config_value
)


class TestConfigSource:
    """Test cases for ConfigSource dataclass"""
    
    def test_config_source_creation(self):
        """Test creating a config source"""
        source = ConfigSource(
            name="test_source",
            format=ConfigFormat.YAML,
            scope=ConfigScope.GLOBAL,
            priority=1,
            path="/path/to/config.yaml",
            environment=ConfigEnvironment.DEVELOPMENT,
            metadata={"description": "Test configuration"}
        )
        
        assert source.name == "test_source"
        assert source.format == ConfigFormat.YAML
        assert source.scope == ConfigScope.GLOBAL
        assert source.priority == 1
        assert source.path == "/path/to/config.yaml"
        assert source.environment == ConfigEnvironment.DEVELOPMENT
        assert source.metadata == {"description": "Test configuration"}


class TestConfigValidationRule:
    """Test cases for ConfigValidationRule dataclass"""
    
    def test_validation_rule_creation(self):
        """Test creating a validation rule"""
        rule = ConfigValidationRule(
            name="port_validation",
            path="server.port",
            rule_type="range",
            parameters={"min": 1024, "max": 65535},
            required=True,
            description="Validate server port range"
        )
        
        assert rule.name == "port_validation"
        assert rule.path == "server.port"
        assert rule.rule_type == "range"
        assert rule.parameters == {"min": 1024, "max": 65535}
        assert rule.required is True
        assert rule.description == "Validate server port range"


class TestConfigChange:
    """Test cases for ConfigChange dataclass"""
    
    def test_config_change_creation(self):
        """Test creating a config change"""
        timestamp = datetime.utcnow()
        
        change = ConfigChange(
            path="database.host",
            old_value="localhost",
            new_value="db.example.com",
            timestamp=timestamp,
            source="admin_update",
            reason="Environment migration"
        )
        
        assert change.path == "database.host"
        assert change.old_value == "localhost"
        assert change.new_value == "db.example.com"
        assert change.timestamp == timestamp
        assert change.source == "admin_update"
        assert change.reason == "Environment migration"


class TestConfigVersion:
    """Test cases for ConfigVersion dataclass"""
    
    def test_config_version_creation(self):
        """Test creating a config version"""
        timestamp = datetime.utcnow()
        
        version = ConfigVersion(
            version="1.2.3",
            timestamp=timestamp,
            changes=[
                ConfigChange(
                    path="app.debug",
                    old_value=True,
                    new_value=False,
                    timestamp=timestamp,
                    source="deployment"
                )
            ],
            description="Production deployment",
            checksum="abc123def456"
        )
        
        assert version.version == "1.2.3"
        assert version.timestamp == timestamp
        assert len(version.changes) == 1
        assert version.description == "Production deployment"
        assert version.checksum == "abc123def456"


class TestFileConfigProvider:
    """Test cases for FileConfigProvider"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.provider = FileConfigProvider()
    
    @pytest.mark.asyncio
    async def test_load_yaml_config(self):
        """Test loading YAML configuration"""
        yaml_content = """
        database:
          host: localhost
          port: 5432
          name: testdb
        app:
          debug: true
          workers: 4
        """
        
        with patch("builtins.open", mock_open(read_data=yaml_content)):
            with patch("os.path.exists", return_value=True):
                config = await self.provider.load_config("/path/to/config.yaml", ConfigFormat.YAML)
                
                assert config["database"]["host"] == "localhost"
                assert config["database"]["port"] == 5432
                assert config["app"]["debug"] is True
                assert config["app"]["workers"] == 4
    
    @pytest.mark.asyncio
    async def test_load_json_config(self):
        """Test loading JSON configuration"""
        json_content = """
        {
          "database": {
            "host": "localhost",
            "port": 5432
          },
          "app": {
            "debug": false
          }
        }
        """
        
        with patch("builtins.open", mock_open(read_data=json_content)):
            with patch("os.path.exists", return_value=True):
                config = await self.provider.load_config("/path/to/config.json", ConfigFormat.JSON)
                
                assert config["database"]["host"] == "localhost"
                assert config["database"]["port"] == 5432
                assert config["app"]["debug"] is False
    
    @pytest.mark.asyncio
    async def test_load_nonexistent_file(self):
        """Test loading non-existent file"""
        with patch("os.path.exists", return_value=False):
            config = await self.provider.load_config("/nonexistent/config.yaml", ConfigFormat.YAML)
            assert config == {}
    
    @pytest.mark.asyncio
    async def test_save_yaml_config(self):
        """Test saving YAML configuration"""
        config_data = {
            "database": {"host": "localhost", "port": 5432},
            "app": {"debug": True}
        }
        
        mock_file = mock_open()
        with patch("builtins.open", mock_file):
            with patch("os.makedirs"):
                await self.provider.save_config("/path/to/config.yaml", config_data, ConfigFormat.YAML)
                
                # Check that file was written
                mock_file.assert_called_once_with("/path/to/config.yaml", 'w', encoding='utf-8')
                written_content = "".join(call.args[0] for call in mock_file().write.call_args_list)
                
                # Parse written YAML to verify content
                parsed = yaml.safe_load(written_content)
                assert parsed["database"]["host"] == "localhost"
                assert parsed["app"]["debug"] is True
    
    @pytest.mark.asyncio
    async def test_save_json_config(self):
        """Test saving JSON configuration"""
        config_data = {
            "database": {"host": "localhost", "port": 5432},
            "app": {"debug": False}
        }
        
        mock_file = mock_open()
        with patch("builtins.open", mock_file):
            with patch("os.makedirs"):
                await self.provider.save_config("/path/to/config.json", config_data, ConfigFormat.JSON)
                
                # Check that file was written
                mock_file.assert_called_once_with("/path/to/config.json", 'w', encoding='utf-8')
                written_content = "".join(call.args[0] for call in mock_file().write.call_args_list)
                
                # Parse written JSON to verify content
                parsed = json.loads(written_content)
                assert parsed["database"]["host"] == "localhost"
                assert parsed["app"]["debug"] is False


class TestSchemaConfigValidator:
    """Test cases for SchemaConfigValidator"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.validator = SchemaConfigValidator()
        
        # Add test validation rules
        self.validator.add_rule(ConfigValidationRule(
            name="port_range",
            path="server.port",
            rule_type="range",
            parameters={"min": 1024, "max": 65535},
            required=True
        ))
        
        self.validator.add_rule(ConfigValidationRule(
            name="debug_type",
            path="app.debug",
            rule_type="type",
            parameters={"type": "boolean"},
            required=False
        ))
        
        self.validator.add_rule(ConfigValidationRule(
            name="database_host",
            path="database.host",
            rule_type="pattern",
            parameters={"pattern": r"^[a-zA-Z0-9.-]+$"},
            required=True
        ))
    
    @pytest.mark.asyncio
    async def test_validate_valid_config(self):
        """Test validating a valid configuration"""
        config = {
            "server": {"port": 8080},
            "app": {"debug": True},
            "database": {"host": "localhost"}
        }
        
        is_valid, errors = await self.validator.validate_config(config)
        
        assert is_valid is True
        assert len(errors) == 0
    
    @pytest.mark.asyncio
    async def test_validate_invalid_port_range(self):
        """Test validating configuration with invalid port range"""
        config = {
            "server": {"port": 80},  # Below minimum
            "app": {"debug": True},
            "database": {"host": "localhost"}
        }
        
        is_valid, errors = await self.validator.validate_config(config)
        
        assert is_valid is False
        assert len(errors) > 0
        assert any("port" in error.lower() for error in errors)
    
    @pytest.mark.asyncio
    async def test_validate_invalid_type(self):
        """Test validating configuration with invalid type"""
        config = {
            "server": {"port": 8080},
            "app": {"debug": "true"},  # Should be boolean
            "database": {"host": "localhost"}
        }
        
        is_valid, errors = await self.validator.validate_config(config)
        
        assert is_valid is False
        assert len(errors) > 0
        assert any("debug" in error.lower() for error in errors)
    
    @pytest.mark.asyncio
    async def test_validate_missing_required_field(self):
        """Test validating configuration with missing required field"""
        config = {
            "server": {"port": 8080},
            "app": {"debug": True}
            # Missing required database.host
        }
        
        is_valid, errors = await self.validator.validate_config(config)
        
        assert is_valid is False
        assert len(errors) > 0
        assert any("database.host" in error for error in errors)
    
    @pytest.mark.asyncio
    async def test_validate_invalid_pattern(self):
        """Test validating configuration with invalid pattern"""
        config = {
            "server": {"port": 8080},
            "app": {"debug": True},
            "database": {"host": "invalid host!"}  # Contains invalid characters
        }
        
        is_valid, errors = await self.validator.validate_config(config)
        
        assert is_valid is False
        assert len(errors) > 0
        assert any("database.host" in error for error in errors)
    
    def test_add_and_remove_rules(self):
        """Test adding and removing validation rules"""
        new_rule = ConfigValidationRule(
            name="test_rule",
            path="test.value",
            rule_type="range",
            parameters={"min": 0, "max": 100}
        )
        
        self.validator.add_rule(new_rule)
        assert "test_rule" in self.validator.rules
        
        self.validator.remove_rule("test_rule")
        assert "test_rule" not in self.validator.rules
    
    def test_get_rule(self):
        """Test getting a validation rule"""
        rule = self.validator.get_rule("port_range")
        assert rule is not None
        assert rule.name == "port_range"
        
        # Test non-existent rule
        assert self.validator.get_rule("nonexistent") is None


class TestSimpleConfigEncryption:
    """Test cases for SimpleConfigEncryption"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.encryption = SimpleConfigEncryption("test_secret_key_32_characters!")
    
    @pytest.mark.asyncio
    async def test_encrypt_decrypt_value(self):
        """Test encrypting and decrypting a value"""
        original_value = "sensitive_password_123"
        
        encrypted = await self.encryption.encrypt_value(original_value)
        assert encrypted != original_value
        assert encrypted.startswith("encrypted:")
        
        decrypted = await self.encryption.decrypt_value(encrypted)
        assert decrypted == original_value
    
    @pytest.mark.asyncio
    async def test_encrypt_decrypt_config(self):
        """Test encrypting and decrypting configuration"""
        config = {
            "database": {
                "host": "localhost",
                "password": "secret123"
            },
            "api": {
                "key": "api_key_456"
            }
        }
        
        sensitive_paths = ["database.password", "api.key"]
        
        encrypted_config = await self.encryption.encrypt_config(config, sensitive_paths)
        
        # Check that sensitive values are encrypted
        assert encrypted_config["database"]["password"].startswith("encrypted:")
        assert encrypted_config["api"]["key"].startswith("encrypted:")
        # Non-sensitive values should remain unchanged
        assert encrypted_config["database"]["host"] == "localhost"
        
        decrypted_config = await self.encryption.decrypt_config(encrypted_config)
        
        # Should match original config
        assert decrypted_config["database"]["password"] == "secret123"
        assert decrypted_config["api"]["key"] == "api_key_456"
        assert decrypted_config["database"]["host"] == "localhost"
    
    @pytest.mark.asyncio
    async def test_decrypt_non_encrypted_value(self):
        """Test decrypting a non-encrypted value"""
        normal_value = "not_encrypted"
        
        result = await self.encryption.decrypt_value(normal_value)
        assert result == normal_value  # Should return as-is


class TestConfigManager:
    """Test cases for ConfigManager"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.config_manager = ConfigManager()
    
    @pytest.mark.asyncio
    async def test_initialize(self):
        """Test config manager initialization"""
        await self.config_manager.initialize()
        
        assert self.config_manager.provider is not None
        assert self.config_manager.validator is not None
        assert self.config_manager.encryption is not None
    
    @pytest.mark.asyncio
    async def test_add_source(self):
        """Test adding a configuration source"""
        await self.config_manager.initialize()
        
        source = ConfigSource(
            name="test_source",
            format=ConfigFormat.YAML,
            scope=ConfigScope.GLOBAL,
            priority=1,
            path="/test/config.yaml"
        )
        
        self.config_manager.add_source(source)
        
        assert "test_source" in self.config_manager.sources
        assert self.config_manager.sources["test_source"] == source
    
    @pytest.mark.asyncio
    async def test_add_validation_rule(self):
        """Test adding a validation rule"""
        await self.config_manager.initialize()
        
        rule = ConfigValidationRule(
            name="test_rule",
            path="test.value",
            rule_type="range",
            parameters={"min": 0, "max": 100}
        )
        
        self.config_manager.add_validation_rule(rule)
        
        # Should be added to validator
        assert self.config_manager.validator.get_rule("test_rule") is not None
    
    @pytest.mark.asyncio
    async def test_load_configuration(self):
        """Test loading configuration from sources"""
        await self.config_manager.initialize()
        
        # Mock configuration data
        config_data = {
            "app": {"name": "TestApp", "debug": True},
            "database": {"host": "localhost", "port": 5432}
        }
        
        # Add mock source
        source = ConfigSource(
            name="test_source",
            format=ConfigFormat.YAML,
            scope=ConfigScope.GLOBAL,
            priority=1,
            path="/test/config.yaml"
        )
        self.config_manager.add_source(source)
        
        # Mock provider to return test data
        with patch.object(self.config_manager.provider, 'load_config', return_value=config_data):
            await self.config_manager.load_configuration()
            
            assert self.config_manager.config["app"]["name"] == "TestApp"
            assert self.config_manager.config["database"]["port"] == 5432
    
    @pytest.mark.asyncio
    async def test_get_config_value(self):
        """Test getting configuration values"""
        await self.config_manager.initialize()
        
        # Set up test configuration
        self.config_manager.config = {
            "app": {"name": "TestApp", "debug": True},
            "database": {"host": "localhost", "port": 5432}
        }
        
        # Test getting existing values
        assert self.config_manager.get("app.name") == "TestApp"
        assert self.config_manager.get("database.port") == 5432
        assert self.config_manager.get("app.debug") is True
        
        # Test getting non-existent value with default
        assert self.config_manager.get("app.nonexistent", "default") == "default"
        
        # Test getting non-existent value without default
        assert self.config_manager.get("app.nonexistent") is None
    
    @pytest.mark.asyncio
    async def test_set_config_value(self):
        """Test setting configuration values"""
        await self.config_manager.initialize()
        
        # Initialize with empty config
        self.config_manager.config = {}
        
        # Set values
        await self.config_manager.set("app.name", "NewApp")
        await self.config_manager.set("database.port", 3306)
        await self.config_manager.set("app.features.auth", True)
        
        # Verify values were set
        assert self.config_manager.get("app.name") == "NewApp"
        assert self.config_manager.get("database.port") == 3306
        assert self.config_manager.get("app.features.auth") is True
        
        # Check that change was recorded
        assert len(self.config_manager.change_history) == 3
    
    @pytest.mark.asyncio
    async def test_reload_configuration(self):
        """Test reloading configuration"""
        await self.config_manager.initialize()
        
        # Set up initial config
        self.config_manager.config = {"app": {"name": "OldApp"}}
        
        # Add source
        source = ConfigSource(
            name="test_source",
            format=ConfigFormat.YAML,
            scope=ConfigScope.GLOBAL,
            priority=1,
            path="/test/config.yaml"
        )
        self.config_manager.add_source(source)
        
        # Mock provider to return updated data
        updated_config = {"app": {"name": "UpdatedApp", "version": "2.0"}}
        
        with patch.object(self.config_manager.provider, 'load_config', return_value=updated_config):
            await self.config_manager.reload()
            
            assert self.config_manager.get("app.name") == "UpdatedApp"
            assert self.config_manager.get("app.version") == "2.0"
    
    @pytest.mark.asyncio
    async def test_configuration_validation(self):
        """Test configuration validation during loading"""
        await self.config_manager.initialize()
        
        # Add validation rule
        rule = ConfigValidationRule(
            name="port_validation",
            path="database.port",
            rule_type="range",
            parameters={"min": 1024, "max": 65535},
            required=True
        )
        self.config_manager.add_validation_rule(rule)
        
        # Add source
        source = ConfigSource(
            name="test_source",
            format=ConfigFormat.YAML,
            scope=ConfigScope.GLOBAL,
            priority=1,
            path="/test/config.yaml"
        )
        self.config_manager.add_source(source)
        
        # Test with invalid configuration
        invalid_config = {"database": {"port": 80}}  # Below minimum
        
        with patch.object(self.config_manager.provider, 'load_config', return_value=invalid_config):
            with pytest.raises(ValueError):  # Should raise validation error
                await self.config_manager.load_configuration()
    
    @pytest.mark.asyncio
    async def test_change_callbacks(self):
        """Test configuration change callbacks"""
        await self.config_manager.initialize()
        
        callback_called = False
        callback_path = None
        callback_old_value = None
        callback_new_value = None
        
        def test_callback(path, old_value, new_value):
            nonlocal callback_called, callback_path, callback_old_value, callback_new_value
            callback_called = True
            callback_path = path
            callback_old_value = old_value
            callback_new_value = new_value
        
        # Register callback
        self.config_manager.add_change_callback(test_callback)
        
        # Set initial value
        self.config_manager.config = {"app": {"debug": False}}
        
        # Change value
        await self.config_manager.set("app.debug", True)
        
        # Verify callback was called
        assert callback_called is True
        assert callback_path == "app.debug"
        assert callback_old_value is False
        assert callback_new_value is True
    
    @pytest.mark.asyncio
    async def test_version_management(self):
        """Test configuration version management"""
        await self.config_manager.initialize()
        
        # Set initial config
        self.config_manager.config = {"app": {"version": "1.0"}}
        
        # Create version
        await self.config_manager.create_version("1.0.0", "Initial version")
        
        # Make changes
        await self.config_manager.set("app.version", "1.1")
        await self.config_manager.set("app.debug", True)
        
        # Create new version
        await self.config_manager.create_version("1.1.0", "Added debug mode")
        
        # Check versions
        versions = self.config_manager.get_versions()
        assert len(versions) == 2
        assert versions[0].version == "1.0.0"
        assert versions[1].version == "1.1.0"
        assert len(versions[1].changes) == 2  # Two changes made


class TestGlobalFunctions:
    """Test cases for global convenience functions"""
    
    @pytest.mark.asyncio
    async def test_get_config_manager(self):
        """Test getting global config manager"""
        manager1 = get_config_manager()
        manager2 = get_config_manager()
        
        # Should return the same instance (singleton)
        assert manager1 is manager2
    
    @pytest.mark.asyncio
    async def test_load_config_from_file(self):
        """Test loading config from file"""
        yaml_content = """
        app:
          name: TestApp
          debug: true
        """
        
        with patch("builtins.open", mock_open(read_data=yaml_content)):
            with patch("os.path.exists", return_value=True):
                config = await load_config_from_file("/test/config.yaml")
                
                assert config["app"]["name"] == "TestApp"
                assert config["app"]["debug"] is True
    
    @pytest.mark.asyncio
    async def test_convenience_functions(self):
        """Test convenience functions"""
        # Mock the global config manager
        mock_manager = Mock()
        mock_manager.get = Mock(return_value="test_value")
        mock_manager.set = AsyncMock()
        
        with patch('campfirevalley.config_manager.get_config_manager', return_value=mock_manager):
            # Test get_config_value
            value = get_config_value("test.path", "default")
            assert value == "test_value"
            mock_manager.get.assert_called_once_with("test.path", "default")
            
            # Test set_config_value
            await set_config_value("test.path", "new_value")
            mock_manager.set.assert_called_once_with("test.path", "new_value")


# Integration tests
class TestConfigManagerIntegration:
    """Integration tests for the complete configuration management system"""
    
    @pytest.mark.asyncio
    async def test_full_configuration_workflow(self):
        """Test complete configuration management workflow"""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_file = os.path.join(temp_dir, "test_config.yaml")
            
            # Create test configuration file
            config_data = {
                "app": {"name": "TestApp", "debug": True, "port": 8080},
                "database": {"host": "localhost", "port": 5432}
            }
            
            with open(config_file, 'w') as f:
                yaml.dump(config_data, f)
            
            # Initialize config manager
            manager = ConfigManager()
            await manager.initialize()
            
            # Add validation rules
            manager.add_validation_rule(ConfigValidationRule(
                name="port_validation",
                path="app.port",
                rule_type="range",
                parameters={"min": 1024, "max": 65535},
                required=True
            ))
            
            # Add configuration source
            source = ConfigSource(
                name="test_config",
                format=ConfigFormat.YAML,
                scope=ConfigScope.GLOBAL,
                priority=1,
                path=config_file
            )
            manager.add_source(source)
            
            # Load configuration
            await manager.load_configuration()
            
            # Verify loaded values
            assert manager.get("app.name") == "TestApp"
            assert manager.get("app.debug") is True
            assert manager.get("database.host") == "localhost"
            
            # Test setting values
            await manager.set("app.version", "1.0.0")
            assert manager.get("app.version") == "1.0.0"
            
            # Test change history
            assert len(manager.change_history) == 1
            assert manager.change_history[0].path == "app.version"
            
            # Test version creation
            await manager.create_version("1.0.0", "Initial release")
            versions = manager.get_versions()
            assert len(versions) == 1
            assert versions[0].version == "1.0.0"
    
    @pytest.mark.asyncio
    async def test_multiple_sources_priority(self):
        """Test loading from multiple sources with different priorities"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create base config
            base_config_file = os.path.join(temp_dir, "base.yaml")
            base_config = {
                "app": {"name": "BaseApp", "debug": False, "port": 8080},
                "database": {"host": "localhost"}
            }
            with open(base_config_file, 'w') as f:
                yaml.dump(base_config, f)
            
            # Create override config
            override_config_file = os.path.join(temp_dir, "override.yaml")
            override_config = {
                "app": {"debug": True, "version": "1.0"},  # Override debug, add version
                "database": {"port": 5432}  # Add port
            }
            with open(override_config_file, 'w') as f:
                yaml.dump(override_config, f)
            
            # Initialize config manager
            manager = ConfigManager()
            await manager.initialize()
            
            # Add sources with different priorities
            base_source = ConfigSource(
                name="base",
                format=ConfigFormat.YAML,
                scope=ConfigScope.GLOBAL,
                priority=1,  # Lower priority
                path=base_config_file
            )
            
            override_source = ConfigSource(
                name="override",
                format=ConfigFormat.YAML,
                scope=ConfigScope.GLOBAL,
                priority=2,  # Higher priority
                path=override_config_file
            )
            
            manager.add_source(base_source)
            manager.add_source(override_source)
            
            # Load configuration
            await manager.load_configuration()
            
            # Verify merged configuration
            assert manager.get("app.name") == "BaseApp"  # From base
            assert manager.get("app.debug") is True  # Overridden
            assert manager.get("app.port") == 8080  # From base
            assert manager.get("app.version") == "1.0"  # From override
            assert manager.get("database.host") == "localhost"  # From base
            assert manager.get("database.port") == 5432  # From override


if __name__ == "__main__":
    pytest.main([__file__])
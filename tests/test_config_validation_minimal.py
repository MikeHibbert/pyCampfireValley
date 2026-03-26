import asyncio
import tempfile
from pathlib import Path
import yaml

from campfirevalley.config_manager import (
    ConfigManager,
    ConfigSource,
    ConfigFormat,
    ConfigScope,
    ConfigValidationRule,
)


async def write_yaml(path: Path, data: dict):
    path.write_text(yaml.dump(data), encoding="utf-8")


def test_validation_rules_pass_event_loop():
    async def _run():
        with tempfile.TemporaryDirectory() as tmp:
            cfg_path = Path(tmp) / "cfg.yaml"
            data = {"env": {"dock_mode": "private"}, "campfires": {"visible": []}}
            await write_yaml(cfg_path, data)

            manager = ConfigManager()
            # Add rules
            manager.add_validation_rule(
                ConfigValidationRule(field_path="env.dock_mode", rule_type="required")
            )
            manager.add_validation_rule(
                ConfigValidationRule(field_path="campfires.visible", rule_type="type", parameters={"type": list})
            )

            # Add source and load
            manager.add_source(
                ConfigSource(path=str(cfg_path), format=ConfigFormat.YAML, scope=ConfigScope.VALLEY, priority=1)
            )
            await manager.load_all_configs()
            val = await manager.get_config("env.dock_mode")
            assert val == "private"

    asyncio.run(_run())


def test_hot_reload_updates_config():
    async def _run():
        with tempfile.TemporaryDirectory() as tmp:
            cfg_path = Path(tmp) / "cfg.yaml"
            data = {"app": {"name": "Alpha"}}
            await write_yaml(cfg_path, data)

            manager = ConfigManager()
            manager.add_source(
                ConfigSource(path=str(cfg_path), format=ConfigFormat.YAML, scope=ConfigScope.GLOBAL, priority=1)
            )
            await manager.load_all_configs()
            assert (await manager.get_config("app.name")) == "Alpha"

            # Modify file to trigger watch
            await write_yaml(cfg_path, {"app": {"name": "Beta"}})
            # Wait a little for the watcher to fire
            await asyncio.sleep(2.5)
            assert (await manager.get_config("app.name")) == "Beta"

    asyncio.run(_run())


"""
Command-line interface for CampfireValley.
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path
from .valley import Valley
from .config import ConfigManager
from .daemon import DaemonState, run_with_pid


def setup_logging(level: str = "INFO"):
    """Setup logging configuration"""
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )


async def start_valley(args):
    """Start a valley instance"""
    print(f"Starting valley '{args.name}' with manifest: {args.manifest}")
    
    try:
        valley = Valley(args.name, args.manifest)
        await valley.start()
        
        print(f"Valley '{args.name}' started successfully")
        print("Press Ctrl+C to stop...")
        
        # Keep running until interrupted
        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            print("\nShutting down valley...")
            await valley.stop()
            print("Valley stopped")
            
    except Exception as e:
        print(f"Error starting valley: {e}")
        sys.exit(1)


def create_config(args):
    """Create a default configuration"""
    manifest_path = Path(args.output)
    
    if manifest_path.exists() and not args.force:
        print(f"Configuration file already exists: {manifest_path}")
        print("Use --force to overwrite")
        sys.exit(1)
    
    try:
        config = ConfigManager.create_default_valley_config(args.name)
        ConfigManager.save_valley_config(config, str(manifest_path))
        
        print(f"Created default configuration: {manifest_path}")
        
    except Exception as e:
        print(f"Error creating configuration: {e}")
        sys.exit(1)


def validate_config(args):
    """Validate a configuration file"""
    try:
        is_valid, error = ConfigManager.validate_config_syntax(args.config)
        
        if is_valid:
            # Try to load as valley config
            config = ConfigManager.load_valley_config(args.config)
            print(f"Configuration is valid: {args.config}")
            print(f"Valley name: {config.name}")
            print(f"Version: {config.version}")
        else:
            print(f"Configuration is invalid: {error}")
            sys.exit(1)
            
    except Exception as e:
        print(f"Error validating configuration: {e}")
        sys.exit(1)

def onboard(args):
    """Initialize local config directories, default manifests, and secrets"""
    base_dir = Path(".")
    config_dir = base_dir / "config"
    secrets_dir = base_dir / ".secrets"
    local_pid_dir = base_dir / ".campfirevalley"
    config_dir.mkdir(parents=True, exist_ok=True)
    secrets_dir.mkdir(parents=True, exist_ok=True)
    local_pid_dir.mkdir(parents=True, exist_ok=True)

    # Copy default/environment configs if missing
    package_config_dir = Path(__file__).parent.parent / "config"
    for name in ("default.yaml", "development.yaml", "production.yaml"):
        src = package_config_dir / name
        dst = config_dir / name
        if src.exists() and not dst.exists():
            dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")

    # Create manifest.yaml if missing
    manifest = base_dir / "manifest.yaml"
    if not manifest.exists():
        cfg = ConfigManager.create_default_valley_config(args.name)
        ConfigManager.save_valley_config(cfg, str(manifest))

    # Create pairing allowlist store
    allowlist = secrets_dir / "dm_allowlist.json"
    if not allowlist.exists():
        allowlist.write_text('{"channels": {}, "notes": "Populate with approved sender IDs"}', encoding="utf-8")

    print("Onboarding complete:")
    print(f"- Configs at {config_dir}")
    print(f"- Secrets at {secrets_dir}")
    print(f"- Manifest at {manifest}")
    print(f"- PID dir at {local_pid_dir}")

async def daemon_run(args):
    """Run valley with PID tracking (foreground)"""
    state = DaemonState(args.name)
    valley = Valley(args.name, args.manifest)
    await valley.start()
    print(f"Daemon running for '{args.name}'. PID file: {state.pid_file}")
    try:
        await run_with_pid(asyncio.sleep(10**9), state)  # long sleep, interrupted by Ctrl+C
    except KeyboardInterrupt:
        pass
    finally:
        await valley.stop()
        print("Daemon stopped")

def daemon_status(args):
    """Report daemon status"""
    state = DaemonState(args.name)
    pid = state.get_pid()
    if pid:
        print(f"Daemon status: RUNNING (pid file {state.pid_file}, pid {pid})")
    else:
        print("Daemon status: NOT RUNNING")

def main():
    """Main CLI entry point"""
    parser = argparse.ArgumentParser(
        description="CampfireValley - Distributed AI Agent Communities",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  campfirevalley start MyValley --manifest ./manifest.yaml
  campfirevalley create-config MyValley --output ./manifest.yaml
  campfirevalley validate-config ./manifest.yaml
  campfirevalley onboard MyValley
  campfirevalley daemon run MyValley --manifest ./manifest.yaml
        """
    )
    
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Set logging level"
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Start command
    start_parser = subparsers.add_parser("start", help="Start a valley instance")
    start_parser.add_argument("name", help="Valley name")
    start_parser.add_argument(
        "--manifest", 
        default="./manifest.yaml",
        help="Path to manifest.yaml file (default: ./manifest.yaml)"
    )
    
    # Create config command
    create_parser = subparsers.add_parser("create-config", help="Create default configuration")
    create_parser.add_argument("name", help="Valley name")
    create_parser.add_argument(
        "--output",
        default="./manifest.yaml", 
        help="Output file path (default: ./manifest.yaml)"
    )
    create_parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing configuration"
    )
    
    # Validate config command
    validate_parser = subparsers.add_parser("validate-config", help="Validate configuration file")
    validate_parser.add_argument("config", help="Path to configuration file")

    # Onboard command
    onboard_parser = subparsers.add_parser("onboard", help="Initialize local configs and secrets")
    onboard_parser.add_argument("name", help="Valley name")
    
    # Daemon command group
    daemon_parser = subparsers.add_parser("daemon", help="Run/status for gateway daemon")
    daemon_sub = daemon_parser.add_subparsers(dest="daemon_cmd", help="Daemon actions")
    daemon_run_parser = daemon_sub.add_parser("run", help="Run foreground with PID tracking")
    daemon_run_parser.add_argument("name", help="Valley name")
    daemon_run_parser.add_argument(
        "--manifest", 
        default="./manifest.yaml",
        help="Path to manifest.yaml file (default: ./manifest.yaml)"
    )
    daemon_status_parser = daemon_sub.add_parser("status", help="Show daemon status")
    daemon_status_parser.add_argument("name", help="Valley name")
    
    args = parser.parse_args()
    
    # Setup logging
    setup_logging(args.log_level)
    
    # Execute command
    if args.command == "start":
        asyncio.run(start_valley(args))
    elif args.command == "create-config":
        create_config(args)
    elif args.command == "validate-config":
        validate_config(args)
    elif args.command == "onboard":
        onboard(args)
    elif args.command == "daemon":
        if args.daemon_cmd == "run":
            asyncio.run(daemon_run(args))
        elif args.daemon_cmd == "status":
            daemon_status(args)
        else:
            print("Specify a daemon action: run|status")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

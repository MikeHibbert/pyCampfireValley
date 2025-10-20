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
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
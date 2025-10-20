# CampfireValley

A Python library that extends the Campfires framework by introducing the concept of "valleys" as interconnected, secure communities of campfires. The library manages docks as gateways for inter-valley communication, handles riverboat (torch) exchanges via MCP, and provides default campfires for loading/offloading, security sanitization, and justice enforcement.

## 🚀 Project Status

**Phase 1 Implementation: COMPLETED** ✅

CampfireValley is currently **~60% complete** with core infrastructure implemented and tested. The foundation is solid and ready for Phase 2 development.

### ✅ Completed Components

- **🔐 Key Manager**: Complete AES-256 and RSA key management system
- **🔄 Redis MCP Broker**: Full pub/sub messaging with connection management  
- **📦 Torch Serialization**: Enhanced with Redis transport and MCP communication
- **🏭 Dockmaster Campfire**: Complete with Loader, Router, and Packer campers
- **🏗️ Core Architecture**: Interfaces, models, and base classes

### 🔄 In Development (Phase 2)

- **VALI Services**: Security scanning and validation
- **Justice System**: Access control and violation handling
- **Specialist Campfires**: Domain-specific processing units
- **Advanced Routing**: Multi-hop and load balancing
- **Web Interface**: Management dashboard

## Features

- **Valley Management**: Self-contained instances hosting multiple campfires
- **Dock Gateways**: Secure entry points for inter-valley communication
- **MCP Integration**: Redis-based message communication protocol
- **Party Box Storage**: Hierarchical storage for torch payloads and attachments
- **Security Framework**: Built-in sanitization and access control
- **GitHub Actions-style Configuration**: Familiar YAML configuration format

## Quick Start

### Installation

```bash
pip install campfirevalley
```

### Basic Usage

1. **Create a valley configuration**:
```bash
campfirevalley create-config MyValley --output manifest.yaml
```

2. **Start a valley**:
```bash
campfirevalley start MyValley --manifest manifest.yaml
```

3. **Programmatic usage**:
```python
import asyncio
from campfirevalley import Valley

async def main():
    # Create and start a valley
    valley = Valley("MyValley", "./manifest.yaml")
    await valley.start()
    
    # Valley is now running and can communicate with other valleys
    print(f"Valley '{valley.name}' is running")
    
    # Stop the valley
    await valley.stop()

asyncio.run(main())
```

## 🏗️ Phase 1 Implementation Details

### Key Manager (`campfirevalley.key_manager`)
- **AES-256 Encryption**: Secure payload encryption/decryption
- **RSA Digital Signatures**: Torch signing and verification
- **Key Rotation**: Community-based key management
- **Secure Storage**: Encrypted key storage in `.secrets/`

### Redis MCP Broker (`campfirevalley.mcp`)
- **Pub/Sub Messaging**: Redis-based inter-valley communication
- **Connection Management**: Robust connection pooling and error handling
- **Message Routing**: Channel-based message distribution
- **Async Support**: Full asyncio compatibility

### Enhanced Torch Model (`campfirevalley.models`)
- **Redis Serialization**: Optimized for Redis transport
- **MCP Envelopes**: Structured message format
- **Compression**: Automatic compression for large payloads
- **Routing Channels**: Smart channel determination

### Dockmaster Campfire (`campfirevalley.campfires.dockmaster`)
- **LoaderCamper**: Torch validation and unpacking
- **RouterCamper**: Intelligent routing decisions
- **PackerCamper**: Transport preparation and packaging
- **Pipeline Processing**: Complete torch processing workflow

### Usage Example

```python
import asyncio
from campfirevalley import Valley, CampfireKeyManager, RedisMCPBroker
from campfirevalley.campfires import DockmasterCampfire
from campfirevalley.models import Torch

async def main():
    # Initialize components
    key_manager = CampfireKeyManager("MyValley")
    mcp_broker = RedisMCPBroker("redis://localhost:6379")
    dockmaster = DockmasterCampfire(mcp_broker)
    
    # Start services
    await mcp_broker.connect()
    await dockmaster.start()
    
    # Create and process a torch
    torch = Torch(
        id="example_001",
        sender_valley="MyValley",
        target_address="TargetValley:dockmaster/loader",
        payload={"message": "Hello from CampfireValley!"},
        signature="example_signature"
    )
    
    # Process through Dockmaster pipeline
    response = await dockmaster.process_torch(torch)
    print(f"Processed torch: {response}")
    
    # Cleanup
    await dockmaster.stop()
    await mcp_broker.disconnect()

asyncio.run(main())
```

## Configuration

CampfireValley uses GitHub Actions-style YAML configuration:

```yaml
name: "MyValley"
version: "1.0"

env:
  dock_mode: "public"
  security_level: "standard"
  auto_create_dock: true

campfires:
  visible: ["helper", "processor"]
  hidden: ["internal"]

community:
  discovery: true
  trusted_valleys: ["FriendValley"]
```

## Architecture

- **Valley**: Main container managing campfires and infrastructure
- **Dock**: Gateway for inter-valley communication
- **Campfire**: Individual AI agent containers
- **Torch**: Message format for inter-valley communication
- **Party Box**: Storage system for attachments and payloads
- **MCP Broker**: Redis-based message routing

## Development

### Requirements

- Python 3.8+
- Redis server (for MCP broker)
- PyYAML, Pydantic, cryptography

### Running Tests

```bash
pip install -e ".[dev]"
pytest
```

## License

MIT License - see LICENSE file for details.
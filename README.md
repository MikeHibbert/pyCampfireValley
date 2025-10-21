# CampfireValley

A Python library that extends the Campfires framework by introducing the concept of "valleys" as interconnected, secure communities of campfires. The library manages docks as gateways for inter-valley communication, handles riverboat (torch) exchanges via MCP, and provides default campfires for loading/offloading, security sanitization, and justice enforcement.

## 🚀 Project Status

**Phase 2 Implementation: COMPLETED** ✅

CampfireValley is now **~95% complete** with comprehensive enterprise-grade features implemented and tested. The system provides a complete distributed torch processing framework.

### ✅ Phase 1 Components (Core Infrastructure)

- **🔐 Key Manager**: Complete AES-256 and RSA key management system
- **🔄 Redis MCP Broker**: Full pub/sub messaging with connection management  
- **📦 Torch Serialization**: Enhanced with Redis transport and MCP communication
- **🏭 Dockmaster Campfire**: Complete with Loader, Router, and Packer campers
- **🏗️ Core Architecture**: Interfaces, models, and base classes

### ✅ Phase 2 Components (Enterprise Features)

- **🛡️ VALI Services**: Complete security scanning and validation framework
- **⚖️ Justice System**: Advanced policy enforcement and violation handling
- **🔧 Specialist Campfires**: Domain-specific processing units (Sanitizer, Validator, Router)
- **🌐 Advanced Routing**: Multi-hop routing with load balancing and failover
- **📊 Monitoring & Logging**: Comprehensive metrics, alerts, and structured logging
- **⚙️ Configuration Management**: Multi-environment config with validation and encryption
- **💾 Hierarchical Storage**: Multi-tier storage with compression and deduplication

### 🔄 Future Enhancements

- **Web Interface**: Management dashboard and monitoring UI
- **Distributed Consensus**: Multi-valley coordination protocols
- **Machine Learning**: Intelligent routing and threat detection

## Features

### Core Infrastructure (Phase 1)
- **Valley Management**: Self-contained instances hosting multiple campfires
- **Dock Gateways**: Secure entry points for inter-valley communication
- **MCP Integration**: Redis-based message communication protocol
- **Key Management**: AES-256 encryption and RSA digital signatures
- **GitHub Actions-style Configuration**: Familiar YAML configuration format

### Enterprise Features (Phase 2)
- **🛡️ VALI Security Services**: 
  - Content validation and signature verification
  - Enhanced security scanning with threat detection
  - Service registry and coordination
- **⚖️ Justice System**: 
  - Policy-based access control and enforcement
  - Violation detection and automated responses
  - Rate limiting and abuse prevention
- **🔧 Specialist Campfires**: 
  - Sanitizer: Content cleaning and threat removal
  - Validator: Data integrity and format validation
  - Router: Intelligent routing decisions
- **🌐 Advanced Routing**: 
  - Multi-hop routing with path optimization
  - Smart load balancing algorithms
  - Automatic failover and health checking
- **📊 Monitoring & Logging**: 
  - Real-time metrics collection and alerting
  - Structured logging with multiple handlers
  - Performance monitoring and health checks
- **⚙️ Configuration Management**: 
  - Multi-environment configuration (dev/prod)
  - Schema validation and encryption
  - Hot-reload and change tracking
- **💾 Hierarchical Storage**: 
  - Multi-tier storage (hot/warm/cold/archive)
  - Data deduplication and compression
  - Intelligent lifecycle management

## 🚀 Getting Started

### Quick Start with Docker

1. **Clone and setup**:
   ```bash
   git clone https://github.com/MikeHibbert/pyCampfireValley.git
   cd pyCampfireValley
   cp .env.example .env
   # Edit .env with your API keys
   ```

2. **Start the server**:
   ```bash
   docker-compose up --build
   ```

3. **Access the web interface**:
   - Open your browser to: http://localhost:8000
   - View the LiteGraph canvas with campfire nodes
   - Monitor real-time campfire processes

### Server Components

The CampfireValley server includes:

- **Web Interface**: LiteGraph-based visual campfire management at http://localhost:8000
- **Valley Management**: Core campfire orchestration and routing
- **Redis**: Inter-campfire communication and caching
- **Monitoring**: Real-time metrics and health monitoring

## 📋 Valley Configuration with Manifests

CampfireValley uses GitHub Actions-style YAML manifests to configure valleys and their campfires. You can easily change your valley's behavior by supplying different manifest files.

### Basic Manifest Structure

Create a `manifest.yaml` file in your project root:

```yaml
# Valley Configuration Manifest
name: "MyValley"
version: "1.0"

# Environment settings
env:
  dock_mode: "public"          # public, partial, private
  security_level: "standard"   # basic, standard, high
  auto_create_dock: true

# Define visible and hidden campfires
campfires:
  visible: ["welcome", "helper", "analyzer"]
  hidden: ["internal-audit", "security-scanner"]

# Dock gateway configuration
dock:
  steps:
    - name: "Initialize gateway"
      uses: "dock/gateway@v1"
      with:
        port: 6379
        encryption: true
    - name: "Setup discovery"
      uses: "dock/discovery@v1"
      if: "${{ env.dock_mode == 'public' }}"
      with:
        broadcast_interval: 30

# Community and networking
community:
  discovery: true
  trusted_valleys: ["FriendlyValley", "HelperValley"]
```

### Changing Valley Tasks with Different Manifests

You can completely change your valley's purpose by using different manifest configurations:

#### 1. **Development Valley** (`manifest-dev.yaml`)
```yaml
name: "DevValley"
version: "1.0"
env:
  dock_mode: "private"
  security_level: "basic"
  auto_create_dock: true
campfires:
  visible: ["code-reviewer", "test-runner", "documentation"]
  hidden: ["debug-logger"]
community:
  discovery: false
  trusted_valleys: []
```

#### 2. **Marketing Valley** (`manifest-marketing.yaml`)
```yaml
name: "MarketingValley"
version: "1.0"
env:
  dock_mode: "public"
  security_level: "standard"
  auto_create_dock: true
campfires:
  visible: ["content-creator", "social-media", "analytics"]
  hidden: ["competitor-analysis"]
community:
  discovery: true
  trusted_valleys: ["ContentValley", "AnalyticsValley"]
```

#### 3. **Security Valley** (`manifest-security.yaml`)
```yaml
name: "SecurityValley"
version: "1.0"
env:
  dock_mode: "private"
  security_level: "high"
  auto_create_dock: false
campfires:
  visible: ["threat-detector", "vulnerability-scanner"]
  hidden: ["forensics", "incident-response", "audit-logger"]
community:
  discovery: false
  trusted_valleys: []
```

### Using Different Manifests

To switch between different valley configurations:

1. **Method 1: Replace the default manifest**
   ```bash
   cp manifest-marketing.yaml manifest.yaml
   docker-compose restart
   ```

2. **Method 2: Specify manifest path in code**
   ```python
   from campfirevalley import Valley
   
   # Load specific manifest
   valley = Valley("MyValley", manifest_path="./manifest-security.yaml")
   await valley.start()
   ```

3. **Method 3: Environment variable**
   ```bash
   export CAMPFIRE_MANIFEST_PATH="./manifest-dev.yaml"
   docker-compose up --build
   ```

### Advanced Configuration

For more complex setups, you can use the full configuration system:

```yaml
# Advanced manifest with specialist campfires
name: "EnterpriseValley"
version: "2.0"

env:
  dock_mode: "partial"
  security_level: "high"
  auto_create_dock: true
  enable_monitoring: true
  enable_justice: true

# Specialist campfire configurations
campfires:
  visible: ["sanitizer", "validator", "router"]
  hidden: ["justice-enforcer", "metrics-collector"]

# Advanced dock configuration
dock:
  steps:
    - name: "Initialize secure gateway"
      uses: "dock/gateway@v2"
      with:
        port: 6379
        encryption: true
        auth_required: true
    - name: "Setup load balancer"
      uses: "dock/loadbalancer@v1"
      with:
        strategy: "round_robin"
        health_check: true
    - name: "Enable monitoring"
      uses: "dock/monitoring@v1"
      with:
        metrics_endpoint: "/metrics"
        alerts_enabled: true

# Justice system policies
justice:
  policies:
    - name: "rate_limiting"
      max_requests_per_minute: 100
    - name: "content_filtering"
      blocked_patterns: ["spam", "malware"]

community:
  discovery: true
  trusted_valleys: ["SecurityValley", "MonitoringValley"]
  federation_enabled: true
```

### Configuration Validation

CampfireValley automatically validates your manifest files:

```python
from campfirevalley.config import ConfigManager

# Validate manifest before using
try:
    config = ConfigManager.load_valley_config("./my-manifest.yaml")
    print("✅ Manifest is valid!")
except ValueError as e:
    print(f"❌ Invalid manifest: {e}")
```

## 🎯 Demos & Examples

CampfireValley includes comprehensive demos showcasing real-world AI agent collaboration workflows. These demos demonstrate the complete system capabilities from idea generation to technical implementation.

### 🚀 Marketing Team Demo

The marketing team demo showcases a complete AI-driven workflow where marketing strategists generate innovative ideas and collaborate with development teams to create technical implementations.

#### Demo Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│  Marketing      │    │   Development    │    │   Generated     │
│  Strategist     │───▶│   Team API       │───▶│   Report        │
│  (AI Agent)     │    │  (Dockerized)    │    │   (JSON/HTML)   │
└─────────────────┘    └──────────────────┘    └─────────────────┘
```

#### Quick Demo Execution

**Option 1: Simplified Demo (Recommended)**
```bash
# Start Docker containers
docker-compose up -d

# Run the simplified marketing demo
python simple_marketing_demo.py
```

**Option 2: Full Valley Demo**
```bash
# Start Docker containers
docker-compose up -d

# Run the complete valley demo
python demo_marketing_team.py
```

#### Demo Workflow

1. **Idea Generation**: Marketing strategist AI generates innovative business ideas
2. **Strategic Analysis**: Each idea is analyzed for market potential and feasibility
3. **Development Requests**: Ideas are formatted and sent to the development team API
4. **Technical Analysis**: Development team provides detailed technical requirements
5. **Report Generation**: Complete workflow results are compiled into comprehensive reports

#### Expected Output

The demo generates:
- **3 Marketing Ideas**: E-commerce Innovation, SaaS Solution, Mobile App Concept
- **Strategic Analysis**: Market research, target audience, competitive analysis
- **Technical Requirements**: Architecture, features, UX considerations
- **Development Analysis**: Detailed technical implementation plans
- **Comprehensive Report**: JSON and HTML formats with complete workflow results

#### Demo Files

- `simple_marketing_demo.py`: Streamlined demo bypassing MCP complexities
- `demo_marketing_team.py`: Full valley implementation with MCP integration
- `development_team_server.py`: Dockerized development team API service
- `docker-compose.yml`: Container orchestration for demo services

### 🐳 Docker Container Services

The demo utilizes several containerized services:

| Service | Container | Port | Purpose |
|---------|-----------|------|---------|
| Development Team | `campfire-development-team` | 8080 | Technical analysis API |
| Redis MCP Broker | `campfire-redis` | 6379 | Message communication |
| Ollama LLM | `campfire-ollama` | 11434 | Local AI model serving |
| Prometheus | `campfire-prometheus` | 9090 | Monitoring and metrics |

#### Container Status Check
```bash
# View running containers
docker ps

# Check container logs
docker logs campfire-development-team
docker logs campfire-redis
```

### 🔧 Troubleshooting

#### Common Issues and Solutions

**1. MCP Broker Connection Issues**
```bash
# Symptom: Demo hangs at "Subscribing to MCP channels"
# Solution: Use simplified demo
python simple_marketing_demo.py
```

**2. Docker Container Issues**
```bash
# Restart all containers
docker-compose down
docker-compose up -d

# Check container health
docker ps
```

**3. Development Team API 404 Errors**
```bash
# Verify development team container is running
docker logs campfire-development-team

# Check API endpoint
curl http://localhost:8080/api/develop_website
```

**4. Port Conflicts**
```bash
# Check port usage
netstat -an | findstr :8080
netstat -an | findstr :6379

# Modify ports in docker-compose.yml if needed
```

#### Demo Variations

**Simplified Workflow (No MCP)**
- Bypasses MCP broker subscription issues
- Direct API communication
- Faster execution
- Recommended for demonstrations

**Full Valley Workflow (With MCP)**
- Complete CampfireValley architecture
- MCP broker integration
- Inter-valley communication
- Production-like environment

### 📊 Demo Reports

Demo execution generates detailed reports:

**JSON Report Structure**:
```json
{
  "execution_summary": {
    "ideas_generated": 3,
    "dev_requests_sent": 3,
    "successful_responses": 3,
    "execution_time": "45.2 seconds"
  },
  "marketing_ideas": [...],
  "development_analysis": [...],
  "workflow_metrics": {...}
}
```

**Report Locations**:
- `simplified_marketing_report_YYYYMMDD_HHMMSS.json`
- `marketing_team_report.html` (if HTML generation enabled)

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

## 🏗️ Phase 2 Implementation Details

### VALI Services (`campfirevalley.vali`)
- **Service Registry**: Centralized service discovery and management
- **Content Validator**: Deep content analysis and validation
- **Signature Verifier**: Cryptographic signature verification
- **Security Scanner**: Advanced threat detection with multiple engines
- **Coordinator**: Service orchestration and lifecycle management

### Justice System (`campfirevalley.justice`)
- **Policy Engine**: Rule-based access control and enforcement
- **Enforcement Engine**: Automated violation response and remediation
- **Violation Detection**: Real-time monitoring and threat identification
- **Rate Limiting**: Configurable rate limiting and abuse prevention
- **Audit Trail**: Complete violation and enforcement logging

### Specialist Campfires (`campfirevalley.specialist_campfires`)
- **SanitizerCampfire**: Content sanitization with multiple levels
- **ValidatorCampfire**: Data validation with custom rules
- **RouterCampfire**: Intelligent routing with strategy selection
- **Configurable Rules**: Custom sanitization, validation, and routing rules
- **Pipeline Integration**: Seamless integration with torch processing

### Advanced Routing (`campfirevalley.routing`)
- **Route Optimization**: Intelligent path selection and optimization
- **Load Balancing**: Multiple algorithms (round-robin, weighted, least-connections)
- **Health Checking**: Continuous endpoint health monitoring
- **Failover Strategies**: Automatic failover with multiple strategies
- **Metrics Collection**: Real-time routing performance metrics

### Monitoring & Logging (`campfirevalley.monitoring`)
- **Metrics System**: Comprehensive metrics collection and aggregation
- **Alert Management**: Configurable alerts with multiple severity levels
- **Structured Logging**: JSON-based logging with multiple handlers
- **Performance Monitoring**: Real-time performance tracking
- **Health Checking**: System-wide health monitoring

### Configuration Management (`campfirevalley.config_manager`)
- **Multi-Environment**: Separate configs for development, production, etc.
- **Schema Validation**: JSON Schema-based configuration validation
- **Encryption Support**: Sensitive configuration data encryption
- **Hot Reload**: Runtime configuration updates without restart
- **Change Tracking**: Complete configuration change history

### Hierarchical Storage (`campfirevalley.hierarchical_storage`)
- **Multi-Tier Storage**: Hot, warm, cold, and archive tiers
- **Data Lifecycle**: Intelligent data movement between tiers
- **Deduplication**: Content-based deduplication to save space
- **Compression**: Configurable compression algorithms
- **Storage Optimization**: Automated storage optimization and cleanup

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

## 🔧 Configuration-Driven Architecture

CampfireValley implements a comprehensive configuration-driven approach that enables flexible, maintainable, and environment-specific deployments without code changes.

### Core Configuration Philosophy

The system follows these key principles:
- **Declarative Configuration**: Define what you want, not how to achieve it
- **Environment Separation**: Clean separation between dev, staging, and production
- **Schema Validation**: All configurations are validated against JSON schemas
- **Hot Reload**: Runtime configuration updates without service restart
- **Encryption Support**: Sensitive data is automatically encrypted

### Configuration Hierarchy

CampfireValley uses a multi-layered configuration system:

1. **Base Configuration**: Core system defaults
2. **Environment Configuration**: Environment-specific overrides (dev/prod)
3. **Valley Configuration**: Valley-specific settings
4. **Runtime Configuration**: Dynamic updates during operation

### GitHub Actions-Style YAML Format

CampfireValley uses familiar GitHub Actions-style YAML configuration:

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

# Advanced configuration sections
security:
  vali:
    enabled: true
    scan_level: "comprehensive"
    threat_detection: true
  
  justice:
    enabled: true
    policy_enforcement: "strict"
    rate_limiting:
      requests_per_minute: 100
      burst_limit: 20

routing:
  strategy: "intelligent"
  load_balancing: "weighted_round_robin"
  health_checks:
    enabled: true
    interval: 30
    timeout: 5

storage:
  hierarchical:
    enabled: true
    tiers:
      hot: { retention: "7d", compression: false }
      warm: { retention: "30d", compression: "lz4" }
      cold: { retention: "1y", compression: "gzip" }
      archive: { retention: "7y", compression: "bzip2" }

monitoring:
  metrics:
    enabled: true
    collection_interval: 10
  
  logging:
    level: "INFO"
    format: "json"
    handlers: ["console", "file", "redis"]
  
  alerts:
    enabled: true
    channels: ["email", "slack"]
```

### Environment-Specific Configuration

Create separate configuration files for different environments:

**config/dev.yaml**:
```yaml
extends: "base.yaml"

env:
  security_level: "development"
  debug: true

monitoring:
  logging:
    level: "DEBUG"

security:
  vali:
    scan_level: "basic"
```

**config/prod.yaml**:
```yaml
extends: "base.yaml"

env:
  security_level: "maximum"
  debug: false

security:
  vali:
    scan_level: "comprehensive"
    threat_detection: true
  
  justice:
    policy_enforcement: "strict"

monitoring:
  alerts:
    enabled: true
    severity_threshold: "warning"
```

### Configuration Management Features

#### 1. Schema Validation
All configurations are validated against JSON schemas:

```python
from campfirevalley.config_manager import ConfigManager

# Load and validate configuration
config_manager = ConfigManager()
config = config_manager.load_config("config/prod.yaml")
# Automatically validates against schema
```

#### 2. Encryption Support
Sensitive configuration data is automatically encrypted:

```yaml
database:
  host: "db.example.com"
  username: "admin"
  password: "!encrypted:AES256:base64encodeddata"  # Auto-encrypted
```

#### 3. Hot Reload
Update configurations without restarting services:

```python
# Configuration changes are automatically detected and applied
config_manager.watch_for_changes()
```

#### 4. Environment Variables
Override any configuration value with environment variables:

```bash
export CAMPFIREVALLEY_SECURITY_LEVEL="maximum"
export CAMPFIREVALLEY_MONITORING_LOGGING_LEVEL="ERROR"
```

### Configuration Sections Reference

#### Core Settings
- `name`: Valley identifier
- `version`: Configuration version
- `env`: Environment variables and basic settings

#### Security Configuration
- `security.vali`: VALI security services settings
- `security.justice`: Justice system and policy enforcement
- `security.encryption`: Encryption and key management

#### Routing Configuration
- `routing.strategy`: Routing algorithm selection
- `routing.load_balancing`: Load balancing configuration
- `routing.health_checks`: Health monitoring settings

#### Storage Configuration
- `storage.hierarchical`: Multi-tier storage settings
- `storage.compression`: Compression algorithms
- `storage.retention`: Data retention policies

#### Monitoring Configuration
- `monitoring.metrics`: Metrics collection settings
- `monitoring.logging`: Logging configuration
- `monitoring.alerts`: Alert management

### Best Practices

1. **Use Environment Inheritance**: Extend base configurations for environments
2. **Validate Early**: Always validate configurations during startup
3. **Encrypt Secrets**: Use the built-in encryption for sensitive data
4. **Monitor Changes**: Enable configuration change tracking
5. **Test Configurations**: Validate configurations in CI/CD pipelines

### Configuration Examples

See the `examples/` directory for complete configuration examples:
- `examples/basic_valley.yaml`: Simple valley setup
- `examples/enterprise_valley.yaml`: Full enterprise configuration
- `examples/development.yaml`: Development environment setup
- `examples/production.yaml`: Production-ready configuration

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

## Additional Documentation

- **[Demo Guide](DEMO_GUIDE.md)**: Comprehensive guide for executing demos and examples
- **[Deployment Guide](DEPLOYMENT.md)**: Detailed deployment instructions and Docker setup
- **[Troubleshooting Guide](TROUBLESHOOTING.md)**: Solutions for common issues and MCP broker problems

## Support

If you encounter issues:

1. Check the [Troubleshooting Guide](TROUBLESHOOTING.md) for common problems
2. Review the [Demo Guide](DEMO_GUIDE.md) for step-by-step execution instructions
3. Use the simplified demo (`simple_marketing_demo.py`) to bypass MCP broker issues
4. Check Docker container logs: `docker-compose logs [service-name]`

## License

MIT License - see LICENSE file for details.
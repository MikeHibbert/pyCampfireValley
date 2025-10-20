# CampfireValley Demo Execution Guide

This comprehensive guide provides step-by-step instructions for executing CampfireValley demos, showcasing AI agent collaboration workflows and enterprise features.

## 📋 Table of Contents

- [Overview](#overview)
- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
- [Demo Scenarios](#demo-scenarios)
- [Troubleshooting](#troubleshooting)
- [Advanced Configuration](#advanced-configuration)
- [Performance Optimization](#performance-optimization)

## 🎯 Overview

CampfireValley demos demonstrate real-world AI agent collaboration scenarios:

- **Marketing Team Demo**: AI-driven idea generation and technical analysis
- **Development Workflow**: Complete software development lifecycle simulation
- **Enterprise Integration**: Multi-service collaboration and communication

### Demo Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   AI Agents     │    │   Docker         │    │   Generated     │
│   (Marketing)   │───▶│   Services       │───▶│   Reports       │
│                 │    │   (Dev Team)     │    │   (JSON/HTML)   │
└─────────────────┘    └──────────────────┘    └─────────────────┘
```

## 🔧 Prerequisites

### System Requirements

**Minimum Requirements**:
- **OS**: Windows 10/11, macOS 10.15+, or Linux (Ubuntu 20.04+)
- **RAM**: 8GB
- **Storage**: 10GB free space
- **Network**: Internet connection for Docker images

**Recommended Requirements**:
- **RAM**: 16GB+
- **Storage**: 20GB+ SSD
- **CPU**: 4+ cores

### Software Dependencies

1. **Docker & Docker Compose**
   ```bash
   # Windows (PowerShell as Administrator)
   winget install Docker.DockerDesktop
   
   # macOS
   brew install --cask docker
   
   # Linux (Ubuntu)
   sudo apt update
   sudo apt install docker.io docker-compose
   ```

2. **Python 3.8+**
   ```bash
   # Windows
   winget install Python.Python.3.11
   
   # macOS
   brew install python@3.11
   
   # Linux
   sudo apt install python3.11 python3.11-pip
   ```

3. **Git**
   ```bash
   # Windows
   winget install Git.Git
   
   # macOS
   brew install git
   
   # Linux
   sudo apt install git
   ```

### Project Setup

1. **Clone Repository**
   ```bash
   git clone https://github.com/your-org/campfirevalley.git
   cd campfirevalley
   ```

2. **Install Python Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Verify Installation**
   ```bash
   python -c "import campfirevalley; print('CampfireValley installed successfully')"
   ```

## 🚀 Quick Start

### Option 1: Simplified Demo (Recommended for First-Time Users)

This option bypasses MCP complexities and provides immediate results.

```bash
# 1. Start Docker services
docker-compose up -d

# 2. Wait for services to be ready (30-60 seconds)
docker-compose ps

# 3. Run simplified marketing demo
python simple_marketing_demo.py

# 4. View results
# Check console output and generated report files
```

**Expected Output**:
```
🚀 Starting Simplified Marketing Demo...
📝 Generating marketing ideas...
✅ Generated 3 marketing ideas
🔄 Sending requests to development team...
✅ Sent 3 development requests
📊 Generating comprehensive report...
✅ Demo completed successfully!

📄 Report saved: simplified_marketing_report_20241020_160542.json
```

### Option 2: Full Valley Demo (Advanced Users)

This option demonstrates the complete CampfireValley architecture.

```bash
# 1. Start Docker services
docker-compose up -d

# 2. Verify all services are healthy
./scripts/health_check.sh

# 3. Run full valley demo
python demo_marketing_team.py

# 4. Monitor progress
tail -f logs/valley.log
```

## 🎬 Demo Scenarios

### Marketing Team Demo

**Scenario**: AI marketing strategist generates business ideas and collaborates with development team for technical analysis.

#### Step-by-Step Execution

1. **Environment Preparation**
   ```bash
   # Check Docker status
   docker --version
   docker-compose --version
   
   # Start services
   docker-compose up -d
   
   # Verify services
   docker-compose ps
   ```

2. **Service Health Verification**
   ```bash
   # Development Team API
   curl http://localhost:8080/health
   # Expected: {"status": "healthy", "service": "development-team"}
   
   # Redis MCP Broker
   docker exec campfire-redis redis-cli ping
   # Expected: PONG
   
   # Ollama LLM Service
   curl http://localhost:11434/api/tags
   # Expected: {"models": [...]}
   ```

3. **Demo Execution**
   ```bash
   # Run simplified demo
   python simple_marketing_demo.py
   
   # Alternative: Run with verbose logging
   python simple_marketing_demo.py --verbose
   
   # Alternative: Run with custom configuration
   python simple_marketing_demo.py --config config/demo.yaml
   ```

4. **Results Analysis**
   ```bash
   # View generated report
   cat simplified_marketing_report_*.json | jq '.'
   
   # Check execution metrics
   grep "execution_time" simplified_marketing_report_*.json
   
   # View detailed logs
   tail -n 50 logs/demo.log
   ```

#### Expected Workflow

1. **Idea Generation Phase** (10-15 seconds)
   - AI generates 3 innovative business ideas
   - Each idea includes strategic analysis and market research

2. **Development Request Phase** (20-30 seconds)
   - Ideas are formatted as development requests
   - Requests sent to containerized development team API

3. **Technical Analysis Phase** (30-45 seconds)
   - Development team analyzes each idea
   - Provides detailed technical requirements and implementation plans

4. **Report Generation Phase** (5-10 seconds)
   - Comprehensive report compiled
   - Results saved in JSON and optionally HTML format

### Development Workflow Demo

**Scenario**: Complete software development lifecycle with AI agents handling different roles.

```bash
# Run development workflow demo
python demo_development_workflow.py

# Monitor multi-agent collaboration
tail -f logs/development_workflow.log
```

### Enterprise Integration Demo

**Scenario**: Multi-valley communication and enterprise-grade features.

```bash
# Start enterprise demo environment
docker-compose -f docker-compose.enterprise.yml up -d

# Run enterprise integration demo
python demo_enterprise_integration.py
```

## 🔍 Troubleshooting

### Common Issues and Solutions

#### 1. Docker Container Issues

**Problem**: Containers fail to start
```bash
# Diagnosis
docker-compose ps
docker logs campfire-development-team

# Solution
docker-compose down
docker-compose up -d --force-recreate
```

**Problem**: Port conflicts
```bash
# Diagnosis
netstat -an | findstr :8080  # Windows
netstat -an | grep :8080     # Linux/macOS

# Solution: Modify docker-compose.yml
ports:
  - "8081:8080"  # Change external port
```

#### 2. MCP Broker Connection Issues

**Problem**: Demo hangs at "Subscribing to MCP channels"
```bash
# Diagnosis
docker logs campfire-redis
redis-cli -h localhost -p 6379 ping

# Solution: Use simplified demo
python simple_marketing_demo.py
```

**Problem**: Redis connection refused
```bash
# Diagnosis
docker exec campfire-redis redis-cli ping

# Solution: Restart Redis container
docker-compose restart campfire-redis
```

#### 3. API Communication Issues

**Problem**: Development team API returns 404 errors
```bash
# Diagnosis
curl -v http://localhost:8080/api/develop_website

# Solution: Verify container and endpoint
docker logs campfire-development-team
curl http://localhost:8080/health
```

**Problem**: Timeout errors
```bash
# Diagnosis
curl -w "@curl-format.txt" http://localhost:8080/api/develop_website

# Solution: Increase timeout in demo script
# Edit simple_marketing_demo.py
timeout = aiohttp.ClientTimeout(total=120)  # Increase from 30
```

#### 4. Python Environment Issues

**Problem**: Import errors
```bash
# Diagnosis
python -c "import campfirevalley"

# Solution: Reinstall dependencies
pip install -r requirements.txt --force-reinstall
```

**Problem**: Permission errors
```bash
# Windows: Run PowerShell as Administrator
# Linux/macOS: Check file permissions
chmod +x simple_marketing_demo.py
```

### Debug Mode Execution

Enable detailed logging for troubleshooting:

```bash
# Set debug environment
export CAMPFIRE_DEBUG=true
export CAMPFIRE_LOG_LEVEL=DEBUG

# Run demo with debug output
python simple_marketing_demo.py --debug

# View debug logs
tail -f logs/debug.log
```

### Health Check Script

Create a comprehensive health check:

```bash
#!/bin/bash
# health_check.sh

echo "🔍 CampfireValley Health Check"
echo "=============================="

# Check Docker
echo "📦 Docker Status:"
docker --version
docker-compose ps

# Check Services
echo "🌐 Service Health:"
curl -s http://localhost:8080/health || echo "❌ Development Team API: FAILED"
docker exec campfire-redis redis-cli ping || echo "❌ Redis: FAILED"
curl -s http://localhost:11434/api/tags > /dev/null || echo "❌ Ollama: FAILED"

# Check Ports
echo "🔌 Port Status:"
netstat -an | grep :8080 || echo "❌ Port 8080: Not listening"
netstat -an | grep :6379 || echo "❌ Port 6379: Not listening"

echo "✅ Health check completed"
```

## ⚙️ Advanced Configuration

### Custom Demo Configuration

Create custom demo configurations:

```yaml
# config/custom_demo.yaml
demo:
  name: "Custom Marketing Demo"
  ideas_count: 5
  timeout: 120
  
marketing:
  focus_areas:
    - "AI/ML Solutions"
    - "Sustainability"
    - "Healthcare Innovation"
  
development:
  api_endpoint: "http://localhost:8080/api/develop_website"
  retry_attempts: 3
  
reporting:
  format: ["json", "html"]
  include_metrics: true
```

### Environment Variables

Configure demos using environment variables:

```bash
# Demo configuration
export CAMPFIRE_DEMO_IDEAS_COUNT=5
export CAMPFIRE_DEMO_TIMEOUT=120
export CAMPFIRE_API_ENDPOINT="http://localhost:8080/api/develop_website"

# Logging configuration
export CAMPFIRE_LOG_LEVEL=INFO
export CAMPFIRE_LOG_FORMAT=json

# Run demo with custom configuration
python simple_marketing_demo.py
```

### Multi-Environment Setup

Set up different environments:

```bash
# Development environment
cp config/demo.dev.yaml config/demo.yaml
python simple_marketing_demo.py

# Production environment
cp config/demo.prod.yaml config/demo.yaml
python simple_marketing_demo.py
```

## 🚀 Performance Optimization

### Resource Allocation

Optimize Docker resource allocation:

```yaml
# docker-compose.override.yml
version: '3.8'

services:
  campfire-development-team:
    deploy:
      resources:
        limits:
          memory: 2G
          cpus: '1.0'
        reservations:
          memory: 1G
          cpus: '0.5'
```

### Parallel Execution

Enable parallel processing:

```python
# In simple_marketing_demo.py
import asyncio

# Increase concurrency
semaphore = asyncio.Semaphore(5)  # Allow 5 concurrent requests
```

### Caching Configuration

Enable response caching:

```bash
# Redis caching
docker exec campfire-redis redis-cli CONFIG SET maxmemory 1gb
docker exec campfire-redis redis-cli CONFIG SET maxmemory-policy allkeys-lru
```

## 📊 Monitoring and Metrics

### Real-time Monitoring

Monitor demo execution:

```bash
# Container resource usage
docker stats

# Service logs
docker-compose logs -f --tail=100

# Prometheus metrics
curl http://localhost:9090/metrics
```

### Performance Metrics

Key metrics to monitor:

- **Execution Time**: Total demo runtime
- **API Response Time**: Development team API latency
- **Memory Usage**: Container memory consumption
- **Success Rate**: Percentage of successful requests

### Log Analysis

Analyze demo logs:

```bash
# Extract execution times
grep "execution_time" simplified_marketing_report_*.json

# Count successful requests
grep "✅" logs/demo.log | wc -l

# Identify errors
grep "ERROR\|FAILED" logs/demo.log
```

## 🎯 Next Steps

After successfully running the demos:

1. **Explore Configuration**: Modify demo parameters and configurations
2. **Custom Scenarios**: Create your own demo scenarios
3. **Integration**: Integrate CampfireValley into your projects
4. **Scaling**: Deploy in production environments
5. **Monitoring**: Set up comprehensive monitoring and alerting

## 📚 Additional Resources

- [README.md](README.md): Project overview and features
- [DEPLOYMENT.md](DEPLOYMENT.md): Production deployment guide
- [TESTING.md](TESTING.md): Testing procedures and guidelines
- [API Documentation](docs/api.md): Complete API reference
- [Configuration Reference](docs/configuration.md): Detailed configuration options

## 🆘 Support

If you encounter issues:

1. Check this troubleshooting guide
2. Review container logs: `docker-compose logs`
3. Verify system requirements
4. Check GitHub issues: [CampfireValley Issues](https://github.com/your-org/campfirevalley/issues)
5. Contact support: support@campfirevalley.com

---

**Happy Demoing! 🎉**
# CampfireValley Troubleshooting Guide

This guide provides solutions to common issues encountered when running CampfireValley demos and services.

## Table of Contents

1. [MCP Broker Issues](#mcp-broker-issues)
2. [Docker Container Issues](#docker-container-issues)
3. [API Connection Issues](#api-connection-issues)
4. [Python Environment Issues](#python-environment-issues)
5. [Performance Issues](#performance-issues)
6. [Configuration Issues](#configuration-issues)

## MCP Broker Issues

### Issue: MCP Subscription Errors

**Symptoms:**
- Error messages like "MCP subscription failed" or "Redis connection timeout"
- Demos hanging at "Initializing campfire..." stage
- Connection refused errors when trying to connect to Redis MCP broker

**Root Cause:**
The MCP (Model Context Protocol) broker requires a Redis connection and proper subscription handling. In some environments, the Redis connection may fail or timeout, causing the entire demo to hang.

**Workarounds:**

#### Option 1: Use Simplified Demo (Recommended)
```bash
# Run the simplified marketing demo that bypasses MCP broker
python simple_marketing_demo.py
```

**Benefits:**
- No Redis dependency
- Direct API communication
- Faster execution
- Same core functionality

#### Option 2: Fix Redis Connection
```bash
# Check if Redis is running
docker ps | grep redis

# Restart Redis container
docker-compose restart redis

# Check Redis logs
docker-compose logs redis

# Test Redis connection
docker exec -it campfirevalley-redis-1 redis-cli ping
```

#### Option 3: Use Local Redis
```bash
# Install Redis locally (Windows)
# Download from: https://github.com/microsoftarchive/redis/releases

# Start Redis server
redis-server

# Update configuration to use local Redis
# Edit config/environments/local.yaml:
redis:
  host: localhost
  port: 6379
```

### Issue: Dock Gateway Startup Problems

**Symptoms:**
- "Dock gateway failed to start" errors
- Timeout errors during campfire initialization
- Services not responding

**Solutions:**

1. **Check Docker Services:**
```bash
# Verify all containers are running
docker-compose ps

# Check container health
docker-compose logs development-team
docker-compose logs marketing-team
```

2. **Restart Services:**
```bash
# Restart specific service
docker-compose restart development-team

# Full restart
docker-compose down && docker-compose up -d
```

3. **Use Direct API Calls:**
```python
# Instead of using campfire gateway, call APIs directly
import requests

response = requests.post(
    "http://localhost:8001/api/develop_website",
    json={"dev_request": your_request}
)
```

## Docker Container Issues

### Issue: Port Conflicts

**Symptoms:**
- "Port already in use" errors
- Services failing to start

**Solutions:**
```bash
# Check what's using the port
netstat -ano | findstr :8001

# Kill process using the port
taskkill /PID <process_id> /F

# Or change ports in docker-compose.yml
```

### Issue: Container Build Failures

**Symptoms:**
- Build errors during `docker-compose up`
- Missing dependencies

**Solutions:**
```bash
# Clean rebuild
docker-compose down
docker-compose build --no-cache
docker-compose up -d

# Check build logs
docker-compose logs --tail=50 development-team
```

### Issue: Volume Mount Problems

**Symptoms:**
- Files not updating in containers
- Permission errors

**Solutions:**
```bash
# Windows: Ensure drive sharing is enabled in Docker Desktop
# Check volume mounts in docker-compose.yml

# Fix permissions (if using WSL)
sudo chown -R $USER:$USER /path/to/project
```

## API Connection Issues

### Issue: 404 Not Found Errors

**Symptoms:**
- API endpoints returning 404
- "Endpoint not found" messages

**Solutions:**

1. **Verify Correct Endpoints:**
```python
# Correct endpoints for different services:
# Development Team: http://localhost:8001/api/develop_website
# Marketing Team: http://localhost:8002/api/marketing/analyze
```

2. **Check Service Status:**
```bash
# Test endpoint directly
curl http://localhost:8001/health
curl http://localhost:8001/api/develop_website -X POST -H "Content-Type: application/json" -d "{}"
```

3. **Update API Calls:**
```python
# Use correct request format
payload = {
    "dev_request": {
        "requirements": "Your requirements here",
        "context": "Additional context"
    }
}
```

### Issue: Connection Timeouts

**Symptoms:**
- Requests timing out
- "Connection refused" errors

**Solutions:**
```bash
# Increase timeout in requests
requests.post(url, json=data, timeout=60)

# Check if service is responsive
docker-compose logs development-team | tail -20
```

## Python Environment Issues

### Issue: Missing Dependencies

**Symptoms:**
- ImportError for required packages
- Module not found errors

**Solutions:**
```bash
# Install requirements
pip install -r requirements.txt

# Or install specific packages
pip install requests pydantic fastapi uvicorn
```

### Issue: Python Version Compatibility

**Symptoms:**
- Syntax errors
- Incompatible package versions

**Solutions:**
```bash
# Check Python version
python --version

# Use Python 3.8+ for best compatibility
# Consider using virtual environment
python -m venv campfire_env
campfire_env\Scripts\activate  # Windows
pip install -r requirements.txt
```

## Performance Issues

### Issue: Slow Response Times

**Symptoms:**
- Long delays in API responses
- Timeouts during processing

**Solutions:**

1. **Optimize Docker Resources:**
```yaml
# In docker-compose.yml, add resource limits
services:
  development-team:
    deploy:
      resources:
        limits:
          memory: 2G
        reservations:
          memory: 1G
```

2. **Use Simplified Workflows:**
```python
# Use simplified demo for faster execution
python simple_marketing_demo.py
```

3. **Monitor Resource Usage:**
```bash
# Check Docker resource usage
docker stats

# Check system resources
Get-Process | Sort-Object CPU -Descending | Select-Object -First 10
```

## Configuration Issues

### Issue: Invalid Configuration Files

**Symptoms:**
- YAML parsing errors
- Configuration validation failures

**Solutions:**

1. **Validate YAML Syntax:**
```bash
# Use online YAML validator or
python -c "import yaml; yaml.safe_load(open('config/file.yaml'))"
```

2. **Check Required Fields:**
```yaml
# Ensure all required fields are present
campfires:
  - name: "required"
    type: "required"
    config: {}
```

3. **Use Default Configurations:**
```bash
# Copy from examples
cp config/examples/basic.yaml config/environments/local.yaml
```

## Quick Diagnostic Commands

```bash
# Check all services
docker-compose ps

# View recent logs
docker-compose logs --tail=20

# Test API endpoints
curl http://localhost:8001/health
curl http://localhost:8002/health

# Check Python environment
python --version
pip list | grep -E "(requests|pydantic|fastapi)"

# Test Redis connection
docker exec -it campfirevalley-redis-1 redis-cli ping

# Check port usage
netstat -ano | findstr :800
```

## Getting Help

If you continue to experience issues:

1. **Check the logs:** Always start with `docker-compose logs [service-name]`
2. **Use simplified demos:** Try `simple_marketing_demo.py` for basic functionality
3. **Verify prerequisites:** Ensure Docker, Python, and all dependencies are properly installed
4. **Test incrementally:** Start with individual services before running full workflows

## Common Error Messages and Solutions

| Error Message | Likely Cause | Solution |
|---------------|--------------|----------|
| "MCP subscription failed" | Redis connection issue | Use simplified demo or restart Redis |
| "Port already in use" | Port conflict | Change ports or kill conflicting process |
| "Connection refused" | Service not running | Check `docker-compose ps` and restart services |
| "404 Not Found" | Wrong API endpoint | Verify endpoint URLs in code |
| "Module not found" | Missing Python package | Run `pip install -r requirements.txt` |
| "YAML parsing error" | Invalid configuration | Validate YAML syntax |
| "Permission denied" | File/directory permissions | Check Docker volume mounts and permissions |

Remember: The simplified demo (`simple_marketing_demo.py`) bypasses most of these issues and provides the same core functionality for testing and demonstration purposes.
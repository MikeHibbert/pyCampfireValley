# CampfireValley Deployment Guide

This guide provides comprehensive instructions for deploying CampfireValley in production environments, covering both Phase 1 (core infrastructure) and Phase 2 (enterprise features).

## Table of Contents

- [Overview](#overview)
- [Prerequisites](#prerequisites)
- [Deployment Options](#deployment-options)
- [Docker Deployment](#docker-deployment)
- [Kubernetes Deployment](#kubernetes-deployment)
- [Traditional Server Deployment](#traditional-server-deployment)
- [Configuration Management](#configuration-management)
- [Security Considerations](#security-considerations)
- [Monitoring and Logging](#monitoring-and-logging)
- [Backup and Recovery](#backup-and-recovery)
- [Performance Tuning](#performance-tuning)
- [Troubleshooting](#troubleshooting)

## Overview

CampfireValley is designed for enterprise deployment with high availability, scalability, and security. This guide covers:

- **Single-node deployment**: For development and small-scale production
- **Multi-node deployment**: For high availability and scalability
- **Cloud deployment**: AWS, Azure, GCP deployment patterns
- **Hybrid deployment**: On-premises and cloud hybrid setups

## Prerequisites

### System Requirements

#### Minimum Requirements
- **CPU**: 2 cores
- **RAM**: 4GB
- **Storage**: 20GB SSD
- **Network**: 1Gbps
- **OS**: Linux (Ubuntu 20.04+, CentOS 8+, RHEL 8+)

#### Recommended Requirements
- **CPU**: 8 cores
- **RAM**: 16GB
- **Storage**: 100GB NVMe SSD
- **Network**: 10Gbps
- **OS**: Linux (Ubuntu 22.04 LTS)

#### High-Performance Requirements
- **CPU**: 16+ cores
- **RAM**: 64GB+
- **Storage**: 500GB+ NVMe SSD with RAID
- **Network**: 25Gbps+
- **OS**: Linux with performance tuning

### Software Dependencies

```bash
# Core dependencies
- Python 3.8+
- Redis 6.0+
- PostgreSQL 13+ (optional, for persistent storage)
- Nginx (for reverse proxy)
- SSL certificates

# Optional dependencies
- Docker 20.10+
- Kubernetes 1.21+
- Prometheus (for monitoring)
- Grafana (for dashboards)
- ELK Stack (for logging)
```

## Deployment Options

### 1. Docker Deployment (Recommended)

Docker deployment provides consistency, isolation, and easy scaling.

#### Single Container Deployment

```dockerfile
# Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create non-root user
RUN useradd -m -u 1000 campfire && chown -R campfire:campfire /app
USER campfire

# Expose port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8080/health')"

# Start application
CMD ["python", "-m", "campfirevalley.server"]
```

#### Docker Compose Deployment

```yaml
# docker-compose.yml
version: '3.8'

services:
  campfirevalley:
    build: .
    ports:
      - "8080:8080"
    environment:
      - REDIS_URL=redis://redis:6379
      - POSTGRES_URL=postgresql://postgres:password@postgres:5432/campfirevalley
      - CAMPFIRE_ENV=production
    volumes:
      - ./config:/app/config
      - ./storage:/app/storage
      - ./logs:/app/logs
    depends_on:
      - redis
      - postgres
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    restart: unless-stopped
    command: redis-server --appendonly yes

  postgres:
    image: postgres:15-alpine
    environment:
      - POSTGRES_DB=campfirevalley
      - POSTGRES_USER=postgres
      - POSTGRES_PASSWORD=password
    volumes:
      - postgres_data:/var/lib/postgresql/data
    restart: unless-stopped

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
      - ./ssl:/etc/nginx/ssl
    depends_on:
      - campfirevalley
    restart: unless-stopped

volumes:
  redis_data:
  postgres_data:
```

#### Production Docker Compose

```yaml
# docker-compose.prod.yml
version: '3.8'

services:
  campfirevalley:
    image: campfirevalley:latest
    deploy:
      replicas: 3
      resources:
        limits:
          cpus: '2'
          memory: 4G
        reservations:
          cpus: '1'
          memory: 2G
      restart_policy:
        condition: on-failure
        delay: 5s
        max_attempts: 3
    environment:
      - CAMPFIRE_ENV=production
      - REDIS_URL=redis://redis-cluster:6379
      - MONITORING_ENABLED=true
      - VALI_ENABLED=true
      - JUSTICE_ENABLED=true
    volumes:
      - /opt/campfirevalley/config:/app/config:ro
      - /opt/campfirevalley/storage:/app/storage
      - /var/log/campfirevalley:/app/logs
    networks:
      - campfire_network

  redis-cluster:
    image: redis:7-alpine
    deploy:
      replicas: 3
    volumes:
      - redis_cluster_data:/data
    networks:
      - campfire_network

networks:
  campfire_network:
    driver: overlay
    attachable: true

volumes:
  redis_cluster_data:
```

### Demo Environment Docker Setup

CampfireValley includes a comprehensive demo environment showcasing AI agent collaboration workflows. The demo uses multiple containerized services to simulate a complete enterprise environment.

#### Demo Docker Compose Configuration

The demo environment includes the following services:

```yaml
# docker-compose.yml (Demo Configuration)
version: '3.8'

services:
  # Development Team API Service
  campfire-development-team:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: campfire-development-team
    ports:
      - "8080:8080"
    environment:
      - PYTHONPATH=/app
      - ENVIRONMENT=demo
    volumes:
      - ./config:/app/config
      - ./data:/app/data
    command: python development_team_server.py
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  # Redis MCP Broker
  campfire-redis:
    image: redis:7-alpine
    container_name: campfire-redis
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    command: redis-server --appendonly yes --maxmemory 512mb --maxmemory-policy allkeys-lru
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 30s
      timeout: 10s
      retries: 3

  # Ollama LLM Service
  campfire-ollama:
    image: ollama/ollama:latest
    container_name: campfire-ollama
    ports:
      - "11434:11434"
    volumes:
      - ollama_data:/root/.ollama
    environment:
      - OLLAMA_HOST=0.0.0.0
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:11434/api/tags"]
      interval: 60s
      timeout: 30s
      retries: 3

  # Prometheus Monitoring
  campfire-prometheus:
    image: prom/prometheus:latest
    container_name: campfire-prometheus
    ports:
      - "9090:9090"
    volumes:
      - ./monitoring/prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus_data:/prometheus
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'
      - '--web.console.libraries=/etc/prometheus/console_libraries'
      - '--web.console.templates=/etc/prometheus/consoles'
      - '--storage.tsdb.retention.time=200h'
      - '--web.enable-lifecycle'
    restart: unless-stopped

volumes:
  redis_data:
    driver: local
  ollama_data:
    driver: local
  prometheus_data:
    driver: local

networks:
  default:
    name: campfire-network
    driver: bridge
```

#### Service Descriptions

| Service | Purpose | Port | Health Check |
|---------|---------|------|--------------|
| **campfire-development-team** | AI development team API providing technical analysis | 8080 | HTTP `/health` endpoint |
| **campfire-redis** | MCP broker for inter-service communication | 6379 | Redis PING command |
| **campfire-ollama** | Local LLM service for AI model inference | 11434 | HTTP `/api/tags` endpoint |
| **campfire-prometheus** | Metrics collection and monitoring | 9090 | Built-in Prometheus health |

#### Demo Container Management

**Starting the Demo Environment**:
```bash
# Start all demo services
docker-compose up -d

# Check service status
docker-compose ps

# View service logs
docker-compose logs -f campfire-development-team
```

**Stopping the Demo Environment**:
```bash
# Stop all services
docker-compose down

# Stop and remove volumes (clean slate)
docker-compose down -v
```

**Individual Service Management**:
```bash
# Restart specific service
docker-compose restart campfire-development-team

# Scale development team service
docker-compose up -d --scale campfire-development-team=3

# View real-time logs
docker-compose logs -f campfire-redis
```

#### Demo Container Troubleshooting

**Common Issues and Solutions**:

1. **Port Conflicts**
   ```bash
   # Check port usage
   netstat -tulpn | grep :8080
   
   # Modify ports in docker-compose.yml
   ports:
     - "8081:8080"  # Change external port
   ```

2. **Container Startup Failures**
   ```bash
   # Check container logs
   docker logs campfire-development-team
   
   # Inspect container configuration
   docker inspect campfire-development-team
   ```

3. **Network Connectivity Issues**
   ```bash
   # Test inter-container communication
   docker exec campfire-development-team ping campfire-redis
   
   # Check network configuration
   docker network ls
   docker network inspect campfire-network
   ```

4. **Resource Constraints**
   ```bash
   # Monitor resource usage
   docker stats
   
   # Adjust resource limits in docker-compose.yml
   deploy:
     resources:
       limits:
         memory: 2G
         cpus: '1.0'
   ```

5. **Volume Mount Issues**
   ```bash
   # Check volume mounts
   docker volume ls
   docker volume inspect redis_data
   
   # Fix permissions
   sudo chown -R 1000:1000 ./data
   ```

#### Demo Environment Monitoring

**Health Checks**:
```bash
# Check all service health
docker-compose ps

# Individual service health
curl http://localhost:8080/health
curl http://localhost:11434/api/tags
redis-cli -h localhost -p 6379 ping
```

**Performance Monitoring**:
```bash
# Resource usage
docker stats --no-stream

# Container logs
docker-compose logs --tail=100 -f

# Prometheus metrics
curl http://localhost:9090/metrics
```

#### Demo Data Persistence

The demo environment uses named volumes for data persistence:

- **redis_data**: Redis data and configuration
- **ollama_data**: Downloaded LLM models and cache
- **prometheus_data**: Metrics and monitoring data

**Backup Demo Data**:
```bash
# Create backup
docker run --rm -v redis_data:/data -v $(pwd):/backup alpine tar czf /backup/redis_backup.tar.gz -C /data .

# Restore backup
docker run --rm -v redis_data:/data -v $(pwd):/backup alpine tar xzf /backup/redis_backup.tar.gz -C /data
```

### 2. Kubernetes Deployment

Kubernetes provides advanced orchestration, scaling, and management capabilities.

#### Namespace and ConfigMap

```yaml
# k8s/namespace.yaml
apiVersion: v1
kind: Namespace
metadata:
  name: campfirevalley

---
# k8s/configmap.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: campfirevalley-config
  namespace: campfirevalley
data:
  config.yaml: |
    valley:
      name: "ProductionValley"
      max_campfires: 100
      enable_monitoring: true
      enable_justice: true
      enable_vali: true
    
    monitoring:
      enabled: true
      metrics_collection: true
      alerting: true
    
    storage:
      type: "hierarchical"
      base_path: "/app/storage"
```

#### Deployment and Service

```yaml
# k8s/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: campfirevalley
  namespace: campfirevalley
  labels:
    app: campfirevalley
spec:
  replicas: 3
  selector:
    matchLabels:
      app: campfirevalley
  template:
    metadata:
      labels:
        app: campfirevalley
    spec:
      containers:
      - name: campfirevalley
        image: campfirevalley:latest
        ports:
        - containerPort: 8080
        env:
        - name: REDIS_URL
          value: "redis://redis-service:6379"
        - name: CAMPFIRE_ENV
          value: "production"
        volumeMounts:
        - name: config
          mountPath: /app/config
        - name: storage
          mountPath: /app/storage
        resources:
          requests:
            memory: "2Gi"
            cpu: "1"
          limits:
            memory: "4Gi"
            cpu: "2"
        livenessProbe:
          httpGet:
            path: /health
            port: 8080
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /ready
            port: 8080
          initialDelaySeconds: 5
          periodSeconds: 5
      volumes:
      - name: config
        configMap:
          name: campfirevalley-config
      - name: storage
        persistentVolumeClaim:
          claimName: campfirevalley-storage

---
# k8s/service.yaml
apiVersion: v1
kind: Service
metadata:
  name: campfirevalley-service
  namespace: campfirevalley
spec:
  selector:
    app: campfirevalley
  ports:
  - protocol: TCP
    port: 80
    targetPort: 8080
  type: ClusterIP
```

#### Ingress and TLS

```yaml
# k8s/ingress.yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: campfirevalley-ingress
  namespace: campfirevalley
  annotations:
    kubernetes.io/ingress.class: nginx
    cert-manager.io/cluster-issuer: letsencrypt-prod
    nginx.ingress.kubernetes.io/ssl-redirect: "true"
    nginx.ingress.kubernetes.io/proxy-body-size: "100m"
spec:
  tls:
  - hosts:
    - campfirevalley.example.com
    secretName: campfirevalley-tls
  rules:
  - host: campfirevalley.example.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: campfirevalley-service
            port:
              number: 80
```

#### Horizontal Pod Autoscaler

```yaml
# k8s/hpa.yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: campfirevalley-hpa
  namespace: campfirevalley
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: campfirevalley
  minReplicas: 3
  maxReplicas: 20
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  - type: Resource
    resource:
      name: memory
      target:
        type: Utilization
        averageUtilization: 80
```

### 3. Traditional Server Deployment

For environments where containerization is not available.

#### System Setup

```bash
#!/bin/bash
# setup.sh - Production server setup script

set -e

# Update system
sudo apt update && sudo apt upgrade -y

# Install Python 3.11
sudo apt install -y software-properties-common
sudo add-apt-repository ppa:deadsnakes/ppa -y
sudo apt update
sudo apt install -y python3.11 python3.11-venv python3.11-dev

# Install Redis
sudo apt install -y redis-server
sudo systemctl enable redis-server
sudo systemctl start redis-server

# Install PostgreSQL
sudo apt install -y postgresql postgresql-contrib
sudo systemctl enable postgresql
sudo systemctl start postgresql

# Install Nginx
sudo apt install -y nginx
sudo systemctl enable nginx
sudo systemctl start nginx

# Create application user
sudo useradd -m -s /bin/bash campfire
sudo usermod -aG sudo campfire

# Create application directories
sudo mkdir -p /opt/campfirevalley
sudo mkdir -p /var/log/campfirevalley
sudo mkdir -p /etc/campfirevalley
sudo chown -R campfire:campfire /opt/campfirevalley
sudo chown -R campfire:campfire /var/log/campfirevalley
sudo chown -R campfire:campfire /etc/campfirevalley
```

#### Application Installation

```bash
#!/bin/bash
# install.sh - Application installation script

# Switch to application user
sudo -u campfire bash << 'EOF'

# Navigate to application directory
cd /opt/campfirevalley

# Create virtual environment
python3.11 -m venv venv
source venv/bin/activate

# Install CampfireValley
pip install --upgrade pip
pip install campfirevalley[all]

# Create configuration
mkdir -p config
cat > config/production.yaml << 'CONFIG'
valley:
  name: "ProductionValley"
  max_campfires: 50
  enable_monitoring: true
  enable_justice: true
  enable_vali: true

monitoring:
  enabled: true
  logging:
    level: "INFO"
    handlers:
      - type: "file"
        path: "/var/log/campfirevalley/app.log"

storage:
  type: "hierarchical"
  base_path: "/opt/campfirevalley/storage"
CONFIG

EOF
```

#### Systemd Service

```ini
# /etc/systemd/system/campfirevalley.service
[Unit]
Description=CampfireValley Service
After=network.target redis.service postgresql.service
Wants=redis.service postgresql.service

[Service]
Type=simple
User=campfire
Group=campfire
WorkingDirectory=/opt/campfirevalley
Environment=PATH=/opt/campfirevalley/venv/bin
Environment=CAMPFIRE_ENV=production
Environment=CAMPFIRE_CONFIG=/etc/campfirevalley/config.yaml
ExecStart=/opt/campfirevalley/venv/bin/python -m campfirevalley.server
ExecReload=/bin/kill -HUP $MAINPID
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=campfirevalley

# Security settings
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/opt/campfirevalley /var/log/campfirevalley

[Install]
WantedBy=multi-user.target
```

## Configuration Management

CampfireValley implements a comprehensive configuration-driven architecture that enables flexible, maintainable, and environment-specific deployments without code changes.

### Configuration-Driven Architecture Overview

The configuration system provides:
- **Declarative Configuration**: Define what you want, not how to achieve it
- **Environment Separation**: Clean separation between dev, staging, and production
- **Schema Validation**: All configurations are validated against JSON schemas
- **Hot Reload**: Runtime configuration updates without service restart
- **Encryption Support**: Sensitive data is automatically encrypted
- **Configuration Inheritance**: Environment-specific overrides of base configurations

### Configuration Hierarchy

CampfireValley uses a multi-layered configuration system:

1. **Base Configuration** (`config/base.yaml`): Core system defaults
2. **Environment Configuration** (`config/{env}.yaml`): Environment-specific overrides
3. **Valley Configuration** (`config/valleys/{valley}.yaml`): Valley-specific settings
4. **Runtime Configuration**: Dynamic updates during operation

### Environment-Specific Configurations

#### Base Configuration (`config/base.yaml`)

```yaml
# Base configuration with sensible defaults
name: "CampfireValley"
version: "2.0"

# Core settings
env:
  dock_mode: "public"
  security_level: "standard"
  auto_create_dock: true
  debug: false

# Campfire configuration
campfires:
  visible: ["dockmaster", "sanitizer", "validator"]
  hidden: ["internal-router"]
  max_instances: 50

# Community settings
community:
  discovery: true
  trusted_valleys: []
  max_connections: 100

# Security configuration
security:
  vali:
    enabled: true
    scan_level: "standard"
    threat_detection: true
    signature_verification: true
  
  justice:
    enabled: true
    policy_enforcement: "moderate"
    rate_limiting:
      requests_per_minute: 60
      burst_limit: 10
      violation_threshold: 5
  
  encryption:
    algorithm: "AES-256-GCM"
    key_rotation_interval: 86400
    auto_encrypt_secrets: true

# Routing configuration
routing:
  strategy: "intelligent"
  load_balancing: "round_robin"
  health_checks:
    enabled: true
    interval: 30
    timeout: 5
    failure_threshold: 3
  
  failover:
    enabled: true
    strategy: "circuit_breaker"
    recovery_timeout: 60

# Storage configuration
storage:
  type: "hierarchical"
  base_path: "/opt/campfirevalley/storage"
  
  hierarchical:
    enabled: true
    tiers:
      hot: { retention: "7d", compression: false }
      warm: { retention: "30d", compression: "lz4" }
      cold: { retention: "1y", compression: "gzip" }
      archive: { retention: "7y", compression: "bzip2" }
    
    policies:
      auto_migration: true
      deduplication: true
      compression_threshold: 1024

# Monitoring configuration
monitoring:
  enabled: true
  
  metrics:
    collection_interval: 10
    retention_days: 30
    aggregation_window: 60
  
  logging:
    level: "INFO"
    format: "json"
    handlers: ["console", "file"]
    rotation: "daily"
    max_files: 30
  
  alerts:
    enabled: true
    severity_threshold: "warning"
    channels: []

# MCP Broker configuration
mcp:
  broker_type: "redis"
  connection_pool_size: 10
  retry_attempts: 3
  timeout: 30
```

#### Production Configuration (`config/production.yaml`)

```yaml
extends: "base.yaml"

# Production-specific overrides
env:
  security_level: "maximum"
  debug: false

# Enhanced security for production
security:
  vali:
    scan_level: "comprehensive"
    threat_detection: true
    advanced_scanning: true
  
  justice:
    policy_enforcement: "strict"
    rate_limiting:
      requests_per_minute: 100
      burst_limit: 20
      violation_threshold: 3
  
  tls:
    enabled: true
    cert_path: "/etc/ssl/certs/campfirevalley.crt"
    key_path: "/etc/ssl/private/campfirevalley.key"
    min_version: "1.3"
    cipher_suites: ["ECDHE-RSA-AES256-GCM-SHA384", "ECDHE-RSA-AES128-GCM-SHA256"]

# Production monitoring
monitoring:
  metrics:
    collection_interval: 5
    retention_days: 90
  
  logging:
    level: "WARNING"
    handlers: ["file", "syslog", "elasticsearch"]
  
  alerts:
    enabled: true
    severity_threshold: "error"
    channels:
      - type: "email"
        smtp_server: "smtp.company.com"
        recipients: ["ops@company.com", "security@company.com"]
      - type: "webhook"
        url: "https://hooks.slack.com/services/..."
      - type: "pagerduty"
        integration_key: "!encrypted:AES256:..."

# Production storage
storage:
  hierarchical:
    tiers:
      hot: { retention: "30d", compression: false }
      warm: { retention: "90d", compression: "lz4" }
      cold: { retention: "365d", compression: "gzip" }
      archive: { retention: "2555d", compression: "bzip2" }

# Production routing
routing:
  load_balancing: "weighted_round_robin"
  health_checks:
    interval: 15
    timeout: 3
    failure_threshold: 2

# Database configuration
database:
  host: "db.company.com"
  port: 5432
  name: "campfirevalley_prod"
  username: "campfire_user"
  password: "!encrypted:AES256:base64encodedpassword"
  pool_size: 20
  max_overflow: 30
  ssl_mode: "require"
```

#### Development Configuration (`config/development.yaml`)

```yaml
extends: "base.yaml"

# Development-specific overrides
env:
  security_level: "development"
  debug: true

# Relaxed security for development
security:
  vali:
    scan_level: "basic"
    threat_detection: false
  
  justice:
    policy_enforcement: "permissive"
    rate_limiting:
      requests_per_minute: 1000
      burst_limit: 100

# Development monitoring
monitoring:
  logging:
    level: "DEBUG"
    handlers: ["console"]
  
  alerts:
    enabled: false

# Local storage
storage:
  base_path: "./dev_storage"
  hierarchical:
    enabled: false

# Local database
database:
  host: "localhost"
  port: 5432
  name: "campfirevalley_dev"
  username: "dev_user"
  password: "dev_password"
  pool_size: 5
```

### Configuration Management Features

#### 1. Schema Validation

All configurations are validated against comprehensive JSON schemas:

```python
from campfirevalley.config_manager import ConfigManager

# Load and validate configuration
config_manager = ConfigManager()
config = config_manager.load_config("config/production.yaml")
# Automatically validates against schema and reports errors
```

#### 2. Encrypted Configuration Values

Sensitive data is automatically encrypted using the `!encrypted:` prefix:

```yaml
database:
  password: "!encrypted:AES256:base64encodeddata"
api_keys:
  external_service: "!encrypted:AES256:anothersecretvalue"
```

#### 3. Hot Configuration Reload

Update configurations without restarting services:

```python
# Configuration changes are automatically detected and applied
config_manager.watch_for_changes()

# Manual reload
await config_manager.reload_config()
```

#### 4. Environment Variable Overrides

Override any configuration value with environment variables using the `CAMPFIREVALLEY_` prefix:

```bash
# Override security level
export CAMPFIREVALLEY_SECURITY_LEVEL="maximum"

# Override logging level
export CAMPFIREVALLEY_MONITORING_LOGGING_LEVEL="ERROR"

# Override database password
export CAMPFIREVALLEY_DATABASE_PASSWORD="newsecretpassword"
```

#### 5. Configuration Validation

Validate configurations before deployment:

```bash
# Validate configuration file
campfirevalley validate-config config/production.yaml

# Validate with environment variables
CAMPFIREVALLEY_ENV=production campfirevalley validate-config config/production.yaml
```

### Environment Variables

```bash
# /etc/environment
CAMPFIRE_ENV=production
CAMPFIRE_CONFIG=/etc/campfirevalley/config.yaml
REDIS_URL=redis://localhost:6379
POSTGRES_URL=postgresql://campfire:password@localhost:5432/campfirevalley
JWT_SECRET_KEY=your-secret-key-here
ENCRYPTION_KEY=your-encryption-key-here
```

## Security Considerations

### SSL/TLS Configuration

```nginx
# /etc/nginx/sites-available/campfirevalley
server {
    listen 80;
    server_name campfirevalley.example.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name campfirevalley.example.com;

    # SSL Configuration
    ssl_certificate /etc/ssl/certs/campfirevalley.crt;
    ssl_certificate_key /etc/ssl/private/campfirevalley.key;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-RSA-AES256-GCM-SHA512:DHE-RSA-AES256-GCM-SHA512:ECDHE-RSA-AES256-GCM-SHA384:DHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers off;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;

    # Security Headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Frame-Options DENY always;
    add_header X-Content-Type-Options nosniff always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    # Proxy Configuration
    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Timeouts
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
        
        # Buffer settings
        proxy_buffering on;
        proxy_buffer_size 128k;
        proxy_buffers 4 256k;
        proxy_busy_buffers_size 256k;
    }

    # Health check endpoint
    location /health {
        proxy_pass http://127.0.0.1:8080/health;
        access_log off;
    }
}
```

### Firewall Configuration

```bash
# UFW firewall rules
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow ssh
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw allow from 10.0.0.0/8 to any port 6379  # Redis (internal only)
sudo ufw allow from 10.0.0.0/8 to any port 5432  # PostgreSQL (internal only)
sudo ufw enable
```

## Monitoring and Logging

### Prometheus Configuration

```yaml
# prometheus.yml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

rule_files:
  - "campfirevalley_rules.yml"

scrape_configs:
  - job_name: 'campfirevalley'
    static_configs:
      - targets: ['localhost:8080']
    metrics_path: '/metrics'
    scrape_interval: 10s

alerting:
  alertmanagers:
    - static_configs:
        - targets:
          - alertmanager:9093
```

### Grafana Dashboard

```json
{
  "dashboard": {
    "title": "CampfireValley Monitoring",
    "panels": [
      {
        "title": "Request Rate",
        "type": "graph",
        "targets": [
          {
            "expr": "rate(campfirevalley_requests_total[5m])",
            "legendFormat": "{{method}} {{status}}"
          }
        ]
      },
      {
        "title": "Response Time",
        "type": "graph",
        "targets": [
          {
            "expr": "histogram_quantile(0.95, rate(campfirevalley_request_duration_seconds_bucket[5m]))",
            "legendFormat": "95th percentile"
          }
        ]
      }
    ]
  }
}
```

### Log Aggregation

```yaml
# filebeat.yml
filebeat.inputs:
- type: log
  enabled: true
  paths:
    - /var/log/campfirevalley/*.log
  fields:
    service: campfirevalley
    environment: production

output.elasticsearch:
  hosts: ["elasticsearch:9200"]
  index: "campfirevalley-%{+yyyy.MM.dd}"

logging.level: info
```

## Backup and Recovery

### Database Backup

```bash
#!/bin/bash
# backup.sh - Database backup script

BACKUP_DIR="/opt/backups/campfirevalley"
DATE=$(date +%Y%m%d_%H%M%S)

# Create backup directory
mkdir -p $BACKUP_DIR

# Backup PostgreSQL
pg_dump -h localhost -U campfire campfirevalley | gzip > $BACKUP_DIR/postgres_$DATE.sql.gz

# Backup Redis
redis-cli --rdb $BACKUP_DIR/redis_$DATE.rdb

# Backup storage
tar -czf $BACKUP_DIR/storage_$DATE.tar.gz /opt/campfirevalley/storage

# Backup configuration
tar -czf $BACKUP_DIR/config_$DATE.tar.gz /etc/campfirevalley

# Clean old backups (keep 30 days)
find $BACKUP_DIR -name "*.gz" -mtime +30 -delete
find $BACKUP_DIR -name "*.rdb" -mtime +30 -delete
```

### Disaster Recovery

```bash
#!/bin/bash
# restore.sh - Disaster recovery script

BACKUP_DIR="/opt/backups/campfirevalley"
RESTORE_DATE=$1

if [ -z "$RESTORE_DATE" ]; then
    echo "Usage: $0 <backup_date>"
    exit 1
fi

# Stop services
sudo systemctl stop campfirevalley
sudo systemctl stop redis
sudo systemctl stop postgresql

# Restore PostgreSQL
gunzip -c $BACKUP_DIR/postgres_$RESTORE_DATE.sql.gz | psql -h localhost -U campfire campfirevalley

# Restore Redis
sudo cp $BACKUP_DIR/redis_$RESTORE_DATE.rdb /var/lib/redis/dump.rdb
sudo chown redis:redis /var/lib/redis/dump.rdb

# Restore storage
tar -xzf $BACKUP_DIR/storage_$RESTORE_DATE.tar.gz -C /

# Restore configuration
tar -xzf $BACKUP_DIR/config_$RESTORE_DATE.tar.gz -C /

# Start services
sudo systemctl start postgresql
sudo systemctl start redis
sudo systemctl start campfirevalley
```

## Performance Tuning

### System Optimization

```bash
# /etc/sysctl.d/99-campfirevalley.conf
# Network optimization
net.core.rmem_max = 134217728
net.core.wmem_max = 134217728
net.ipv4.tcp_rmem = 4096 65536 134217728
net.ipv4.tcp_wmem = 4096 65536 134217728
net.core.netdev_max_backlog = 5000

# File descriptor limits
fs.file-max = 2097152

# Memory optimization
vm.swappiness = 10
vm.dirty_ratio = 15
vm.dirty_background_ratio = 5
```

### Application Tuning

```yaml
# config/performance.yaml
valley:
  max_campfires: 100
  worker_processes: 8
  max_connections: 10000
  connection_timeout: 30

performance:
  enable_caching: true
  cache_size_mb: 1024
  connection_pool_size: 20
  async_workers: 16

storage:
  hierarchical:
    optimization:
      enable_compression: true
      compression_level: 6
      enable_deduplication: true
      chunk_size: 8192
```

## Troubleshooting

### Common Issues

#### High Memory Usage

```bash
# Check memory usage
free -h
ps aux --sort=-%mem | head

# Check for memory leaks
valgrind --tool=memcheck --leak-check=full python -m campfirevalley.server

# Optimize garbage collection
export PYTHONMALLOC=malloc
export MALLOC_ARENA_MAX=2
```

#### High CPU Usage

```bash
# Check CPU usage
top -p $(pgrep -f campfirevalley)

# Profile CPU usage
py-spy top --pid $(pgrep -f campfirevalley)

# Check for CPU-intensive operations
strace -p $(pgrep -f campfirevalley) -c
```

#### Network Issues

```bash
# Check network connections
netstat -tulpn | grep :8080

# Test connectivity
curl -I http://localhost:8080/health

# Check DNS resolution
nslookup campfirevalley.example.com
```

### Log Analysis

```bash
# Check application logs
tail -f /var/log/campfirevalley/app.log

# Check system logs
journalctl -u campfirevalley -f

# Search for errors
grep -i error /var/log/campfirevalley/app.log

# Analyze performance
grep "slow" /var/log/campfirevalley/app.log | tail -20
```

### Health Checks

```bash
# Application health
curl http://localhost:8080/health

# Redis health
redis-cli ping

# PostgreSQL health
pg_isready -h localhost -p 5432

# System health
systemctl status campfirevalley
```

This deployment guide provides comprehensive instructions for deploying CampfireValley in production environments with enterprise-grade reliability, security, and performance.
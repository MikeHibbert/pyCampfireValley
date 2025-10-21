# CampfireValley Federation Demo

This demo showcases the powerful federation capabilities of CampfireValley, demonstrating how multiple valleys can collaborate seamlessly across different domains and specialties.

## Overview

The federation demo creates three specialized valleys that work together on collaborative projects:

- **TechValley**: Software development and engineering
- **CreativeValley**: Design and marketing  
- **BusinessValley**: Strategy and operations

## Features Demonstrated

### 🌐 Multi-Valley Federation
- Automatic valley discovery and federation establishment
- Cross-valley communication and torch routing
- Federation-wide announcements and coordination

### 🔄 Inter-Valley Collaboration
- Cross-domain project workflows
- Resource sharing between valleys
- Collaborative decision making

### 📊 Advanced Communication
- Priority message queues for critical communications
- Federation heartbeat monitoring
- Message statistics and health monitoring

### 🛡️ Security & Governance
- Encrypted inter-valley communication
- Digital signature verification
- Federation governance and consensus mechanisms

## Quick Start

### Prerequisites

- Docker and Docker Compose
- Python 3.9+ (for local development)
- Redis (included in Docker setup)

### Option 1: Docker Compose (Recommended)

1. **Start the federation infrastructure:**
   ```bash
   cd examples
   docker-compose -f docker-compose.federation.yml up -d
   ```

2. **Run the federation demo:**
   ```bash
   docker-compose -f docker-compose.federation.yml --profile demo up federation_demo
   ```

3. **Monitor with observability tools (optional):**
   ```bash
   docker-compose -f docker-compose.federation.yml --profile monitoring up -d
   ```

4. **Access monitoring dashboards:**
   - Prometheus: http://localhost:9090
   - Grafana: http://localhost:3000 (admin/admin)
   - Redis Commander: http://localhost:8081

### Option 2: Local Development

1. **Start Redis:**
   ```bash
   docker run -d -p 6379:6379 redis:7-alpine
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Run the federation demo:**
   ```bash
   python examples/federation_demo.py
   ```

## Demo Scenarios

### 1. Cross-Valley Collaboration

The demo simulates a mobile app development project involving all three valleys:

1. **BusinessValley** initiates the project with requirements and budget
2. **CreativeValley** responds with design proposals and timelines
3. **TechValley** provides technical architecture and implementation plans

### 2. Federation Announcements

Demonstrates federation-wide communication:

- Quarterly innovation summit announcements
- Emergency security alerts
- Policy updates and governance decisions

### 3. Resource Sharing

Shows how valleys share resources and expertise:

- **TechValley** shares reusable authentication services
- **CreativeValley** shares UI component libraries
- **BusinessValley** shares project management templates

## Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   TechValley    │    │  CreativeValley │    │  BusinessValley │
│   Port: 8001    │    │   Port: 8002    │    │   Port: 8003    │
└─────────┬───────┘    └─────────┬───────┘    └─────────┬───────┘
          │                      │                      │
          └──────────────────────┼──────────────────────┘
                                 │
                    ┌─────────────┴─────────────┐
                    │     Redis MCP Broker      │
                    │      Port: 6379           │
                    └───────────────────────────┘
```

### Key Components

- **Dock Gateway**: Manages inter-valley communication and routing
- **Federation Manager**: Handles federation membership and discovery
- **MCP Broker**: Redis-based message communication protocol
- **VALI Services**: Validation and security services
- **Party Box**: Large attachment storage and retrieval

## Configuration

Each valley has its own configuration file in `config/federation/`:

- `techvalley.yaml`: Technical campfires and development tools
- `creativevalley.yaml`: Design and marketing campfires
- `businessvalley.yaml`: Strategy and operations campfires

### Key Configuration Sections

```yaml
valley:
  name: "TechValley"
  federation:
    enabled: true
    federations:
      - name: "InnovationFederation"
        role: "member"

dock:
  port: 8001
  mcp_broker:
    type: "redis"
    connection_string: "redis://localhost:6379"

campfires:
  - name: "backend_developer"
    type: "specialist"
    specialization: "backend_development"
```

## Monitoring and Observability

### Message Statistics

Each valley tracks:
- Messages sent/received
- Error rates
- Active subscriptions
- Federation health

### Health Checks

- Valley availability
- Redis connectivity
- Federation membership status
- Campfire responsiveness

### Metrics Collection

When running with monitoring profile:
- Prometheus metrics collection
- Grafana dashboards
- Real-time federation monitoring

## API Endpoints

Each valley exposes REST APIs:

### Valley Status
```
GET http://localhost:800X/health
GET http://localhost:800X/status
GET http://localhost:800X/federation/status
```

### Torch Operations
```
POST http://localhost:800X/torch/send
GET http://localhost:800X/torch/history
```

### Federation Management
```
GET http://localhost:800X/federation/members
POST http://localhost:800X/federation/announce
```

## Troubleshooting

### Common Issues

1. **Redis Connection Failed**
   ```bash
   # Check Redis is running
   docker ps | grep redis
   
   # Check Redis connectivity
   redis-cli ping
   ```

2. **Valley Not Joining Federation**
   ```bash
   # Check valley logs
   docker logs tech_valley
   
   # Verify federation configuration
   cat config/federation/techvalley.yaml
   ```

3. **Messages Not Routing**
   ```bash
   # Check MCP broker status
   curl http://localhost:8001/federation/status
   
   # Monitor Redis channels
   redis-cli monitor
   ```

### Debug Mode

Run with debug logging:
```bash
LOG_LEVEL=DEBUG python examples/federation_demo.py
```

### Network Issues

Check Docker network:
```bash
docker network ls
docker network inspect examples_campfire_federation
```

## Extending the Demo

### Adding New Valleys

1. Create valley configuration in `config/federation/`
2. Add service to `docker-compose.federation.yml`
3. Update federation membership in demo script

### Custom Campfires

Add specialized campfires to valley configurations:

```yaml
campfires:
  - name: "data_scientist"
    type: "specialist"
    specialization: "data_science"
    tools:
      - "machine_learning"
      - "data_analysis"
      - "statistical_modeling"
```

### Federation Governance

Implement custom governance rules:

```python
federation_config = {
    "governance": {
        "consensus_required": True,
        "voting_threshold": 0.75,
        "decision_timeout": 300
    }
}
```

## Production Considerations

### Security

- Enable TLS for inter-valley communication
- Implement proper authentication and authorization
- Use secure key management for digital signatures
- Regular security audits and updates

### Scalability

- Use Redis Cluster for high availability
- Implement load balancing for valley endpoints
- Consider message queue partitioning
- Monitor resource usage and scaling metrics

### Reliability

- Implement circuit breakers for inter-valley calls
- Add retry mechanisms with exponential backoff
- Use health checks and automatic failover
- Implement proper logging and alerting

## Support

For questions and support:

- Check the main [README.md](../README.md)
- Review [TROUBLESHOOTING.md](../TROUBLESHOOTING.md)
- See [DEPLOYMENT.md](../DEPLOYMENT.md) for production setup

## License

This demo is part of the CampfireValley project and follows the same license terms.
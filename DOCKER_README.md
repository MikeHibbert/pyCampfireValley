# CampfireValley Docker Deployment

This guide explains how to run CampfireValley with web monitoring using Docker.

## Quick Start

1. **Clone the repository** (if you haven't already):
   ```bash
   git clone https://github.com/MikeHibbert/pyCampfireValley.git
   cd pyCampfireValley
   ```

2. **Set up environment variables**:
   ```bash
   cp .env.example .env
   # Edit .env with your API keys and configuration
   ```

3. **Build and run with Docker Compose**:
   ```bash
   docker-compose up --build
   ```

4. **Access the web interface**:
   - Open your browser to: http://localhost:8080
   - The web interface provides real-time monitoring of campfire processes

## What's Included

The Docker setup includes:

- **CampfireValley Web Server**: Main application with web monitoring interface
- **Redis**: For caching and inter-process communication
- **Prometheus**: For metrics collection and monitoring
- **Web Interface**: Real-time dashboard to observe campfire processes

## Configuration

### Environment Variables

- `OPENROUTER_API_KEY`: Your OpenRouter API key for cloud-based LLMs
- `OLLAMA_HOST`: Host for local Ollama instance (default: http://host.docker.internal:11434)
- `CAMPFIRE_VALLEY_LOG_LEVEL`: Logging level (default: INFO)

### Using Local Ollama

If you're running Ollama locally on your host machine:

1. Make sure Ollama is running: `ollama serve`
2. The default configuration should work: `OLLAMA_HOST=http://host.docker.internal:11434`

### Using Cloud LLMs

1. Get an API key from [OpenRouter](https://openrouter.ai/)
2. Set `OPENROUTER_API_KEY` in your `.env` file

## Monitoring and Observability

### Web Interface (Port 8080)
- **Dashboard**: Overview of all campfire processes
- **Real-time Logs**: Live log streaming from campfires
- **Metrics**: Performance and activity metrics
- **Process Management**: Start/stop/restart campfires

### Prometheus Metrics (Port 9090)
- Access Prometheus at: http://localhost:9090
- Metrics include campfire activity, processing times, and system health

### Health Checks
- Application health: http://localhost:8080/health
- Detailed status: http://localhost:8080/status

## Example Valley Workflow

The Docker container runs an example valley that demonstrates:

1. **Multiple Campfires**: Different specialized AI agents
2. **Collaborative Problem Solving**: Campfires working together
3. **Real-time Monitoring**: Web interface showing all activity
4. **Emergent Intelligence**: Complex behaviors from simple interactions

## Troubleshooting

### Container Won't Start
- Check logs: `docker-compose logs campfire-valley`
- Verify environment variables in `.env`
- Ensure ports 8080, 6379, and 9090 are available

### No LLM Responses
- Verify `OPENROUTER_API_KEY` is set correctly
- For Ollama: ensure it's running and accessible
- Check logs for API connection errors

### Web Interface Not Loading
- Verify container is healthy: `docker-compose ps`
- Check if port 8080 is accessible
- Review application logs for startup errors

## Development

### Building Locally
```bash
docker build -t campfire-valley .
```

### Running Individual Services
```bash
# Just the valley application
docker-compose up campfire-valley

# With dependencies
docker-compose up campfire-valley redis
```

### Accessing Container Shell
```bash
docker-compose exec campfire-valley bash
```

## Stopping the Services

```bash
# Stop all services
docker-compose down

# Stop and remove volumes (clears all data)
docker-compose down -v
```

## Data Persistence

The following data is persisted in Docker volumes:
- Valley data and configurations: `valley_data`
- Redis data: `redis_data`
- Prometheus metrics: `prometheus_data`
- Application logs: `./logs` (host directory)
# CampfireValley Docker Deployment

This guide covers the Docker stack that is currently used and tested in this repository.

## What The Stack Runs

| Service | Container | Host Port | Notes |
| --- | --- | --- | --- |
| Local valley web app | `campfire-valley-web` | `8000` | Main UI and local valley |
| Remote demo valley | `campfire-valley-remote` | `8001` | Second valley used for discovery and remote inspection |
| Redis | `campfire-redis` | internal | MCP broker and shared state |
| Prometheus | `campfire-prometheus` | `9090` | Metrics |
| Optional Discord bot | `campfire-discord-bot` | none | Sends Discord requests into the local valley |

## Quick Start

1. Clone the repository:

```bash
git clone https://github.com/MikeHibbert/pyCampfireValley.git
cd CampfireValley
```

2. Copy the environment file:

```bash
cp .env.example .env
```

3. Start the stack:

```bash
docker compose up -d --build
```

4. Open the services:

- Local valley UI: `http://localhost:8000`
- Remote demo valley UI: `http://localhost:8001`
- Prometheus: `http://localhost:9090`

## What To Expect After Startup

- `8000` shows the local valley graph and management UI
- `8001` shows the remote demo valley
- The local valley should discover the remote demo valley through Dock
- The left sidebar on `8000` should show the local valley, dock status, and discovered valleys

## Useful Commands

### Start or rebuild everything

```bash
docker compose up -d --build
```

### Rebuild only the web UIs

```bash
docker compose up -d --build campfire-valley campfire-valley-remote
```

### Check service status

```bash
docker compose ps
```

### View logs

```bash
docker compose logs -f campfire-valley
docker compose logs -f campfire-valley-remote
docker compose logs -f redis
```

### Stop the stack

```bash
docker compose down
```

## Environment Variables

These are the most commonly used compose variables:

- `OPENROUTER_API_KEY` - optional cloud model access
- `OLLAMA_HOST` - local Ollama host, default `http://host.docker.internal:11434`
- `VALLEY_IDENTIFIER` - stable local valley identifier used in discovery and routing
- `CAMPFIRE_IDENTIFIER` - default campfire identifier for inbound addressing
- `DISCORD_BOT_TOKEN` - enables the optional Discord bot
- `DISCORD_CHANNEL` - channel watched by the Discord bot
- `PORT` - override the host port mapped to the local valley UI

## Docker Volumes And Persistence

The stack persists state in Docker volumes for:

- local valley data
- remote valley data
- campfire configs
- embeddings
- logs
- Redis data
- Prometheus data

The repository also mounts:

- `./config` into the containers as read-only config input
- `./logs` and `./reports` for host-visible outputs

## Remote Demo Valley Notes

The second valley in compose is intentional and is useful for testing discovery flows:

- It runs at `http://localhost:8001`
- It uses Dock discovery so the local valley can see it
- Its campfires and services can be inspected from the local UI
- Remote admin actions remain disabled in the local UI

## Health Checks And Verification

### Check containers

```bash
docker compose ps
```

### Verify the UIs respond

- `http://localhost:8000/`
- `http://localhost:8001/`

### Verify discovery APIs

- `http://localhost:8000/api/dock/status`
- `http://localhost:8000/api/dock/valleys`
- `http://localhost:8000/api/services`

## Troubleshooting

### The web UI does not load

- Run `docker compose ps`
- Check `docker compose logs -f campfire-valley`
- Check that the configured port is not already in use

### The remote valley is not shown on `8000`

- Check `docker compose ps`
- Confirm both `campfire-valley-web` and `campfire-valley-remote` are running
- Check `docker compose logs -f campfire-valley`
- Check `docker compose logs -f campfire-valley-remote`
- Refresh `http://localhost:8000` after both services are healthy

### The app is up but there are no model responses

- Verify `OPENROUTER_API_KEY`, or
- Make sure your local Ollama service is running and reachable at `OLLAMA_HOST`

## Related Docs

- [README.md](README.md)
- [docs/web-ui.md](docs/web-ui.md)
- [examples/README_FEDERATION.md](examples/README_FEDERATION.md)

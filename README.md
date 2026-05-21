# CampfireValley

CampfireValley is a Campfires-based multi-agent workspace with a LiteGraph web UI, dock-based valley discovery, and a Docker stack that runs a local valley alongside a remote demo valley.

The workflow actively maintained in this repository is the web UI and Docker stack:

- Local valley UI on `http://localhost:8000`
- Remote demo valley UI on `http://localhost:8001`
- Redis-backed dock discovery and service catalog exchange
- Auditor-driven campfire management, including natural-language camper creation
- Visual graph links between valley, campfire, auditor, and campers

## What Is Available Now

### Web UI

- Local and remote valleys rendered on a LiteGraph canvas
- Left sidebar cards for the local valley, dock state, and discovered remote valleys
- Stable valley IDs shown in the sidebar and remote discovery cards
- Local and remote campfire detail panels with chat and action controls
- Snapshots, rounds, import/export, logs, tools, and model selection

### Local Campfire Management

- Chat directly with local campfires and campers
- Use the Auditor as the orchestrator for a campfire team
- Ask deterministic read-only questions about workflow, settings, tools, and execution order
- Create campers with natural language, for example:

```text
Create a new camper called summary-bot for this campfire.
```

- Reorder workflow steps with natural language
- Run `self audit` and `self audit cid:<correlation_id>`
- Clean up older legacy backend auditor campfires from the valley details panel

### Remote Valley and Campfire Discovery

- Discover remote valleys through Dock broadcasts
- Inspect remote valley route addresses, stable IDs, exposed campfires, and exposed services
- Open a remote campfire and inspect:
  - visible campfires
  - visible services
  - advertised remote campers
  - task types, capabilities, exposure, and rounds support
- Message remote campfires and add them to rounds
- Remote admin controls remain disabled by design

### Service Catalog and Addressing

- Local services are described through service manifests
- Discovery payloads include stable valley IDs, public addresses, and exposed service summaries
- Campfires can be resolved by identifier as well as by display name
- Remote service manifests include capabilities, task types, summaries, and valley-scoped addresses

## Quick Start

### Docker Compose

1. Clone the repository:

```bash
git clone https://github.com/MikeHibbert/pyCampfireValley.git
cd CampfireValley
```

2. Copy the environment file:

```bash
cp .env.example .env
```

3. Update `.env` if needed:

- `OPENROUTER_API_KEY`
- `OLLAMA_HOST`
- `VALLEY_IDENTIFIER`
- `CAMPFIRE_IDENTIFIER`
- `DISCORD_BOT_TOKEN`
- `DISCORD_CHANNEL`

4. Start the stack:

```bash
docker compose up -d --build
```

5. Open the running services:

- Local valley UI: `http://localhost:8000`
- Remote demo valley UI: `http://localhost:8001`
- Prometheus: `http://localhost:9090`

## Default Compose Services

| Service | Container | Host Port | Purpose |
| --- | --- | --- | --- |
| Local valley web app | `campfire-valley-web` | `8000` | Main UI and local valley |
| Remote demo valley | `campfire-valley-remote` | `8001` | Remote discovery target |
| Redis | `campfire-redis` | internal | MCP broker and shared state |
| Prometheus | `campfire-prometheus` | `9090` | Metrics |
| Optional Discord bot | `campfire-discord-bot` | none | Routes Discord requests into the valley |

## Common UI Workflows

### Create a Camper

1. Open `http://localhost:8000`
2. Select the local campfire or its Auditor
3. Send a message such as:

```text
Create a new camper called research-assistant for this campfire.
```

4. Wait for the graph to refresh
5. The new camper should appear with a single structural link from the parent campfire

### Inspect a Remote Campfire

1. Select a discovered remote valley
2. Select one of its visible campfires
3. Use the remote detail actions:
   - `Message This Campfire`
   - `Use In Rounds`
   - `Open Remote Valley`
   - `Show Visible Services`

### Work With Snapshots and Rounds

- `Save Valley` and `Load Valley` save and restore graph snapshots
- `Import Campfire` and export actions move campfire configs across valleys
- `Rounds` builds ordered local or remote service chains when those services are advertised

## Useful REST Endpoints

These endpoints are available from either web server instance:

- `GET /api/campfires`
- `GET /api/services`
- `GET /api/dock/status`
- `GET /api/dock/valleys`
- `GET /api/valley/details`
- `GET /api/campfire/details`
- `POST /api/voice/ingest`
- `POST /api/auditors/cleanup`
- `GET /api/rounds/catalog`
- `POST /api/rounds/run`
- `GET /api/valley/snapshots`
- `POST /api/valley/save`

## Voice Ingestion

`POST /api/voice/ingest` accepts text directly and can also operate in auditor mode.

Typical payload fields:

- `text`
- `campfire`
- `role_prompt`
- `auditor_mode`
- `admin_token` for admin-only actions

## Development

### Run Tests

```bash
pip install -e ".[dev]"
pytest
```

### Rebuild the UI Stack

```bash
docker compose up -d --build campfire-valley campfire-valley-remote
```

## Documentation

- [DOCKER_README.md](DOCKER_README.md) - running and operating the Docker stack
- [docs/web-ui.md](docs/web-ui.md) - day-to-day UI usage
- [examples/README_FEDERATION.md](examples/README_FEDERATION.md) - dock discovery and federation concepts
- [DEMO_GUIDE.md](DEMO_GUIDE.md) - current demo entry points
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) - troubleshooting guidance

## License

MIT License. See `LICENSE`.

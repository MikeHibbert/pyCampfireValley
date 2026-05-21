# Demo Guide

This repository still contains several older demo scripts, but the actively maintained and tested demo path is the Docker-based two-valley UI stack.

## Recommended Demo Path

Start the stack from the repository root:

```bash
docker compose up -d --build
```

Then open:

- `http://localhost:8000` for the local valley
- `http://localhost:8001` for the remote demo valley
- `http://localhost:9090` for Prometheus

## What This Demo Shows

The current demo path is focused on the web UI and live valley discovery:

- local valley management
- remote valley discovery through Dock
- remote-safe campfire inspection
- Auditor-driven camper creation
- rounds and snapshot workflows
- stable valley IDs and service manifests

## Suggested Walkthrough

1. Open `http://localhost:8000`
2. Confirm the local valley appears in the sidebar
3. Wait for the remote demo valley to appear in discovered valleys
4. Select the local campfire and inspect its Auditor
5. Create a camper with a message such as:

```text
Create a new camper called demo-helper for this campfire.
```

6. Select the remote valley and inspect one of its remote campfires
7. Use `Show Visible Services` or `Use In Rounds`

## Legacy Demo Scripts

The repository may still include older standalone demo scripts and notes. Treat those as exploratory or historical unless you have separately verified them in your environment.

## Useful Commands

### Rebuild the demo stack

```bash
docker compose up -d --build campfire-valley campfire-valley-remote
```

### Check status

```bash
docker compose ps
```

### View logs

```bash
docker compose logs -f campfire-valley
docker compose logs -f campfire-valley-remote
```

## Related Docs

- [README.md](README.md)
- [DOCKER_README.md](DOCKER_README.md)
- [docs/web-ui.md](docs/web-ui.md)
- [examples/README_FEDERATION.md](examples/README_FEDERATION.md)

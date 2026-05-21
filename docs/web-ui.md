# Web UI Guide

CampfireValley includes a LiteGraph-based web UI at `http://localhost:8000` for managing a local valley and inspecting remote valleys discovered through Dock.

## Main Areas Of The UI

### Left Sidebar

The sidebar shows:

- the local valley summary card
- the local valley stable ID
- dock status and current mode
- the number of known valleys
- discovered remote valleys with route address, stable ID, visible campfire count, and visible service count

### Graph Canvas

The graph shows:

- the local valley
- local campfires
- an Auditor node for each local campfire
- camper nodes attached to that campfire
- remote valley nodes and remote campfire nodes when discovered

Structural links are rebuilt from backend state so the valley, campfire, auditor, and camper connections stay in sync after refreshes and camper creation.

## Local Campfires

### Auditor Role

The Auditor is the orchestration node for a local campfire.

You can use it to:

- ask for workflow and execution order
- inspect settings, tools, and model state
- create campers
- update workflow order with natural language
- run `self audit`

### Creating A Camper

1. Select the Auditor for a local campfire
2. Use the message box at the bottom of the UI
3. Send a request like:

```text
Create a new camper called summary-bot for this campfire.
```

The graph should refresh and show the new camper connected to the parent campfire.

### Legacy Auditor Cleanup

If older builds created standalone backend auditor campfires, use:

- `Valley Details -> Cleanup Legacy Auditors`

## Remote Valleys And Remote Campfires

Remote nodes are read-only from the local valley's point of view.

### Remote Valley Details

Selecting a remote valley shows:

- remote route address
- remote stable ID
- visible campfires
- visible services
- discovery metadata from Dock

### Remote Campfire Details

Selecting a remote campfire shows a remote-safe details panel with:

- route
- remote valley name and stable ID
- service ID
- kind and exposure
- supported task types and capabilities
- visible campfires in the remote valley
- visible services in the remote valley
- visible remote campers when they are advertised

### Remote Campfire Actions

The remote campfire panel includes these actions:

- `Message This Campfire`
- `Use In Rounds`
- `Open Remote Valley`
- `Show Visible Services`

Remote admin actions are intentionally disabled.

## Rounds Builder

The `Rounds` panel can be used to build ordered service chains.

You can:

- load the service catalog
- add local services
- add remote services that are advertised through Dock discovery
- save a rounds plan
- preview it
- run it

## Snapshots And Transfer

### Save And Load Valley

- `Save Valley` stores a graph snapshot and backend configuration state
- `Load Valley` opens a searchable snapshot picker
- snapshots can be selected with mouse or keyboard
- old snapshots can be deleted from the picker

### Export And Import Campfires

- export a campfire's config, beliefs, and logs
- import a previously exported campfire into the running valley

## Chat, Logs, Voice, And Tools

### Chat Rendering

Chat responses render markdown, including:

- headings
- lists
- inline code
- fenced code blocks
- links

### Logs

Use `Logs` to view the selected campfire or camper log stream.

### Voice

The UI uses `POST /api/voice/ingest` for text and voice-style interactions.

### Tools And Model Selection

The tools panel allows per-node tool toggles and model selection when supported by that node.

## Useful API Endpoints

- `GET /api/campfires`
- `GET /api/services`
- `GET /api/dock/status`
- `GET /api/dock/valleys`
- `GET /api/campfire/details`
- `GET /api/valley/details`
- `POST /api/voice/ingest`
- `POST /api/auditors/cleanup`
- `GET /api/rounds/catalog`
- `POST /api/rounds/run`

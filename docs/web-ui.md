# Web UI Guide (LiteGraph)

CampfireValley includes a LiteGraph-based web UI at `http://localhost:8000` for visually managing a valley and chatting with campfires/campers.

## Snapshots

### Load Valley

- Click **Load Valley**
- Pick a snapshot from the searchable list
  - Click to select
  - Double-click to load
  - Type in the filter box to narrow long filenames
  - Use ↑/↓ to move selection, Enter to load, Esc to cancel
- Optional: delete old snapshots from the same dialog

Notes:
- Snapshot load restores backend campfires from the snapshot and reloads the saved graph.
- Snapshot load clears any previously persisted workflow/schedule state so stale “phantom” workflow steps do not leak into the new session.

## Layout

### Reset Layout

**Reset Layout** performs a radial auto-arrange:
- Valley node stays central
- Campfires place on hex-terminal anchors around the valley
- Campers place around their campfire using hex-terminal anchors

Connections are re-routed so campfire ↔ camper links attach to the nearest connector terminals.

## Chat (Markdown)

Chat messages render markdown:
- headings, lists, blockquotes
- inline code and fenced code blocks
- links

This is intended for readable workflow/config output and tool responses.

## Auditor Behavior

Auditors are campers with a special role (they are not backend campfires).

### Read-only questions (no mutations)

These queries respond deterministically and do not create/rename campers or change workflow/schedule:
- “What’s the execution order?”
- “What’s the workflow?”
- “What are the settings / environment / config?”
- “What model/tools are enabled?”

If there is no valid stored workflow for the linked campers, the UI reports **Execution order (visual)** derived from the current graph layout.

### Reordering steps

You can reorder workflow steps using natural language:

- `move Intake Camper to the first step and then editor/reporter camper 2nd`
- `move Risk Assessor Camper to 1st`

This persists a workflow for the parent campfire, and subsequent “what’s the workflow?” queries will return **Execution order (workflow)**.

## Legacy Cleanup

If older builds provisioned `* Auditor` as separate backend campfires, you can remove them via:

- **Valley Details → Cleanup Legacy Auditors**


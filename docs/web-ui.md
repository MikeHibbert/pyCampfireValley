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
- Workflow/schedule are persisted separately from snapshots. If you load a snapshot and the workflow doesn’t match what you expect, use the Auditor chat commands `show workflow`, `set workflow ...`, `clear workflow`, `show schedule`, `set schedule ...`, `clear schedule`.

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

## Chat (TTS)

- Use **⏹️ Stop Audio** to stop any in-progress text-to-speech playback immediately.

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

### Auditing execution

Use `self audit` to confirm that each camper actually ran (and in the correct order) for the last 30 minutes. To inspect a specific run, use:

- `self audit cid:<correlation_id>`

### Final report synthesis (Role Contributions)

The final step in the workflow is treated as the final report author. The orchestrator automatically requires the final report to include a `Role Contributions` section with step-numbered quotes from the upstream campers. This makes it easy to verify that the final report is a synthesis of multiple perspectives, not a single generic response.

## Legacy Cleanup

If older builds provisioned `* Auditor` as separate backend campfires, you can remove them via:

- **Valley Details → Cleanup Legacy Auditors**

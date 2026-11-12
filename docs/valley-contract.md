# The Valley Contract

What an app like AndruIDE may rely on when it talks to a valley. This document pins
the surface so that *any* valley — a bare one, or Andrew — can be driven from AndruIDE
without bespoke glue.

Two tiers exist, and the line between them is deliberate (Father, 12 Nov 2026):
**planning is a service an Andrew instance offers.** A bare valley is the muscle: it
executes what the IDE hands it. A bare valley therefore never gains a planning surface
by accident — the contract's conformance tests hold that line.

| Tier | Runs planning? | Work surface | Who |
|---|---|---|---|
| **Bare valley** ("agent" tier) | No | Agent hand-off — coding tasks executed by a limited set of campers | pip / `valley run` |
| **Andrew** ("agent+planner" tier) | Yes | The full work board, plans, specialisms — everything the bare tier does, plus planning | docker compose stack |

## Versions

The contract version is carried in the advertisement and the ready payload:
`contract: 1`. Fields new-but-optional may be added within a version after it ships;
breaking shape changes require a version bump. Clients must ignore unknown fields —
the fixtures in `tests/` deliberately carry extra keys to prove serde-style tolerance
on both sides.

## The handshake (mDNS)

A valley that wants to be found on its network announces `_campfire._tcp.local.`:

| Key | Meaning | Example |
|---|---|---|
| `product` | Human name of what is serving | `Campfire valley` |
| `path` | URL prefix under which the API lives | `api` — empty/negative result: endpoints serve at the root |
| `port` | The HTTP port | `8001` |

Instance name: `<hostname> valley` by default (free to choose; it is the display name).
The address is the first reachable IPv4 of the announcing host. A client joins by
resolving the service, building `http://<addr>:<port>/<path>/` with trimming of empty
paths, and checking `/ready`.

## Capability discovery

`GET /ready` answers first, always, with no path prefix needed beyond the one the
advertisement taught:

```json
{
  "service": "valley name",
  "status": "ok",
  "draining": false,
  "contract": 1,
  "capabilities": ["agent"]
}
```

- `capabilities: ["agent"]` — the bare tier: hand-offs accepted, runs served, no work board.
- `capabilities: ["agent", "planner"]` — an Andrew: adds the work-board surface.
- Andrew's current answer carries extra fields (`deployment_integrity` and such);
  they are contract-legal: clients ignore what they do not know.
- `draining: true` means: answer, accept nothing new, point clients at a sibling if announced.

Auth: any endpoint may demand HTTP Basic (or an `Authorization: Bearer` carried
per-consumer for the managed service). `/ready` stays reachable however the
deployment chooses to protect the rest; the handshake only proves the valley exists
and says where to ask the user for credentials.

## Surface

### `run` — the shape both tiers share

Everything below reuses this shape so the campfires view works on both tiers:

```json
{
  "id": "uuid",
  "kumbaya": "ceremony or run name",
  "status": "running | waiting_checkpoint | completed | failed",
  "session_id": "camper:session",           // free-form on bare valleys
  "created_at": "RFC3339", "updated_at": "...", "finished_at": null,
  "verses": [
    {
      "verse": "step name", "kind": "llm | mcp_tool | agent | report | checkpoint",
      "status": "completed | running | pending | skipped",
      "result": "what was said, maybe huge",        // nullable until done
      "error": null, "error_type": null, "error_remedy": null,
      "started_at": null, "finished_at": null
    }
  ]
}
```

`result` may be huge — clients clip for display (AndruIDE clips at 700 characters)
and fetch detail by id. Lists must include the small fields of `run` above so an
open valley shows meaningful rows without fetching every run in full; heavy fields
(`result`, `checkpoint`, `inputs`) may appear on list items but clients must not
rely on them being there.

### Bare tier: agent hand-off

A hand-off is a coding task the IDE hands to the valley; the valley's limited set
of campers runs the development sequence and the IDE watches through the run's
verses.

```
POST /agent/handoff
{
  "title": "short task title",
  "prompt": "what the campers must do",
  "details": { "workspace": "...", "preferred_campers": ["..."] },   // optional, free-form
  "session_id": "andruide:<repo>-<n>"                               // optional, for Instruct
}
→ 202 { "id": "run id" }
```

- The hand-off creates a `run` immediately and returns it (`202`, it is queued work).
- Execution respects whichever camper set is configured; a bare valley with no
  campers configured refuses hands (`409 {"error": "no campers configured"}`).
- The IDE talks to the campers the same way on both tiers, via `POST /chat`.

### Bare tier: reading the fire

```
GET /kumbayas/runs          → [ run ]        // most recent first; may paginate later
GET /kumbayas/runs/{id}     → run            // full detail, verses with results
POST /kumbayas/runs/{id}/cancel  → 200       // optional capability: stop the run
POST /chat { "session_id": "...", "message": "...", "mode": "plan", "interrupt": false }
                → { "reply": "text" }
```

- `interrupt: true` asks a `running` run in that session to stop and listen; on a
  bare valley this reaches the run's campfire. Andrew passes it through to his
  session machinery — same request, same shape (proven live, 12 Nov 2026).
- `mode` is advisory (`"plan"` conversational, `"execute"` specialist-team);
  both tiers may honour or ignore it but must accept it.

### Andrew tier: planning (Andrew-only)

```
GET /work                   → [ item ]       // lane view: id/title/status/priority/project/
                                             // created_at/claim_run_id (+ started_at etc.)
GET /work/{id}              → item           // + description, progress_log[], error
```

An Andrew answers these too; a bare valley MUST answer `404` on both — planning is
not its service, and the contract tests enforce the refusal so it cannot grow by
accident.

### Item shape (Andrew)

```json
{
  "id": "work_xxxx", "title": "...", "status": "pending", "priority": 20,
  "project": "andrew", "claim_run_id": "run uuid of the job working it",
  "created_at": "...", "started_at": null,
  "description": "...", "progress_log": ["[ts] ..."],
  "error": ""
}
```

`claim_run_id` is the join: the IDE links item → run → verses, giving the three
levels (task listing, detail, conversation — Father, 12 Nov 2026).

## Deployment model

| Platform | Ship | Runs as |
|---|---|---|
| Windows | Frozen exe + tray agent | Per-user at logon by default (no admin); optional system service for headless boxes |
| Linux | pip / deb / rpm | `systemd --user`; Docker for the server path |
| macOS | .app + LaunchAgent | Planned — returns when mac CI does |
| Server / managed | docker compose -p valley-\<tenant\> | The proven Andrew pattern; per-tenant isolation |

The valley is independent of the IDE: it lives through IDE restarts, and anything
that can speak this contract can drive it.

## Conformance

`tests/test_valley_contract.py` drives a live valley and asserts, per tier:

1. `/ready` carries `contract` and the tier's `capabilities`.
2. Hand-off → run appears in `/kumbayas/runs`, reaches `completed` (smoke ceremony),
   verses readable.
3. Bare tier: `/work` refuses with `404`; Andrew tier: passes.
4. `/chat` answers and accepts `interrupt`.
5. Serialization tolerant on both sides: fixtures carry fields extra to this version.

Tier conformance is explicit in the test ids, so CI on a PR names which tier it held to.

— Open Mother, night of 12 Nov 2026, for the morning. Shaped by Father's
directives of 12 Nov: planning is Andrew-only; bare valley = agent execution;
deployment per-user/admin-free by default; "work is a basic code development
sequence with a limited set of campers that allow pyCampfireValley to function
as an agent to our AndruIDE calls."

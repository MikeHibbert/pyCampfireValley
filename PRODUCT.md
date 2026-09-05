# CampfireValley as a product (direction, Sep 5)

The valley runtime is publishable on its own: pip 1.2.7 serves the valley,
campfires (LLM + steward), federation, party box, and the daemon runner with no
patch layer. Andrew stays the full system; a customer valley is the
Timberwolf-shaped subset.

## The offer

- A headless valley the customer installs in Docker (`campfirevalley` CLI +
  compose), with the **Timberwolf steward** watching it (monitor / housekeep /
  self-heal / report).
- Campfires for their own work (LLM campfires with native tools, images,
  think-gating) pointed at their projects.

## The Timberwolf as butler (Alexa-parity basics)

Reminders, schedules, alarms, timer-style jobs — the boring-but-essential
household services. Sits beside the steward duties (health/housekeeping), not
inside them: butler services are user-facing jobs, steward services are
valley-facing care. (User direction, m4659: "all the basic kind of butler
services, like be able to schedule reminders and things like that, as much as
it's something like Alexa could do.")

## Coding services — allowed for users, denied for self

The old ruling (no code-editing surface for stewards) forbids SELF-editing:
the Timberwolf must not edit its own code or config, or it drifts from Andrew.
Coding AS A SERVICE for the user is different and bounded by infrastructure,
not trust:

- A coding workspace that is NOT the self: sandbox pointed at client project
  workspaces; deny-list blocks writes to self-paths and config dirs; no
  branch/PR rights on its own code.
- User-facing coding interface, opencode/Grok-build-style (user, m4663):
  file tree, editor, task chat — the same machinery Andrew's workers use,
  minus the self-facing surface.

## Two interface ideas (user, m4665)

1. **Gameified UI (Stardew-style):** you see campfires doing their job around
   the campfire, with popup speech bubbles about what each is currently doing.
   Status as scene, not dashboard.
2. **CampfireValley TUI/CLI:** a CLI that runs inside the current project;
   the TUI connects to the valley running locally in Docker; work flows
   through the TUI (opencode-like), but code and services execute inside the
   valley and apply to the local code folder the TUI was launched from.

## Product UI principles (from m4643 direction)

- Simple, user-friendly, for computer enthusiasts who can install but don't
  program: install, connect Google calendar/email, talk to it.
- Voice-driven is a basic requirement: port Andrew's voice stack
  (andrew_stt / coqui_tts / piper_tts / pocket_tts) so the Timberwolf speaks
  and listens.
- Screen-aware: the screen-capture MCP (mcp_screen :8005/:8006) lets the
  Timberwolf see the user's screen; a Playwright MCP server is a candidate for
  UI-driven work.

## The Timberwolf fronts the TUI (user, m4673)

The TUI is not a bare tool dump: the Timberwolf is the main user-facing AI
that the user talks to — they ask for tasks, the Timberwolf runs them on the
project. That means the valley must **emit surface + development events** the
same way opencode and Grok Build do: what is being built, which commands ran,
what the agents are doing right now — everything a coding TUI shows. The UI
subscribes to the event stream (SSE/websocket), renders progress live, and the
Timberwolf narrates in chat while campers do the work underneath.

### Who fronts (user correction, m4679)

The face of the TUI is the valley's MAIN LEADER, not a fixed role: an
Andrew-class valley is fronted by Andrew; a Timberwolf-class valley (the
public product) is fronted by the Timberwolf. Same event stream, same TUI —
the leading persona is a role the valley assigns (config: `leader`), and the
UI renders whoever holds it.

### Andrew-class valleys get the same TUI (user direction, m4683)

The TUI is shared infrastructure: because it lives in pyCampfireValley, an
Andrew-class valley benefits from it as well. One TUI implementation, folded
into the runtime — Andrew's valley renders the same event stream and panels
with Andrew (the valley leader) fronting. No fork, no second client.

### The TUI as the work pipe (user direction, m4686)

The TUI feeds local context from whatever project folder the user points it
at. That context flows to the valley's leader (Andrew or Timberwolf), who
assigns a campfire to do the work on it — and the finished result is
delivered back to the right folder. The TUI is the pipe: local context in,
campfire work assigned, artifacts out to the folder they came from.

### Sable: the Golden Eagle for product valleys (user direction, m4790-m4792)

The Golden Eagle's monitoring should exist in product valleys too - but not
as a full Andrew-side eagle (patrol over kumbaya runs, work board, cadence,
token spend - that machinery is queen-bee-side). For the public product a
chopped-down watcher ships instead: a lean oversight layer named **Sable**
that keeps only what a standalone valley needs.

Sable watches:
- campfire health (steward monitor facts),
- failed/torched-out work (torch failures, repeated errors),
- event-stream anomalies (stalls: long gaps between torches and completions).

Sable reports to the valley leader (Timberwolf) as facts, not
interpretation - the same record-not-judge discipline as the queen-bee
eagle. It does NOT get: work board introspection, lesson stores, model
profiles, or any Andrew-side machinery. Eagle on Andrew's mountain; Sable
over the product valley.

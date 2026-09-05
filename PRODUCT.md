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

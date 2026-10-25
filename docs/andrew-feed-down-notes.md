# Andrew feed-down notes — structural patterns the Andrew project introduced

Why this document exists: the Andrew project (orchestrator built on
pyCampfireValley) has accumulated structural patterns that the package does
not have. Andrew's side keeps the full inventory with receipts
(`Andrew/docs/valley-extensions.md`); this file lists the candidates for
feeding down INTO the package, from the package's point of view, so the
feed-down starts from evidence rather than archaeology (coordinated between
both projects, Father 25 Oct 2026).

## Version caveat (read first)

The repo HEAD (`423a9bc`, events-bus tier) still declares
`setup.py version="1.2.5"` while PyPI ships `1.2.9` — published builds have
outrun the version string and the repo history. Before ANY feed-down work:

1. Diff the installed 1.2.9 wheel against repo HEAD to find true lineage.
2. `campfires.core.ollama` (the `OllamaConfig`/`OllamaClient` payload
   builder) ships in the wheel but has no counterpart in the clone — pull
   it out of a container's site-packages to reconstruct the full tree.
3. Bump the version and reconcile release flow (publishing key lives in
   this repo's own `.env`; never copy it elsewhere).

## Feed-down candidates (ordered by appetite)

1. **Floor-respect for `max_tokens`.** Today `llm_campfire.py`'s
   OllamaConfig branch treats any `max_tokens < 2048` as unset and forces
   4096. Hosts that want SMALL bounded campers (the Andrew project caps
   its specialist campers at 2048 exactly because sub-2048 values are
   structurally impossible) cannot express the intent. Fix: default 4096
   only when `max_tokens` is absent; honor explicit values, including
   sub-2048. Same check for OpenRouter `getattr(max_tokens, 1000)` and
   the ollama init default 2048.

2. **Per-campfire budget-stamp hook.** Andrew stamps camper budgets by
   wrapping THREE llm-dict sources on its side (specialist factory, skills
   loader, permanent-YAML loader). A single `provision_campfire`-adjacent
   hook in the package would make this a one-chokepoint host concern.

3. **`num_predict` option threading.** The ollama client builds payload
   options `{temperature, top_p, top_k, repeat_penalty, **config.options}`,
   then sets `data['options']['num_predict']` AFTER the spread — so any
   host-provided option-level `num_predict` is silently clobbered whenever
   `max_tokens` is truthy. Either document the precedence or stop
   overwriting when the option is explicitly present.

4. **Topic-keyed event routing — ALREADY DONE upstream.** PR #22
   (events-bus tier): ledger sinks receive everything; live subscribers
   subscribe to the topics they declare. Recorded here for the
   feed-down ledger's completeness.

5. **Degenerate-reply retry wrapper.** Cloud models occasionally emit
   token-soup (observed ~4% of calls across a 2661-row labeling run with
   glm). Andrew's wrapper detects degenerate replies via
   script-ratio/word-distinctness heuristics, retries once, adopts clean
   retries, and logs a `degenerate_retry` event receipt. Worth a
   provider-agnostic home in the package.

6. **Shadow-labeling pattern.** Fire-and-forget teacher labeling of live
   traffic (appends labeled pairs to a JSONL + a route stamp) at zero
   turn-latency cost — the data engine for future distillation of any
   packaged classifier. Generalizes beyond Andrew's intent classifier.

## What Andrew contributes back already

- Daily-ledger telemetry conventions (append-only JSONL per day; retired
  the single-file `routing_events.json` shape).
- The mined-leads promotion cycle: recurring model-behavior receipts
  (`reply_leak` events) get promoted into guard lists under test lockstep.
- The kindling/ember taxonomy (provisioned trained camper vs
  riding-persona) as naming vocabulary for package concepts that today
  have no words.

---
Maintained under declared-work discipline: amend in the same PR as the
package change it describes; receipts live in the Andrew repo
(`docs/valley-extensions.md`, PRs #1096-#1104).
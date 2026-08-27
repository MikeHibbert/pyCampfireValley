# New in CampfireValley 1.2.5

This page showcases the features added in the 1.2.5 release.

## Deterministic Watch Plan

The watch system orchestrates a campfire through `discover → plan → execute → verify → improve` rounds. By default the auditor LLM generates the plan for each round. For self-contained, well-specified tasks this LLM planning can be unnecessary ceremony — the auditor re-plans and re-discovers before any work happens.

`plan_mode` lets you skip the LLM plan/discover rounds and use the deterministic default watch plan directly, while **keeping the verify round** that checks the result before it ships.

### How to enable

Set `plan_mode` to `"deterministic"` in a campfire's `behavior.watch` config:

```python
from campfirevalley import Valley, CampfireConfig

valley = Valley()

cfg = CampfireConfig(
    name="my-campfire",
    type="LLMCampfire",
    config={
        "llm": {"provider": "ollama", "model": "your-model"},
        "behavior": {
            "watch": {
                "plan_mode": "deterministic",
            },
        },
    },
)

valley.provision_campfire(cfg)
```

### What changes

| Round | `plan_mode: "llm"` (default) | `plan_mode: "deterministic"` |
|-------|------------------------------|-------------------------------|
| discover | Auditor LLM picks campers | Skipped (deterministic default) |
| plan | Auditor LLM builds the plan | Skipped (deterministic default) |
| execute | Specialist runs the task | Specialist runs the task |
| verify | Auditor LLM checks the result | Auditor LLM checks the result |

The deterministic plan:
- assigns the preferred specialist camper to execute,
- keeps the auditor as the verifier,
- applies the fixed pass criteria ("the result answers the torch request", "important context is included", "the output is ready to send to the requester").

### When to use it

Use `"deterministic"` for tasks that are self-contained and already well-specified — a single specialist, a clear deliverable. It removes the plan/discover LLM drift and gets straight to work while still verifying the output.

Keep `"llm"` (the default) for open-ended tasks where the auditor genuinely needs to decide which campers to spin up and how to sequence them.

## Onboarding Script

`onboard.sh` is a one-shot installer that gets a CampfireValley workspace running with minimal friction.

```bash
./onboard.sh
```

It will:

- check for Python 3.8+ and pip,
- install the package in editable mode with dev extras,
- detect your LLM provider (OpenRouter if `OPENROUTER_API_KEY` is set, otherwise Ollama),
- detect an available model via `ollama list`,
- run a setup-only smoke test against the legal team demo,
- optionally bring up the Docker stack.

Useful flags:

| Flag | Effect |
|------|--------|
| `--no-install` | Skip the pip install |
| `--no-docker` | Skip the Docker bring-up |
| `--workspace <dir>` | Set the workspace directory |
| `--provider <name>` | Force a provider |
| `--model <name>` | Force a model |

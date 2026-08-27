[OPEN] Debug Session: watch-reboot-logs

- Session ID: `watch-reboot-logs`
- Started: `2026-06-22`
- Scope: inspect runtime evidence around the recent reboot and watch-related LLM errors

## Symptoms

- A recent live watch test reportedly caused another reboot.
- Docker logs reportedly showed many LLM-related errors.
- Need evidence from the most recent runtime logs before making any logic changes.

## Initial Hypotheses

1. The reboot was caused by resource pressure during a live watch run, such as repeated LLM calls or oversized responses.
2. The watch `improve` addition triggered a pathological response pattern that amplified prompt size or retry behavior.
3. The container did not cause the reboot directly, but the app emitted LLM/runtime errors immediately before the machine restarted.
4. The terminal/process handling around the live test was interrupted while the container itself remained healthy, and the reboot masked the original failure mode.
5. A separate recurring runtime issue, such as metrics/logging exceptions, contributed noise in logs and needs to be separated from the true reboot trigger.

## Evidence Plan

1. Read the last `1000` lines from `campfire-valley-web` logs.
2. Check container status and restart counts.
3. Identify repeated exception signatures, OOM indicators, connection resets, or crash loops.
4. Compare evidence against the hypotheses before deciding whether any code instrumentation is needed.

## Status

- Current phase: evidence collection
- Business logic changed: no

## Evidence Collected

- Checked `docker logs --tail 1000 campfire-valley-web`.
- Checked container runtime state with `docker inspect`.
- Checked container status history with `docker ps -a`.

## Findings

- `campfire-valley-web` is currently `running`, `healthy`, `restarts=0`, `oom_killed=false`, `exit_code=0`.
- The logs do **not** show evidence that the web container itself crashed or was OOM-killed during the inspected window.
- The logs do show repeated LLM/Ollama failures:
  - `Ollama request failed`
  - `Generation failed`
  - `Ollama generate failed, trying chat`
  - `Chat completion failed`
  - `LLM processing failed`
  - `LLM processing returned no response`
- These failures affected multiple torches and campers, including:
  - `watch_*` torches in `discover` / `plan`
  - `workflow_*` torches in workflow steps
  - `Main Campfire`, `Main Campfire Auditor`, `Intake Camper`, `Risk Assessor Camper`
- The logs also repeatedly show a separate warning:
  - `Error updating metrics: float() argument must be a string or a real number, not 'Queue'`

## Hypothesis Status

1. Resource-pressure reboot caused directly by `campfire-valley-web`: **not supported by current evidence**
   - No restart loop
   - No OOM-kill flag
2. Watch/improve flow triggered pathological LLM behavior: **partially supported**
   - Failures appear during watch and workflow torches
   - But evidence points more directly to LLM backend failures than a container crash
3. App emitted LLM/runtime errors immediately before the reboot: **supported**
   - Repeated no-response and Ollama failures are present in the inspected logs
4. Terminal/process interruption was mistaken for app crash: **plausible**
   - Current evidence shows healthy container state despite earlier disruption reports
5. Metrics warning is noise rather than root cause: **supported**
   - It is frequent but non-fatal, and the app continues serving requests

## Interim Conclusion

- The strongest confirmed issue is **repeated Ollama/LLM request failure leading to no-response watch/workflow steps**.
- The inspected evidence does **not** show that `campfire-valley-web` itself crashed.
- The reboot may have happened at the machine/Docker/runtime level outside this container, but that is not proven by the current container logs.

## Additional Ollama Evidence

- Ollama is running on the Windows host, not as a Docker container:
  - `ollama.exe serve`
  - listening on `localhost:11434`
- The installed model list includes `gemma4:e4b`, and the API is responsive at `/api/tags`.
- `GET /api/ps` returned no loaded models at idle, which is normal when nothing is currently active.
- Ollama processes restarted at about `2026-06-22 19:09:55`, matching the reported reboot window.
- The strongest log pattern in `C:\Users\Mike\AppData\Local\Ollama\server-1.log` is:
  - `POST /api/generate` or `POST /api/chat`
  - request runs normally and emits token timing
  - request ends at roughly `30.95s` to `30.99s`
  - response is `500`
  - log immediately shows `srv stop: cancel task`
- This pattern strongly suggests **client-side timeout/cancellation around 30 seconds**, not an Ollama process crash or out-of-memory event.

## Redis Warning Evidence

- Redis warning source addresses were internal Docker IPs, not public internet addresses.
- Docker network inspection identified:
  - `172.20.0.2` as `campfire-prometheus`
  - `172.20.0.3` as `campfire-redis`
  - `172.20.0.4` as `campfire-valley-web`
- `monitoring/prometheus.yml` currently configures:
  - job `redis`
  - target `redis:6379`
- That means Prometheus is attempting HTTP scraping against the raw Redis TCP port, which explains the Redis log:
  - `Possible SECURITY ATTACK detected... sending POST or Host: commands to Redis`
- Current evidence indicates this is a **monitoring misconfiguration / protocol mismatch**, not an actual attacker.

## Updated Hypothesis Status

1. Resource-pressure reboot caused directly by `campfire-valley-web`: **still not supported**
2. Watch/improve flow triggered pathological LLM behavior: **partially supported**
   - More rounds can increase prompt count and total runtime
   - But the direct failure signature is timeout/cancellation, not a watch-specific crash
3. App emitted LLM/runtime errors immediately before the reboot: **strongly supported**
4. Terminal/process interruption was mistaken for app crash: **still plausible**
5. Metrics warning is noise rather than root cause: **still supported**
6. Campfire Valley is timing out Ollama requests at about 30 seconds: **strongly supported by Ollama logs**
7. Redis "security attack" warning is caused by internal Prometheus scraping Redis incorrectly: **supported**

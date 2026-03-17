# Subagent + Claude Code CLI Runner

A lightweight alternative to ACP for long-running coding tasks inside OpenClaw.

Instead of relying on ACP session lifecycle, this example uses:

1. `sessions_spawn(runtime="subagent")`
2. a blocking shell wrapper (`run_v1.sh`)
3. a local Node.js runner (`runner.js`) that spawns Claude Code CLI directly
4. an optional file-based watcher (`watcher.js`) for progress inspection

The result is a small, auditable run-directory protocol that does **not** depend on ACP completion callbacks.

## What is included

- `runner.js`: hardened Claude Code CLI runner with total-timeout + two-stage stall watchdog
- `run_v1.sh`: convenience wrapper that returns stable `RUN_DIR` / `FINAL_SUMMARY_JSON`
- `watcher.js`: optional watcher that emits `started / heartbeat / milestone / stall / stall_cleared / completed / failed`
- `cleanup.sh`: retention-based cleanup for old run directories
- `test_watchdog_smoke.sh`: self-contained smoke test using mock `claude` binaries

## What is intentionally not included

- business-specific prompts or trading logic
- machine-local paths or user-specific configuration
- private run artifacts
- internal hardening report raw text

## Why use this pattern

| Concern | ACP-heavy path | This example |
|---|---|---|
| Completion truth | Depends on ACP lifecycle and follow-up plumbing | Process exit + terminal summary file |
| Zombie session risk | Possible | Not applicable |
| Long silent file-writing task | Easy to misclassify as idle | `workdir` activity keeps it alive |
| Timeout semantics | Often ambiguous | Explicit `total` vs `stall` timeout |
| Cleanup | Extra session hygiene needed | Local process-tree kill + run cleanup |

## Files

### `runner.js`

The runner launches:

```bash
claude --permission-mode bypassPermissions --print "<task>"
```

It writes a run directory containing:

- `meta.json`
- `status.json`
- `claude.stdout.log`
- `claude.stderr.log`
- `milestones.jsonl`
- `final-summary.json`
- `final-report.md`

Key behaviors:

- total timeout (`--timeout-s`)
- suspected stall threshold (`--idle-timeout-s`)
- stall grace window (`--stall-grace-s`)
- `SIGTERM -> SIGKILL` escalation (`--kill-grace-ms`)
- milestone extraction from explicit markers
- `stdout` / `stderr` / `workdir` activity tracking

### `run_v1.sh`

Blocking wrapper that:

- resolves the local `runner.js`
- defaults `WORKDIR` to the caller's current directory
- prints stable key/value output for shells and orchestrators

Example output:

```text
RUN_DIR=/abs/path/to/tmp/claude-runs/run-...
WORKDIR=/abs/path/to/repo
STATUS=/abs/path/to/.../status.json
FINAL_SUMMARY_PATH=/abs/path/to/.../final-summary.json
FINAL_SUMMARY_JSON={...}
```

### `watcher.js`

Consumes the run directory and emits structured progress events.

For new-format runs it reads `status.stall` as the source of truth.
For older runs it can still fall back to `--stall-ms` based detection.

### `cleanup.sh`

Deletes stale run directories while skipping `starting` / `running` runs by default.

## Quick start

Run from any project directory; the run output will go under `./tmp/claude-runs` unless you override paths.

### Wrapper path

```bash
bash examples/subagent-claude-runner/run_v1.sh \
  "Analyze this repository and summarize the architecture" \
  repo-summary
```

### Direct runner path

```bash
node examples/subagent-claude-runner/runner.js \
  --cwd "$PWD" \
  --label repo-summary \
  --task "Analyze this repository and summarize the architecture"
```

### Override timeouts

```bash
SUBAGENT_CLAUDE_TIMEOUT_S=3600 \
SUBAGENT_CLAUDE_IDLE_TIMEOUT_S=900 \
SUBAGENT_CLAUDE_STALL_GRACE_S=300 \
SUBAGENT_CLAUDE_KILL_GRACE_MS=5000 \
  bash examples/subagent-claude-runner/run_v1.sh "Your task here" my-task
```

### Watch a run once

```bash
node examples/subagent-claude-runner/watcher.js \
  --run-dir ./tmp/claude-runs/run-2026-03-16T12-34-56-789Z-demo \
  --once
```

### Clean old runs

```bash
bash examples/subagent-claude-runner/cleanup.sh --keep-days 3 --dry-run
bash examples/subagent-claude-runner/cleanup.sh --keep-days 3
```

## Milestone convention

If you want machine-readable progress without parsing natural language, ask Claude to print standalone lines such as:

```text
MILESTONE: started analysis
[milestone] wrote patch
[[milestone]] tests passed
```

Those lines are copied into `milestones.jsonl`.

## Watchdog semantics

The public example uses a **two-stage idle watchdog**.

### Activity sources

Any of these reset idle detection:

1. Claude `stdout`
2. Claude `stderr`
3. file activity under `workdir`

The runner ignores its own run-directory writes so it does not keep itself alive accidentally.

### State model

- `timeout.type=total`: exceeded total runtime
- `stall.suspected=true`: idle threshold crossed
- `stall.recoveredAt`: activity returned before grace expired
- `timeout.type=stall`: no recovery during grace window

Useful fields in `status.json` and `final-summary.json`:

- `lastActivityAt`
- `lastActivitySource`
- `activity.lastWorkdirAt`
- `activity.lastWorkdirPath`
- `activity.workdirEventCount`
- `stall.suspectedAt`
- `stall.deadlineAt`
- `stall.recoveredAt`
- `stall.hardTimeoutAt`
- `timeout.type`

## Smoke test

This repository includes a self-contained smoke test that does **not** require a real Claude installation.

```bash
bash examples/subagent-claude-runner/test_watchdog_smoke.sh
```

It covers two cases:

1. **quiet but still writing files** → should stay alive and complete
2. **true hard stall** → should enter suspected stall, then fail with `timeout.type=stall`

## OpenClaw integration pattern

Typical orchestrator flow:

```text
main agent
  -> sessions_spawn(runtime="subagent")
  -> subagent exec: bash examples/subagent-claude-runner/run_v1.sh "task" "label"
  -> wait for subagent completion
  -> read final-summary.json or final-report.md
  -> send only terminal-state result upstream
```

This keeps the execution model simple:

- one subagent per long task
- one run directory per task
- one terminal summary as truth

## Known limitations

- `fs.watch` recursion differs by platform; nested directory visibility may be weaker outside macOS/Windows
- `workdir` activity is coarse-grained: unrelated file writes in the same directory can delay stall detection
- milestones still require explicit prefixes; the runner does not infer them from free-form text
- `CLAUDE_EXTRA_ARGS` is split on whitespace only; it does not implement shell-grade quoting

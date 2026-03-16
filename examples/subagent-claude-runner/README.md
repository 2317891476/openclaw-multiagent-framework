# Subagent + Claude Code CLI Runner

A lightweight alternative to ACP for executing Claude Code tasks within OpenClaw. Instead of going through the ACP layer (which suffers from zombie sessions, concurrency deadlocks, and cross-process event loss), this approach uses `sessions_spawn(runtime="subagent")` combined with a Node.js runner that directly invokes the Claude Code CLI.

## Architecture

```
Main Agent (OpenClaw)
  ↓ sessions_spawn(runtime="subagent")
  Subagent Session
    ↓ exec: bash run_v1.sh "task prompt" "label"
    run_v1.sh (blocking wait)
      ↓ node runner.js --task "..."
      Runner → spawn claude --permission-mode bypassPermissions --print "task"
        ↓
        Claude Code CLI (executes coding task)
        ↓
      Runner ← collects stdout/stderr/milestones/status
      Runner → writes run directory (status.json / final-summary.json / final-report.md)
    run_v1.sh ← parses runner stdout → outputs RUN_DIR / STATUS / FINAL_SUMMARY_JSON
  Subagent Session ← exec returns
  ↓ subagent_ended event
  spawn-interceptor → notifies parent (CLI fallback)
Main Agent ← receives completion notification
```

## Why Not ACP?

| Issue | ACP | This Approach |
|-------|-----|---------------|
| Zombie sessions | Common (session stays open after process exits) | Impossible (CLI exits = done) |
| Concurrent deadlocks | `maxConcurrentSessions` exhaustion | No session pool needed |
| Cross-process event loss | `onAgentEvent` only works in-process | No cross-process dependency |
| Completion detection | Requires 5-layer polling pipeline | Native `subagent_ended` event |
| Process cleanup | Manual `acpx` garbage collection | Dual timeout watchdog + SIGTERM→SIGKILL |

## Components

### `runner.js` — Claude Code CLI Process Manager

Spawns `claude --permission-mode bypassPermissions --print <task>` and manages the entire lifecycle:

- **Dual timeout watchdog**: Total runtime (default: 1800s) + idle timeout (default: 600s)
- **Graceful shutdown**: SIGTERM → grace period → SIGKILL escalation
- **Process group kill**: Uses `detached: true` + `-pid` to clean entire process tree
- **Milestone extraction**: Captures `MILESTONE: xxx` / `[milestone] xxx` from stdout
- **Heartbeat**: Periodic status.json updates for external monitoring
- **Auto-detection**: Finds Claude Code CLI in PATH, npm global, or custom locations
- **Structured output**: `final-summary.json` (machine-readable) + `final-report.md` (human-readable)

### `run_v1.sh` — Orchestration Wrapper

Simplified blocking wrapper that:
1. Runs `node runner.js` with configurable timeouts
2. Captures runner output to temp file
3. Parses `RUN_DIR`, `FINAL_SUMMARY_PATH`, `FINAL_SUMMARY_JSON` from output
4. Returns runner exit code

### `watcher.js` — Optional Progress Monitor

Polls the run directory for status changes and emits structured events:
- `started` / `heartbeat` / `milestone` / `stall` / `completed` / `failed`

Not needed when using `run_v1.sh` (which blocks until completion).

### `cleanup.sh` — Run Directory Garbage Collection

Cleans old run directories with configurable retention:
- `--keep-hours N` / `--keep-days N`
- `--dry-run` for preview
- Skips running tasks by default (`--include-running` to override)

## Quick Start

```bash
# 1. Run with v1 wrapper (recommended)
bash run_v1.sh "Analyze the codebase and create a summary" my-task

# 2. Run runner directly
node runner.js --label smoke --task "echo hello"

# 3. With custom timeouts
SUBAGENT_CLAUDE_TIMEOUT_S=1200 \
SUBAGENT_CLAUDE_IDLE_TIMEOUT_S=300 \
bash run_v1.sh "Your task here" label

# 4. Clean old runs
bash cleanup.sh --keep-days 3 --dry-run
bash cleanup.sh --keep-days 3
```

## Run Directory Structure

Each run creates a directory under `tmp/claude-runs/`:

```
run-2026-03-16T12-34-56-789Z-my-task/
├── meta.json              # Command, paths, timeout policy
├── status.json            # Live state (runner updates heartbeat)
├── claude.stdout.log      # Raw Claude stdout
├── claude.stderr.log      # Raw Claude stderr
├── milestones.jsonl       # Extracted milestones
├── final-summary.json     # Terminal state (machine-readable)
└── final-report.md        # Terminal state (human-readable)
```

## Integration with OpenClaw

In your agent AGENTS.md or TOOLS.md, configure the default coding path:

```markdown
## Coding Task Execution

Default: `sessions_spawn(runtime="subagent")` with exec:

```bash
bash scripts/run_v1.sh "task prompt" "task-label"
```

The subagent runs blocking. On completion, `spawn-interceptor` detects `subagent_ended` and wakes the parent via CLI fallback (~20s latency).
```

## Known Limitations

- **CLI fallback latency**: `spawn-interceptor`'s `subagent.run()` is unavailable outside gateway request context, so completion notification falls back to CLI (~20s delay)
- **No intermediate progress to parent**: Claude Code transcript writes happen at LLM turn boundaries. Milestones require explicit `MILESTONE:` markers in Claude output
- **Single-node**: File-based run directory assumes collocated processes
- **No auto-retry**: Runner detects failure but does not retry. Retry logic belongs in the orchestration layer

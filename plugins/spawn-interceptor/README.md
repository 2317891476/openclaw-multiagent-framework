# spawn-interceptor

> Zero-config OpenClaw plugin for ACP task lifecycle management. Tracks spawns, relays progress, detects completion (including failures), notifies Discord, and actively wakes parent agents — without any agent-side code changes.

## The Problem

OpenClaw's ACP has five fundamental gaps (each discovered in production):

1. **No completion signal** — `sessions_spawn(runtime="acp")` returns immediately. When the child finishes, nothing happens. No callback, no event, no webhook. ([#40272](https://github.com/openclaw/openclaw/issues/40272))
2. **Broken event relay** — `parentStreamRelay` has a cross-process bug ([#45205](https://github.com/openclaw/openclaw/issues/45205)): ACP runs in a gateway subprocess, so `onAgentEvent` never crosses the process boundary. Only synthetic `start`/`stall` notices reach the parent.
3. **Zombie accumulation** — Dead sessions stay `closed: false` in `~/.acpx/sessions/index.json`, consuming `maxConcurrentSessions` slots. ([PR #46949](https://github.com/openclaw/openclaw/pull/46949))
4. **Batch spawn failure** — Concurrent ACP spawns trigger `ACP_SESSION_INIT_FAILED` due to metadata race conditions. Failed sessions get GC'd and misidentified as "completed". (v3.6 fix)
5. **Passive hook model** — `before_prompt_build` only fires when someone sends a message to the agent. Completed tasks queue up indefinitely if no one triggers a new turn. (v3.6 fix)

Result: agents dispatch tasks into a black hole with zero visibility, false completion reports, and no automatic continuation.

## Architecture

```
┌─────────────────── spawn-interceptor v3.6.0 ───────────────────┐
│                                                                 │
│  HOOKS (system-level interception)                              │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ before_tool_call   → inject streamTo + taskId + relay    │   │
│  │                      + immediate start notification      │   │
│  │ after_tool_call    → link ACP session + streamLogPath    │   │
│  │                      + detect spawn failures (v3.6)      │   │
│  │ subagent_spawning  → enrich with Discord context         │   │
│  │ subagent_spawned   → precise session key binding         │   │
│  │ subagent_ended     → L1 completion detection             │   │
│  │ before_prompt_build→ inject completion report            │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                 │
│  BACKGROUND WORKERS                                             │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ Progress relay (15s tick, adaptive rate)                  │   │
│  │   <2min: every tick │ 2-10min: 60s │ >10min: 5min        │   │
│  │                                                          │   │
│  │ ACP session poller (15s) → L2 completion/failure detect  │   │
│  │   + failure heuristics: never-used / too-short (v3.6)    │   │
│  │ Stale reaper (5min) → L3 timeout fallback                │   │
│  │ ACPX zombie cleanup → close dead sessions                │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                 │
│  PROGRESS READING (dual-mode)                                   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ Incremental (relay): offset-tracked, noise-filtered      │   │
│  │ Full (completion): read from byte 0, idempotent          │   │
│  │ Heartbeat: stall detected → emit liveness signal         │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                 │
│  POST-COMPLETION (v3.6)                                         │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ subagent.run(parentSessionKey) → trigger parent turn     │   │
│  │ prompt injection → parent gets completion report         │   │
│  │ Discord notification → user sees result                  │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                 │
│  PERSISTENCE                                                    │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ task-log.jsonl      → single source of truth             │   │
│  │ .pending-tasks.json → survives gateway restart           │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

## Design Decisions

### Why plugin hooks instead of wrapper functions?

Agents have "muscle memory" from training. They call `sessions_spawn` directly. Wrapper functions get skipped. Even `MUST`/`P0` prompt directives fail with <100% compliance. System-level `before_tool_call` hooks are **invisible to the agent — impossible to bypass**.

### Why two read modes (incremental vs full)?

v3.3 used one `readProgress` for both relay and completion. Relay consumed the file offset → completion found nothing left → **empty completion reports** for a week.

- **Incremental**: offset-tracked, filters noise, for periodic relay
- **Full**: reads entire file, idempotent, for all completion paths

### Why failure detection in the poller (v3.6)?

Prior to v3.6, `session closed` always meant "assumed complete". But `closed` has three causes:

| Cause | `last_used_at` | Output | Correct status |
|-------|----------------|--------|---------------|
| Normal completion | > created_at | Has content | `assumed_complete` |
| Init failure + GC | = created_at | Empty | **`failed`** |
| Crash + GC | > created_at | Partial | `assumed_complete` |

v3.6 checks `last_used_at == created_at` (never used) and `age < 2min + no output` (closed too quickly) to distinguish failures from completions.

### Why active parent wake (v3.6)?

`before_prompt_build` is passive — it only runs when the agent starts a new turn. If no one sends a message, completion reports queue forever. `pluginRuntime.subagent.run()` actively delivers a message to the parent session, triggering a new turn and prompt injection.

### Why adaptive relay frequency?

Fixed 15s relay floods Discord during 30-minute tasks (120+ messages).

| Task age | Interval | Rationale |
|----------|----------|-----------|
| < 2 min  | 15s | Maximum visibility for short tasks |
| 2–10 min | 60s | Reduce noise |
| > 10 min | 5 min | Summary-level only |

## Version History

| Version | Key Changes |
|---------|-------------|
| **v3.6.0** | **Failure detection**: distinguish init failure from completion. **Active parent wake** via `subagent.run()`. **Spawn error detection** in `after_tool_call`. |
| **v3.5.0** | Immediate start notification. Heartbeat on stall. Adaptive relay. |
| **v3.4.0** | Split full/incremental read. 42 unit tests. |
| **v3.3.0** | Full transcript in completion reports. |
| **v3.2.0** | Transcript fallback for #45205. |
| **v3.0.0** | Simplify to `streamTo: "parent"` injection. |

## Testing

```bash
node test.js  # 42 tests, ~500ms
```

## Installation

```bash
cp -r plugins/spawn-interceptor ~/.openclaw/plugins/
```

## Known Limitations

- **Single-turn tasks**: No intermediate progress (transcript writes at turn completion only). Heartbeats provide liveness.
- **Same-host only**: File system polling requires co-located processes.
- **Concurrent spawn instability**: 4 concurrent ACP spawns had 50% init failure rate. v3.6 detects but can't prevent.
- **No auto-retry**: Detects and reports, doesn't retry. Retry is orchestrator's responsibility.

## Related Issues & PRs

- [#45205](https://github.com/openclaw/openclaw/issues/45205) — Cross-process event relay broken
- [#40272](https://github.com/openclaw/openclaw/issues/40272) — `notifyChannel` silently ignored
- [PR #46308](https://github.com/openclaw/openclaw/pull/46308) — Register ACP in subagent lifecycle
- [PR #46949](https://github.com/openclaw/openclaw/pull/46949) — Back-pressure eviction for zombies
- [PR #46952](https://github.com/openclaw/openclaw/pull/46952) — Fix fetch proxy for bot identity

# mini-watcher — Minimal Runnable Task Monitoring

A self-contained, zero-dependency task monitoring implementation extracted from
the internal OpenClaw production system. Demonstrates the core watcher pattern
in ~300 lines of Python.

## What It Does

```
Register task → Watcher polls status files → Detects state changes → Sends notifications
```

This is the same pattern used in the full `task_callback_bus`, stripped down to
the essential loop: **poll → detect → notify**.

## Quick Start

```bash
cd examples/mini-watcher
python demo.py
```

Expected output:

```
==============================================================
  Mini-Watcher End-to-End Demo
==============================================================

Working directory: /tmp/mini-watcher-demo-xxxxx

[1/3] Task registered: demo-001

[2/3] Background worker started (will take ~12s)

[3/3] Watcher polling every 2 seconds...
------------------------------------------------------------
12:00:02 [watcher] INFO [UPDATE] [demo-001] registered -> started | Worker initialized | owner=main
12:00:06 [watcher] INFO [UPDATE] [demo-001] started -> in_progress | Analyzing data... | owner=main
12:00:10 [watcher] INFO [UPDATE] [demo-001] in_progress -> in_progress | Generating report... | owner=main
12:00:14 [watcher] INFO [OK] [demo-001] in_progress -> completed | Analysis complete | owner=main
------------------------------------------------------------

Task reached terminal state: completed
```

## Files

| File | Lines | Purpose |
|------|-------|---------|
| `models.py` | ~70 | `Task` and `StateResult` dataclasses |
| `store.py` | ~90 | JSONL-based persistence with file locking |
| `watcher.py` | ~130 | Poll loop, state detection, notification |
| `demo.py` | ~100 | End-to-end demo with simulated worker |
| `tests/` | ~400 | 79 unit tests covering all three layers |

## Tests

```bash
# Run all 79 tests
python3 -m pytest tests/ -v

# Run specific test file
python3 -m pytest tests/test_models.py -v     # 27 tests — data model
python3 -m pytest tests/test_store.py -v       # 30 tests — persistence
python3 -m pytest tests/test_watcher.py -v     # 22 tests — orchestration
```

Tests are organized by architectural layer:
- **test_models.py**: Pure data logic — no I/O, millisecond execution
- **test_store.py**: File I/O with temp dirs — CRUD, locking, compact, corruption recovery
- **test_watcher.py**: Integration — full lifecycle, expiration, multi-task, idempotency

See [../../TESTING.md](../../TESTING.md) for the full testing guide.

---

## How To Extend

### Custom Notifier

Replace the `notify()` function in `watcher.py`:

```python
import requests

def notify(task, old_state, new_state, summary=""):
    # Send to Slack
    requests.post(SLACK_WEBHOOK, json={
        "text": f"[{task.task_id}] {old_state} → {new_state}: {summary}"
    })
    # Send to Discord via OpenClaw
    # os.system(f'openclaw agent --deliver "Task {task.task_id}: {new_state}"')
    return True
```

### Custom State Checker

Replace `check_status_file()` for non-file sources:

```python
def check_github_pr(task):
    """Check GitHub PR status via API."""
    resp = requests.get(f"https://api.github.com/repos/{task.metadata['repo']}/pulls/{task.metadata['pr']}")
    data = resp.json()
    merged = data.get("merged", False)
    state = "completed" if merged else data.get("state", "open")
    return StateResult(state=state, terminal=merged)
```

### Run as Cron

```bash
# Every 3 minutes
*/3 * * * * cd /path/to/mini-watcher && python -m mini_watcher.watcher --once --tasks-file ~/.openclaw/shared-context/monitor-tasks/tasks.jsonl >> /var/log/watcher.log 2>&1
```

## Design Decisions

1. **No external dependencies** — stdlib only (dataclasses, json, fcntl, argparse)
2. **File-based state** — status checked by reading JSON files, not APIs
3. **Append-only JSONL** — safe for concurrent writes, compact when needed
4. **Pluggable notification** — default prints to stdout + writes JSON files
5. **Idempotent polls** — same state detected twice won't trigger duplicate notifications

## Relation to Full Implementation

This is a simplified version. The production `task_callback_bus` adds:
- Pluggable adapters (XHS, GitHub, Cron, generic-exec)
- Dead letter queue for failed deliveries
- Discord panel bridge (auto-updating status embeds)
- Terminal bridge (auto-creating follow-up/dispatch files)
- Content-hash deduplication
- Delivery intent tracking (first_send vs retry vs repair)
- Audit logging with rotation

See `CAPABILITY_LAYERS.md` for the full L1/L2/L3 breakdown.

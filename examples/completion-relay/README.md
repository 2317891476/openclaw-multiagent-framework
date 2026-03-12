# completion-relay

Lightweight listener for ACP task completion notifications.

## Overview

When the `spawn-interceptor` plugin injects completion relay instructions into
ACP prompts, ACP sub-agents send `sessions_send` messages to a dedicated
completion-relay session upon finishing their work. This listener picks up
those messages and dispatches notifications.

## How It Works

```
ACP sub-agent finishes work
    ↓
sessions_send(sessionKey="agent:main:completion-relay",
              message={"type": "acp_completion", "taskId": "...", ...})
    ↓
completion_listener.py (cron every 1 min)
    ↓
  1. Reads messages from completion-relay session
  2. Parses completion notifications
  3. Updates task-log.jsonl with completion status
  4. Prints notification to stdout (extend for Discord/Telegram)
```

## Usage

```bash
# Single check
python completion_listener.py --once

# Continuous monitoring (every 60 seconds)
python completion_listener.py --loop --interval 60

# Custom task log location
python completion_listener.py --once --task-log /path/to/task-log.jsonl
```

### Cron Setup

```bash
# Add to crontab: check every minute
*/1 * * * * cd ~/.openclaw/repos/openclaw-multiagent-framework/examples/completion-relay && python3 completion_listener.py --once >> /tmp/completion-relay.log 2>&1
```

## Message Format

The listener expects JSON messages in the completion-relay session:

```json
{
  "type": "acp_completion",
  "taskId": "tsk_20260312_abc123",
  "status": "completed",
  "summary": "Analyzed 3 files, found 2 performance bottlenecks",
  "error": ""
}
```

## Extending Notifications

The `notify()` function currently prints to stdout. To add Discord/Telegram:

```python
def notify(task_id, status, summary, error=""):
    # Default: stdout
    log.info(f"[{status}] {task_id}: {summary}")
    
    # Add Discord webhook
    requests.post(DISCORD_WEBHOOK, json={
        "content": f"Task {task_id} {status}: {summary}"
    })
```

## Compared to the Old Watcher

| Aspect | Old Watcher (task_callback_bus) | Completion Relay |
|--------|-------------------------------|------------------|
| Method | Polls 6+ status files every 5 min | Reads 1 session on demand |
| Code | 9,600 lines | ~200 lines |
| Latency | Up to 5 minutes | < 1 minute (or real-time with hooks) |
| Registration | Agent must remember to use wrapper | Automatic via plugin |
| Reliability | notifications_sent: 0 (observed) | Direct sessions_send |

## Files

- `completion_listener.py` — Main listener script
- `README.md` — This file

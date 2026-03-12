# completion-relay

Lightweight listener for task completion events from `task-log.jsonl`.

轻量级任务完成事件监听器，从 `task-log.jsonl` 读取事件。

## How It Works / 工作原理

The `completion_listener.py` does **not** detect completion itself. It reads the unified event stream `task-log.jsonl`, which is written by:

`completion_listener.py` **不**自己检测完成。它读取统一事件流 `task-log.jsonl`，该文件由以下组件写入：

| Writer / 写入者 | Scope / 范围 | Latency / 延迟 |
|----------------|-------------|----------------|
| spawn-interceptor `subagent_ended` hook | runtime=subagent | <1s |
| spawn-interceptor ACP Session Poller | runtime=acp | ~15s |
| spawn-interceptor Stale Reaper | stuck tasks | 30min |
| task-callback-bus WatcherBus | external tasks | adapter-driven |

```
spawn-interceptor / WatcherBus
         │  writes events
         ▼
  task-log.jsonl
         │  reads events
         ▼
  completion_listener.py
         │
         ▼
  stdout / Discord / Telegram
```

## Usage / 用法

```bash
# Single check / 单次检查
python3 completion_listener.py --once

# Continuous monitoring (every 30 seconds) / 持续监听
python3 completion_listener.py --loop --interval 30

# Custom task log location / 自定义日志路径
python3 completion_listener.py --once --task-log /path/to/task-log.jsonl
```

### Cron Setup / 定时任务

```bash
*/1 * * * * cd /path/to/completion-relay && python3 completion_listener.py --once >> /tmp/completion-relay.log 2>&1
```

## Event Format / 事件格式

Events in `task-log.jsonl` follow this structure:

```json
{
  "taskId": "tsk_20260313_abc123",
  "agentId": "main",
  "runtime": "acp",
  "status": "completed",
  "completionSource": "acp_session_poller",
  "spawnedAt": "2026-03-13T01:30:00.000Z",
  "completedAt": "2026-03-13T01:32:15.000Z"
}
```

Key fields / 关键字段:
- `status`: `spawning` → `completed` / `failed` / `timeout`
- `completionSource`: `subagent_ended` | `acp_session_poller` | `stale_reaper` | `watcher_bus`

## Extending Notifications / 扩展通知

The `notify()` function currently prints to stdout. To add webhooks:

```python
def notify(task_id, status, summary, error=""):
    log.info(f"[{status}] {task_id}: {summary}")
    
    # Discord webhook
    requests.post(DISCORD_WEBHOOK, json={
        "content": f"Task {task_id} {status}: {summary}"
    })
```

## Tests / 测试

```bash
python3 -m pytest tests/ -v
```

15 test cases covering cursor tracking, event parsing, and notification dispatch.

15 个测试用例，覆盖游标追踪、事件解析和通知分发。

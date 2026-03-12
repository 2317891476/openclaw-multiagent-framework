# Examples

Reference implementations demonstrating the OpenClaw Agent Protocol concepts.

## mini-watcher/ (Start Here)

**A complete, runnable task monitoring system in ~300 lines of Python.**

This is the recommended starting point — it implements the core watcher pattern (poll → detect → notify) with zero external dependencies.

```bash
cd examples/mini-watcher
python3 demo.py
```

| File | Purpose |
|------|---------|
| `models.py` | Task and StateResult dataclasses |
| `store.py` | JSONL persistence with file locking |
| `watcher.py` | Poll loop, state detection, notification |
| `demo.py` | End-to-end demo with simulated worker |
| `README.md` | Detailed docs, extension patterns |

See [mini-watcher/README.md](mini-watcher/README.md) for customization (replace notify backend, add API state sources, run as cron).

---

## protocol_messages.py

Message format implementation per AGENT_PROTOCOL.md.

**Demonstrates:**
- Agent identity format (`agent:<name>:<transport>:<channel>`)
- Handoff message creation (Section 4)
- ACK message handling (Section 4.2)
- Message parsing and validation

```bash
python3 examples/protocol_messages.py
```

### Usage

```python
from examples.protocol_messages import (
    AgentIdentity, HandoffContext, create_handoff_message
)

sender = AgentIdentity("trading", "discord", "trading-room")
receiver = AgentIdentity("macro", "discord", "macro-room")
context = HandoffContext(reason="Need macro analysis", priority="high")
msg = create_handoff_message(sender, receiver, "task_001", "Analyze FOMC", context)
```

---

## task_state_machine.py

Task lifecycle state machine per AGENT_PROTOCOL.md Section 5.

**Demonstrates:**
- State transitions (PENDING → ACKNOWLEDGED → IN_PROGRESS → COMPLETED)
- State validation (prevents invalid transitions)
- Status file persistence
- Terminal states (COMPLETED, FAILED, CANCELLED)

```bash
python3 examples/task_state_machine.py
```

### Usage

```python
from examples.task_state_machine import TaskStateMachine, TaskState

task = TaskStateMachine("task_001", "trading")
task.transition_to(TaskState.ACKNOWLEDGED, "Task accepted")
task.mark_started("Fetching data...")
task.mark_completed(report_file="report.md")
```

---

## test-protocol.sh

Shell-based protocol validation script.

```bash
chmod +x examples/test-protocol.sh
./examples/test-protocol.sh
```

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENCLAW_STATUS_DIR` | `./shared-context/job-status` | Status file location |
| `OPENCLAW_NOTIFICATION_DIR` | `./shared-context/monitor-tasks/notifications` | Notification output |

## Notes

- `mini-watcher/` is production-quality — the same pattern runs in the internal system
- Other examples are reference implementations for understanding the protocol
- See AGENT_PROTOCOL.md for full specification, ARCHITECTURE.md for system design

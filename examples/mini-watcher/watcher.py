"""
Minimal task watcher -- polls status files, detects state changes, sends notifications.

Usage:
    python -m mini_watcher.watcher --once                 # single poll cycle
    python -m mini_watcher.watcher --loop --interval 30   # continuous polling

No external dependencies required (stdlib only).
"""

import argparse
import json
import os
import sys
import time
import logging
from datetime import datetime
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


from models import Task, StateResult, TERMINAL_STATES
from store import TaskStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [watcher] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("watcher")


def check_status_file(task: Task) -> Optional[StateResult]:
    """Read a task's status_file and return its current state."""
    path = os.path.expanduser(task.status_file)
    if not path or not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            data = json.load(f)
        state = data.get("state", "unknown")
        terminal = state in TERMINAL_STATES
        summary = data.get("summary", "")
        return StateResult(state=state, terminal=terminal, summary=summary)
    except (json.JSONDecodeError, OSError) as e:
        return StateResult(state="error", error=str(e))


def notify(task: Task, old_state: str, new_state: str, summary: str = "") -> bool:
    """
    Send a notification about a state change.

    Default: prints to stdout + writes JSON file.
    Override or extend for Discord/Slack/webhook/etc.
    """
    if new_state == "completed":
        icon = "OK"
    elif new_state == "failed":
        icon = "FAIL"
    elif new_state == "timeout":
        icon = "TIMEOUT"
    else:
        icon = "UPDATE"

    parts = [
        "[{}] [{}] {} -> {}".format(icon, task.task_id, old_state, new_state)
    ]
    if summary:
        parts.append("| " + summary)
    if task.owner:
        parts.append("| owner=" + task.owner)
    if task.reply_to:
        parts.append("| reply_to=" + task.reply_to)

    msg = " ".join(parts)
    log.info(msg)

    # Also write notification to file
    notification_dir = os.path.expanduser(
        os.path.join(os.path.dirname(task.status_file) or ".", "notifications")
    )
    os.makedirs(notification_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    nf = os.path.join(notification_dir, "{}_{}.json".format(task.task_id, ts))
    try:
        with open(nf, "w") as f:
            json.dump({
                "task_id": task.task_id,
                "old_state": old_state,
                "new_state": new_state,
                "summary": summary,
                "owner": task.owner,
                "reply_to": task.reply_to,
                "timestamp": datetime.now().isoformat(),
            }, f, indent=2, ensure_ascii=False)
    except OSError:
        pass

    return True


def poll_once(store: TaskStore) -> dict:
    """Run one poll cycle over all active tasks. Returns stats."""
    stats = {"checked": 0, "changed": 0, "closed": 0, "expired": 0, "errors": 0}
    active = store.active_tasks()

    for task in active:
        stats["checked"] += 1

        if task.is_expired():
            log.warning("Task %s expired", task.task_id)
            store.close(task.task_id, "timeout")
            notify(task, task.current_state, "timeout", "Task expired")
            stats["expired"] += 1
            stats["closed"] += 1
            continue

        result = check_status_file(task)
        if result is None:
            continue
        if result.error:
            stats["errors"] += 1
            continue

        if result.state != task.current_state:
            old = task.current_state
            store.update(task.task_id, current_state=result.state, last_notified_state=old)
            notify(task, old, result.state, result.summary)
            stats["changed"] += 1

            if result.terminal:
                store.close(task.task_id, result.state)
                stats["closed"] += 1

    return stats


def main():
    parser = argparse.ArgumentParser(description="Minimal task watcher")
    parser.add_argument("--tasks-file", default="./tasks.jsonl",
                        help="Path to tasks JSONL file")
    parser.add_argument("--once", action="store_true",
                        help="Single poll cycle then exit")
    parser.add_argument("--loop", action="store_true",
                        help="Continuous polling")
    parser.add_argument("--interval", type=int, default=30,
                        help="Poll interval in seconds (default: 30)")
    args = parser.parse_args()

    store = TaskStore(args.tasks_file)
    active_count = len(store.active_tasks())
    log.info("Watcher started -- tasks_file=%s, active=%d", args.tasks_file, active_count)

    if args.once or not args.loop:
        stats = poll_once(store)
        log.info("Poll done: %s", stats)
        return

    log.info("Entering poll loop (interval=%ds)", args.interval)
    try:
        while True:
            stats = poll_once(store)
            if stats["changed"] or stats["closed"]:
                log.info("Poll: %s", stats)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        log.info("Watcher stopped")


if __name__ == "__main__":
    main()

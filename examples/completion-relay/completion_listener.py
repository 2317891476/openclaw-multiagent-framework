"""
completion_listener.py — Listens for ACP completion notifications and dispatches alerts.

Checks the completion-relay session for new messages from ACP sub-agents,
updates the task log, and sends notifications via Discord/stdout.

Usage:
    python completion_listener.py --once           # single check
    python completion_listener.py --loop            # continuous (every 60s)
    python completion_listener.py --task-log PATH   # custom task log location

No external dependencies (stdlib only).
"""

import argparse
import json
import os
import sys
import time
import logging
import subprocess
from datetime import datetime
from typing import Dict, List, Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [relay] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("completion-relay")

DEFAULT_TASK_LOG = os.path.expanduser(
    "~/.openclaw/shared-context/monitor-tasks/task-log.jsonl"
)
COMPLETION_SESSION = "agent:main:completion-relay"
PROCESSED_FILE = os.path.expanduser(
    "~/.openclaw/shared-context/monitor-tasks/.relay-cursor"
)


def read_task_log(path: str) -> Dict[str, dict]:
    tasks = {}
    if not os.path.exists(path):
        return tasks
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                tid = entry.get("taskId", "")
                if tid:
                    tasks[tid] = entry
            except (json.JSONDecodeError, KeyError):
                continue
    return tasks


def append_task_log(path: str, entry: dict) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def get_relay_messages() -> List[dict]:
    """
    Fetch recent messages from the completion-relay session.
    Uses openclaw CLI if available, otherwise reads session file directly.
    """
    try:
        result = subprocess.run(
            ["openclaw", "sessions", "list", "--json"],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            sessions = json.loads(result.stdout)
            for s in sessions:
                if s.get("sessionKey") == COMPLETION_SESSION:
                    return s.get("messages", [])
    except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError):
        pass

    relay_path = os.path.expanduser(
        f"~/.openclaw/sessions/{COMPLETION_SESSION.replace(':', '_')}.json"
    )
    if os.path.exists(relay_path):
        try:
            with open(relay_path) as f:
                data = json.load(f)
            return data.get("messages", [])
        except (json.JSONDecodeError, OSError):
            pass

    return []


def get_processed_cursor() -> str:
    if os.path.exists(PROCESSED_FILE):
        with open(PROCESSED_FILE) as f:
            return f.read().strip()
    return ""


def set_processed_cursor(cursor: str) -> None:
    os.makedirs(os.path.dirname(PROCESSED_FILE) or ".", exist_ok=True)
    with open(PROCESSED_FILE, "w") as f:
        f.write(cursor)


def parse_completion(message: dict) -> Optional[dict]:
    content = message.get("content", message.get("text", ""))
    if not content:
        return None

    if isinstance(content, str):
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            idx = content.find("{")
            if idx >= 0:
                try:
                    data = json.loads(content[idx:])
                except json.JSONDecodeError:
                    return None
            else:
                return None
    elif isinstance(content, dict):
        data = content
    else:
        return None

    if data.get("type") != "acp_completion":
        return None

    return {
        "taskId": data.get("taskId", "unknown"),
        "status": data.get("status", "unknown"),
        "summary": data.get("summary", ""),
        "error": data.get("error", ""),
        "receivedAt": datetime.now().isoformat(),
    }


def notify(task_id: str, status: str, summary: str, error: str = "") -> None:
    icon = {"completed": "OK", "failed": "FAIL"}.get(status, "UPDATE")
    parts = [f"[{icon}] Task {task_id}: {status}"]
    if summary:
        parts.append(f"| {summary}")
    if error:
        parts.append(f"| error: {error}")
    log.info(" ".join(parts))


def check_once(task_log_path: str) -> dict:
    stats = {"checked": 0, "completions": 0, "errors": 0}

    messages = get_relay_messages()
    cursor = get_processed_cursor()
    tasks = read_task_log(task_log_path)
    new_cursor = cursor

    for msg in messages:
        msg_id = msg.get("id", msg.get("timestamp", ""))
        if msg_id and msg_id <= cursor:
            continue

        stats["checked"] += 1
        completion = parse_completion(msg)

        if completion is None:
            continue

        task_id = completion["taskId"]
        status = completion["status"]
        summary = completion["summary"]
        error = completion.get("error", "")

        if task_id in tasks:
            updated = {**tasks[task_id]}
            updated["status"] = status
            updated["completionReceived"] = True
            updated["completedAt"] = completion["receivedAt"]
            updated["summary"] = summary
            if error:
                updated["error"] = error
            append_task_log(task_log_path, updated)

        notify(task_id, status, summary, error)
        stats["completions"] += 1

        if msg_id:
            new_cursor = max(new_cursor, msg_id) if new_cursor else msg_id

    if new_cursor != cursor:
        set_processed_cursor(new_cursor)

    return stats


def main():
    parser = argparse.ArgumentParser(description="ACP completion relay listener")
    parser.add_argument("--task-log", default=DEFAULT_TASK_LOG,
                        help="Path to task-log.jsonl")
    parser.add_argument("--once", action="store_true",
                        help="Single check then exit")
    parser.add_argument("--loop", action="store_true",
                        help="Continuous checking")
    parser.add_argument("--interval", type=int, default=60,
                        help="Check interval in seconds (default: 60)")
    args = parser.parse_args()

    log.info("Completion listener started — log=%s", args.task_log)

    if args.once or not args.loop:
        stats = check_once(args.task_log)
        log.info("Check done: %s", stats)
        return

    log.info("Entering loop (interval=%ds)", args.interval)
    try:
        while True:
            stats = check_once(args.task_log)
            if stats["completions"]:
                log.info("Check: %s", stats)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        log.info("Listener stopped")


if __name__ == "__main__":
    main()

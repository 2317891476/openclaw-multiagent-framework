#!/usr/bin/env python3
"""
End-to-end demo: register a task, simulate background work, watch for completion.

Run from the mini-watcher directory:
    cd examples/mini-watcher
    python demo.py

What it does:
    1. Registers a task in tasks.jsonl
    2. Starts a background "worker" thread that simulates async work
    3. Starts the watcher in a loop
    4. Worker writes status updates to a JSON file
    5. Watcher detects changes and prints notifications
    6. Everything stops cleanly when the task reaches terminal state
"""

import json
import os
import sys
import time
import threading
import tempfile
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from models import Task
from store import TaskStore
from watcher import poll_once, log


def simulate_worker(status_file: str, report_file: str):
    """Simulate an async worker that takes ~12 seconds to complete."""
    stages = [
        (2, "started", "Worker initialized"),
        (3, "in_progress", "Analyzing data..."),
        (4, "in_progress", "Generating report..."),
        (3, "completed", "Analysis complete, report written"),
    ]

    for delay, state, summary in stages:
        time.sleep(delay)
        with open(status_file, "w") as f:
            json.dump({
                "state": state,
                "summary": summary,
                "updated_at": datetime.now().isoformat(),
            }, f, indent=2)
        log.info("[worker] Wrote state=%s to %s", state, os.path.basename(status_file))

    with open(report_file, "w") as f:
        f.write("# Task Report\n\n")
        f.write("## Results\n")
        f.write("- Analysis completed successfully\n")
        f.write("- 42 items processed\n")
        f.write("- No anomalies detected\n")
        f.write("\n_Generated at {}_\n".format(datetime.now().isoformat()))
    log.info("[worker] Report written to %s", os.path.basename(report_file))


def main():
    work_dir = tempfile.mkdtemp(prefix="mini-watcher-demo-")
    tasks_file = os.path.join(work_dir, "tasks.jsonl")
    status_file = os.path.join(work_dir, "task-demo-001.json")
    report_file = os.path.join(work_dir, "task-demo-001-report.md")

    print("=" * 60)
    print("  Mini-Watcher End-to-End Demo")
    print("=" * 60)
    print()
    print("Working directory:", work_dir)
    print()

    # Step 1: Register a task
    store = TaskStore(tasks_file)
    task = Task(
        task_id="demo-001",
        owner="main",
        subject="Demo analysis task",
        status_file=status_file,
        report_file=report_file,
        reply_to="user:demo",
        expires_at=(datetime.now() + timedelta(minutes=5)).isoformat(),
    )
    store.register(task)
    print("[1/3] Task registered: demo-001")
    print()

    # Step 2: Start background worker
    worker = threading.Thread(target=simulate_worker, args=(status_file, report_file), daemon=True)
    worker.start()
    print("[2/3] Background worker started (will take ~12s)")
    print()

    # Step 3: Poll until task completes
    print("[3/3] Watcher polling every 2 seconds...")
    print("-" * 60)
    max_polls = 30
    for i in range(max_polls):
        stats = poll_once(store)

        t = store.get("demo-001")
        if t and t.is_terminal():
            print("-" * 60)
            print()
            print("Task reached terminal state: %s" % t.current_state)
            if os.path.exists(report_file):
                print()
                print("Report contents:")
                with open(report_file) as f:
                    print(f.read())
            break

        time.sleep(2)
    else:
        print("Timed out waiting for task completion")

    # Show generated files
    print("Generated files:")
    for f in sorted(os.listdir(work_dir)):
        fpath = os.path.join(work_dir, f)
        if os.path.isdir(fpath):
            for ff in sorted(os.listdir(fpath)):
                print("  %s/%s" % (f, ff))
        else:
            print("  %s" % f)

    print()
    print("Cleanup: rm -rf %s" % work_dir)


if __name__ == "__main__":
    main()

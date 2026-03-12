#!/usr/bin/env python3
"""
Unit tests for watcher.py — poll loop, state detection, notification.

Architecture intent:
    watcher.py is the orchestration layer — it ties models + store together
    with I/O (status files, notifications). Tests verify:
      1. Status file parsing (check_status_file)
      2. Notification generation (notify)
      3. Poll cycle behavior (poll_once)
      4. Expiration handling
      5. Error resilience

    Uses temp directories to isolate from real state.
"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import Task
from store import TaskStore
from watcher import check_status_file, notify, poll_once


class WatcherTestCase(unittest.TestCase):
    """Base with temp directory and helper methods."""

    def setUp(self):
        self.work_dir = tempfile.mkdtemp(prefix="test-watcher-")
        self.tasks_file = os.path.join(self.work_dir, "tasks.jsonl")
        self.store = TaskStore(self.tasks_file)

    def _write_status(self, filename, state, **extra):
        path = os.path.join(self.work_dir, filename)
        data = {"state": state, **extra}
        with open(path, "w") as f:
            json.dump(data, f)
        return path

    def _register_task(self, task_id, status_filename=None, **kwargs):
        sf = os.path.join(self.work_dir, status_filename or f"{task_id}.json")
        task = Task(task_id=task_id, status_file=sf, **kwargs)
        return self.store.register(task)


class TestCheckStatusFile(WatcherTestCase):

    def test_reads_valid_status(self):
        path = self._write_status("t.json", "completed", summary="done")
        task = Task(task_id="t", status_file=path)
        result = check_status_file(task)
        self.assertIsNotNone(result)
        self.assertEqual(result.state, "completed")
        self.assertTrue(result.terminal)
        self.assertEqual(result.summary, "done")

    def test_non_terminal_state(self):
        path = self._write_status("t.json", "in_progress", summary="working")
        task = Task(task_id="t", status_file=path)
        result = check_status_file(task)
        self.assertEqual(result.state, "in_progress")
        self.assertFalse(result.terminal)

    def test_missing_file_returns_none(self):
        task = Task(task_id="t", status_file="/tmp/nonexistent_12345.json")
        result = check_status_file(task)
        self.assertIsNone(result)

    def test_empty_status_file_returns_none(self):
        task = Task(task_id="t", status_file="")
        result = check_status_file(task)
        self.assertIsNone(result)

    def test_malformed_json_returns_error(self):
        path = os.path.join(self.work_dir, "bad.json")
        with open(path, "w") as f:
            f.write("not json")
        task = Task(task_id="t", status_file=path)
        result = check_status_file(task)
        self.assertIsNotNone(result)
        self.assertEqual(result.state, "error")
        self.assertNotEqual(result.error, "")

    def test_missing_state_field(self):
        path = os.path.join(self.work_dir, "no_state.json")
        with open(path, "w") as f:
            json.dump({"summary": "no state"}, f)
        task = Task(task_id="t", status_file=path)
        result = check_status_file(task)
        self.assertEqual(result.state, "unknown")

    def test_all_terminal_states_detected(self):
        for state in ("completed", "failed", "timeout", "cancelled"):
            path = self._write_status(f"{state}.json", state)
            task = Task(task_id="t", status_file=path)
            result = check_status_file(task)
            self.assertTrue(result.terminal, f"{state} should be terminal")


class TestNotify(WatcherTestCase):

    def test_returns_true(self):
        task = Task(task_id="t-001", status_file=os.path.join(self.work_dir, "t.json"),
                    owner="main")
        result = notify(task, "registered", "completed", "done")
        self.assertTrue(result)

    def test_creates_notification_file(self):
        sf = os.path.join(self.work_dir, "status.json")
        with open(sf, "w") as f:
            json.dump({"state": "completed"}, f)
        task = Task(task_id="t-001", status_file=sf, owner="main")
        notify(task, "registered", "completed", "done")

        ndir = os.path.join(self.work_dir, "notifications")
        self.assertTrue(os.path.isdir(ndir))
        files = os.listdir(ndir)
        self.assertEqual(len(files), 1)

        with open(os.path.join(ndir, files[0])) as f:
            data = json.load(f)
        self.assertEqual(data["task_id"], "t-001")
        self.assertEqual(data["new_state"], "completed")
        self.assertEqual(data["summary"], "done")

    def test_notification_contains_reply_to(self):
        sf = os.path.join(self.work_dir, "status.json")
        with open(sf, "w") as f:
            json.dump({"state": "completed"}, f)
        task = Task(task_id="t-001", status_file=sf, reply_to="user:demo")
        notify(task, "registered", "completed")

        ndir = os.path.join(self.work_dir, "notifications")
        files = os.listdir(ndir)
        with open(os.path.join(ndir, files[0])) as f:
            data = json.load(f)
        self.assertEqual(data["reply_to"], "user:demo")


class TestPollOnce(WatcherTestCase):

    def test_detects_state_change(self):
        sf = self._write_status("t-001.json", "in_progress", summary="working")
        self._register_task("t-001", "t-001.json")

        stats = poll_once(self.store)
        self.assertEqual(stats["checked"], 1)
        self.assertEqual(stats["changed"], 1)

        task = self.store.get("t-001")
        self.assertEqual(task.current_state, "in_progress")

    def test_detects_terminal_state(self):
        sf = self._write_status("t-001.json", "completed", summary="done")
        self._register_task("t-001", "t-001.json")

        stats = poll_once(self.store)
        self.assertEqual(stats["closed"], 1)

        task = self.store.get("t-001")
        self.assertTrue(task.terminal)

    def test_no_change_no_notification(self):
        """If status file state matches current_state, no change detected."""
        sf = self._write_status("t-001.json", "registered")
        self._register_task("t-001", "t-001.json")

        stats = poll_once(self.store)
        self.assertEqual(stats["changed"], 0)

    def test_missing_status_file_no_error(self):
        self._register_task("t-001", "missing.json")
        stats = poll_once(self.store)
        self.assertEqual(stats["checked"], 1)
        self.assertEqual(stats["errors"], 0)
        self.assertEqual(stats["changed"], 0)

    def test_expired_task_closed_as_timeout(self):
        from datetime import datetime, timedelta
        past = (datetime.now() - timedelta(hours=1)).isoformat()
        sf = self._write_status("t-001.json", "in_progress")
        self._register_task("t-001", "t-001.json", expires_at=past)

        stats = poll_once(self.store)
        self.assertEqual(stats["expired"], 1)
        self.assertEqual(stats["closed"], 1)

        task = self.store.get("t-001")
        self.assertTrue(task.terminal)

    def test_multiple_tasks_independent(self):
        self._write_status("t-001.json", "completed")
        self._write_status("t-002.json", "in_progress")
        self._write_status("t-003.json", "registered")
        self._register_task("t-001", "t-001.json")
        self._register_task("t-002", "t-002.json")
        self._register_task("t-003", "t-003.json")

        stats = poll_once(self.store)
        self.assertEqual(stats["checked"], 3)
        self.assertEqual(stats["changed"], 2)  # t-001 and t-002 changed
        self.assertEqual(stats["closed"], 1)   # t-001 terminal

    def test_already_terminal_not_polled(self):
        self._write_status("t-001.json", "completed")
        self._register_task("t-001", "t-001.json")
        self.store.close("t-001", "completed")

        stats = poll_once(self.store)
        self.assertEqual(stats["checked"], 0)

    def test_malformed_status_file_counted_as_error(self):
        path = os.path.join(self.work_dir, "bad.json")
        with open(path, "w") as f:
            f.write("{broken")
        task = Task(task_id="t-001", status_file=path)
        self.store.register(task)

        stats = poll_once(self.store)
        self.assertEqual(stats["errors"], 1)

    def test_poll_empty_store(self):
        stats = poll_once(self.store)
        self.assertEqual(stats["checked"], 0)
        self.assertEqual(stats["changed"], 0)


class TestPollOnceSequence(WatcherTestCase):
    """Test multi-poll sequences simulating real watcher lifecycle."""

    def test_full_lifecycle(self):
        """registered → started → in_progress → completed"""
        sf = os.path.join(self.work_dir, "lifecycle.json")
        self._register_task("t-001", "lifecycle.json")

        states_sequence = [
            ("started", 1, 0),
            ("in_progress", 1, 0),
            ("completed", 1, 1),
        ]

        for state, expected_changed, expected_closed in states_sequence:
            self._write_status("lifecycle.json", state)
            stats = poll_once(self.store)
            self.assertEqual(stats["changed"], expected_changed,
                             f"Expected {expected_changed} change(s) for {state}")
            self.assertEqual(stats["closed"], expected_closed,
                             f"Expected {expected_closed} close(s) for {state}")

    def test_no_double_notification_for_same_state(self):
        """Polling twice with same state shouldn't trigger twice."""
        self._write_status("t.json", "in_progress")
        self._register_task("t-001", "t.json")

        stats1 = poll_once(self.store)
        self.assertEqual(stats1["changed"], 1)

        stats2 = poll_once(self.store)
        # After first poll updated last_notified_state, no change detected
        # Note: depends on watcher updating last_notified_state = old (not new)
        # The current implementation sets last_notified_state=old, so
        # current_state(in_progress) != last_notified_state(registered→old)
        # Actually, re-read code: store.update sets last_notified_state=old
        # So after update: current_state=in_progress, last_notified_state=registered
        # Second poll: status file still says in_progress, current_state=in_progress
        # No state change from current_state perspective → no notification
        self.assertEqual(stats2["changed"], 0)


if __name__ == "__main__":
    unittest.main()

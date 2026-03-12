#!/usr/bin/env python3
"""
Unit tests for store.py — JSONL-based TaskStore.

Architecture intent:
    store.py is the persistence layer — file I/O with locking guarantees.
    Tests verify CRUD operations, append-only semantics, idempotency,
    concurrency safety, and compact behavior.

    Each test gets a fresh temp directory to avoid cross-test interference.
"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import Task
from store import TaskStore


class StoreTestCase(unittest.TestCase):
    """Base class that provides a fresh TaskStore per test."""

    def setUp(self):
        self.work_dir = tempfile.mkdtemp(prefix="test-store-")
        self.tasks_file = os.path.join(self.work_dir, "tasks.jsonl")
        self.store = TaskStore(self.tasks_file)

    def _make_task(self, task_id="t-001", **kwargs):
        return Task(task_id=task_id, **kwargs)


class TestStoreInit(StoreTestCase):

    def test_creates_file_on_init(self):
        self.assertTrue(os.path.exists(self.tasks_file))

    def test_creates_parent_directory(self):
        nested = os.path.join(self.work_dir, "sub", "dir", "tasks.jsonl")
        TaskStore(nested)
        self.assertTrue(os.path.exists(nested))

    def test_empty_file_on_init(self):
        self.assertEqual(os.path.getsize(self.tasks_file), 0)

    def test_expands_user_path(self):
        """TaskStore should expand ~ in paths."""
        store = TaskStore("~/test-store-expand.jsonl")
        expected = os.path.expanduser("~/test-store-expand.jsonl")
        self.assertEqual(store.path, expected)
        if os.path.exists(expected):
            os.unlink(expected)


class TestStoreRegister(StoreTestCase):

    def test_register_writes_to_file(self):
        task = self._make_task()
        self.store.register(task)
        with open(self.tasks_file) as f:
            lines = [l.strip() for l in f if l.strip()]
        self.assertEqual(len(lines), 1)
        data = json.loads(lines[0])
        self.assertEqual(data["task_id"], "t-001")

    def test_register_sets_timestamps(self):
        task = self._make_task()
        registered = self.store.register(task)
        self.assertIsNotNone(registered.created_at)
        self.assertEqual(registered.created_at, registered.updated_at)

    def test_register_duplicate_raises(self):
        self.store.register(self._make_task("t-001"))
        with self.assertRaises(ValueError) as ctx:
            self.store.register(self._make_task("t-001"))
        self.assertIn("already exists", str(ctx.exception))

    def test_register_multiple_tasks(self):
        for i in range(5):
            self.store.register(self._make_task(f"t-{i:03d}"))
        with open(self.tasks_file) as f:
            lines = [l.strip() for l in f if l.strip()]
        self.assertEqual(len(lines), 5)

    def test_register_returns_task(self):
        task = self._make_task(owner="main")
        result = self.store.register(task)
        self.assertIsInstance(result, Task)
        self.assertEqual(result.owner, "main")


class TestStoreGet(StoreTestCase):

    def test_get_existing(self):
        self.store.register(self._make_task("t-001", owner="main"))
        result = self.store.get("t-001")
        self.assertIsNotNone(result)
        self.assertEqual(result.owner, "main")

    def test_get_nonexistent_returns_none(self):
        result = self.store.get("nonexistent")
        self.assertIsNone(result)

    def test_get_returns_latest_version(self):
        """After update, get() returns the updated version."""
        self.store.register(self._make_task("t-001", owner="v1"))
        self.store.update("t-001", owner="v2")
        result = self.store.get("t-001")
        self.assertEqual(result.owner, "v2")


class TestStoreUpdate(StoreTestCase):

    def test_update_existing(self):
        self.store.register(self._make_task("t-001"))
        updated = self.store.update("t-001", current_state="in_progress")
        self.assertIsNotNone(updated)
        self.assertEqual(updated.current_state, "in_progress")

    def test_update_nonexistent_returns_none(self):
        result = self.store.update("nonexistent", current_state="done")
        self.assertIsNone(result)

    def test_update_preserves_other_fields(self):
        self.store.register(self._make_task("t-001", owner="main", subject="test"))
        updated = self.store.update("t-001", current_state="completed")
        self.assertEqual(updated.owner, "main")
        self.assertEqual(updated.subject, "test")

    def test_update_rejects_task_id_in_kwargs(self):
        """task_id is a positional arg, so passing it in kwargs raises TypeError."""
        self.store.register(self._make_task("t-001"))
        with self.assertRaises(TypeError):
            self.store.update("t-001", task_id="t-999")

    def test_update_sets_updated_at(self):
        self.store.register(self._make_task("t-001"))
        task_before = self.store.get("t-001")
        import time
        time.sleep(0.01)
        updated = self.store.update("t-001", current_state="in_progress")
        self.assertGreater(updated.updated_at, task_before.updated_at)

    def test_update_is_append_only(self):
        """Updates append new lines; old versions remain in file."""
        self.store.register(self._make_task("t-001"))
        self.store.update("t-001", current_state="started")
        self.store.update("t-001", current_state="completed")
        with open(self.tasks_file) as f:
            lines = [l.strip() for l in f if l.strip()]
        self.assertEqual(len(lines), 3)


class TestStoreClose(StoreTestCase):

    def test_close_marks_terminal(self):
        self.store.register(self._make_task("t-001"))
        closed = self.store.close("t-001", "completed")
        self.assertIsNotNone(closed)
        self.assertTrue(closed.terminal)
        self.assertEqual(closed.current_state, "completed")

    def test_close_nonexistent_returns_none(self):
        result = self.store.close("nonexistent", "failed")
        self.assertIsNone(result)

    def test_closed_task_not_in_active(self):
        self.store.register(self._make_task("t-001"))
        self.store.close("t-001", "completed")
        active = self.store.active_tasks()
        self.assertEqual(len(active), 0)


class TestStoreActiveTasks(StoreTestCase):

    def test_returns_only_non_terminal(self):
        self.store.register(self._make_task("active-1"))
        self.store.register(self._make_task("active-2"))
        self.store.register(self._make_task("done-1"))
        self.store.close("done-1", "completed")

        active = self.store.active_tasks()
        ids = {t.task_id for t in active}
        self.assertEqual(ids, {"active-1", "active-2"})

    def test_empty_store_returns_empty(self):
        self.assertEqual(len(self.store.active_tasks()), 0)


class TestStoreCompact(StoreTestCase):

    def test_compact_reduces_file_size(self):
        self.store.register(self._make_task("t-001"))
        for i in range(10):
            self.store.update("t-001", current_state=f"state_{i}")
        size_before = os.path.getsize(self.tasks_file)
        saved = self.store.compact()
        size_after = os.path.getsize(self.tasks_file)

        self.assertGreater(saved, 0)
        self.assertLess(size_after, size_before)

    def test_compact_preserves_latest_state(self):
        self.store.register(self._make_task("t-001"))
        self.store.update("t-001", current_state="final_state")
        self.store.compact()

        result = self.store.get("t-001")
        self.assertEqual(result.current_state, "final_state")

    def test_compact_preserves_all_tasks(self):
        for i in range(5):
            self.store.register(self._make_task(f"t-{i:03d}"))
        self.store.compact()
        for i in range(5):
            self.assertIsNotNone(self.store.get(f"t-{i:03d}"))

    def test_compact_single_entry_returns_zero(self):
        self.store.register(self._make_task("t-001"))
        saved = self.store.compact()
        self.assertEqual(saved, 0)

    def test_compact_file_has_one_line_per_task(self):
        for i in range(3):
            self.store.register(self._make_task(f"t-{i:03d}"))
            self.store.update(f"t-{i:03d}", current_state="updated")
        self.store.compact()
        with open(self.tasks_file) as f:
            lines = [l.strip() for l in f if l.strip()]
        self.assertEqual(len(lines), 3)


class TestStoreRobustness(StoreTestCase):
    """Test behavior with malformed data and edge cases."""

    def test_handles_blank_lines(self):
        with open(self.tasks_file, "w") as f:
            f.write("\n\n")
            f.write(Task(task_id="t-001").to_json() + "\n")
            f.write("\n")
        result = self.store.get("t-001")
        self.assertIsNotNone(result)

    def test_handles_malformed_json_lines(self):
        with open(self.tasks_file, "w") as f:
            f.write("this is not json\n")
            f.write(Task(task_id="t-001").to_json() + "\n")
            f.write("{broken json\n")
        result = self.store.get("t-001")
        self.assertIsNotNone(result)
        self.assertEqual(len(self.store.active_tasks()), 1)

    def test_handles_missing_file(self):
        os.unlink(self.tasks_file)
        result = self.store.get("anything")
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()

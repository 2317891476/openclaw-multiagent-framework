#!/usr/bin/env python3
"""
Unit tests for models.py — Task and StateResult dataclasses.

Architecture intent:
    models.py is the foundation layer — pure data with no I/O dependencies.
    Tests verify serialization roundtrips, state predicates, and edge cases.
    No file system or external state involved.
"""

import json
import unittest
from datetime import datetime, timedelta

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import Task, StateResult, TERMINAL_STATES


class TestTaskConstruction(unittest.TestCase):
    """Verify default values and post-init behavior."""

    def test_minimal_construction(self):
        t = Task(task_id="t-001")
        self.assertEqual(t.task_id, "t-001")
        self.assertEqual(t.current_state, "registered")
        self.assertEqual(t.owner, "")
        self.assertFalse(t.terminal)
        self.assertFalse(t.delivery_ok)
        self.assertIsInstance(t.metadata, dict)

    def test_post_init_syncs_last_notified_state(self):
        """last_notified_state defaults to current_state if not set."""
        t = Task(task_id="t-001", current_state="in_progress")
        self.assertEqual(t.last_notified_state, "in_progress")

    def test_post_init_preserves_explicit_last_notified_state(self):
        t = Task(task_id="t-001", current_state="completed",
                 last_notified_state="in_progress")
        self.assertEqual(t.last_notified_state, "in_progress")

    def test_timestamps_auto_generated(self):
        before = datetime.now().isoformat()
        t = Task(task_id="t-001")
        after = datetime.now().isoformat()
        self.assertGreaterEqual(t.created_at, before)
        self.assertLessEqual(t.created_at, after)

    def test_metadata_isolation(self):
        """Each Task instance gets its own metadata dict."""
        t1 = Task(task_id="t-001")
        t2 = Task(task_id="t-002")
        t1.metadata["key"] = "value"
        self.assertNotIn("key", t2.metadata)


class TestTaskPredicates(unittest.TestCase):
    """Verify state predicates: is_terminal, is_expired, state_changed."""

    def test_is_terminal_by_flag(self):
        t = Task(task_id="t-001", terminal=True)
        self.assertTrue(t.is_terminal())

    def test_is_terminal_by_state(self):
        for state in TERMINAL_STATES:
            t = Task(task_id="t-001", current_state=state)
            self.assertTrue(t.is_terminal(), f"State '{state}' should be terminal")

    def test_not_terminal_for_active_states(self):
        for state in ("registered", "started", "in_progress", "running"):
            t = Task(task_id="t-001", current_state=state)
            self.assertFalse(t.is_terminal(), f"State '{state}' should not be terminal")

    def test_is_expired_no_expiry(self):
        t = Task(task_id="t-001")
        self.assertFalse(t.is_expired())

    def test_is_expired_future(self):
        future = (datetime.now() + timedelta(hours=1)).isoformat()
        t = Task(task_id="t-001", expires_at=future)
        self.assertFalse(t.is_expired())

    def test_is_expired_past(self):
        past = (datetime.now() - timedelta(hours=1)).isoformat()
        t = Task(task_id="t-001", expires_at=past)
        self.assertTrue(t.is_expired())

    def test_is_expired_invalid_format(self):
        t = Task(task_id="t-001", expires_at="not-a-date")
        self.assertFalse(t.is_expired())

    def test_state_changed_true(self):
        t = Task(task_id="t-001", current_state="completed",
                 last_notified_state="in_progress")
        self.assertTrue(t.state_changed())

    def test_state_changed_false(self):
        t = Task(task_id="t-001", current_state="in_progress",
                 last_notified_state="in_progress")
        self.assertFalse(t.state_changed())


class TestTaskSerialization(unittest.TestCase):
    """Verify JSON roundtrip and from_dict edge cases."""

    def test_roundtrip_json(self):
        original = Task(
            task_id="t-001",
            owner="main",
            subject="test task",
            current_state="in_progress",
            metadata={"key": "value"},
        )
        json_str = original.to_json()
        restored = Task.from_json(json_str)

        self.assertEqual(restored.task_id, "t-001")
        self.assertEqual(restored.owner, "main")
        self.assertEqual(restored.current_state, "in_progress")
        self.assertEqual(restored.metadata, {"key": "value"})

    def test_roundtrip_dict(self):
        original = Task(task_id="t-001", subject="test")
        d = original.to_dict()
        restored = Task.from_dict(d)
        self.assertEqual(original.task_id, restored.task_id)
        self.assertEqual(original.subject, restored.subject)

    def test_from_dict_ignores_unknown_keys(self):
        data = {"task_id": "t-001", "unknown_field": "should_be_ignored"}
        t = Task.from_dict(data)
        self.assertEqual(t.task_id, "t-001")

    def test_from_json_valid(self):
        line = '{"task_id": "t-001", "owner": "test"}'
        t = Task.from_json(line)
        self.assertEqual(t.task_id, "t-001")
        self.assertEqual(t.owner, "test")

    def test_from_json_invalid_raises(self):
        with self.assertRaises(json.JSONDecodeError):
            Task.from_json("not valid json")

    def test_to_json_is_valid_json(self):
        t = Task(task_id="t-001", subject="中文测试")
        parsed = json.loads(t.to_json())
        self.assertEqual(parsed["subject"], "中文测试")

    def test_to_json_ensure_ascii_false(self):
        t = Task(task_id="t-001", subject="中文")
        self.assertIn("中文", t.to_json())
        self.assertNotIn("\\u", t.to_json())


class TestStateResult(unittest.TestCase):

    def test_defaults(self):
        r = StateResult(state="completed")
        self.assertEqual(r.state, "completed")
        self.assertFalse(r.terminal)
        self.assertEqual(r.summary, "")
        self.assertEqual(r.error, "")

    def test_with_error(self):
        r = StateResult(state="error", error="file not found")
        self.assertEqual(r.error, "file not found")

    def test_terminal_flag(self):
        r = StateResult(state="completed", terminal=True, summary="done")
        self.assertTrue(r.terminal)
        self.assertEqual(r.summary, "done")


class TestTerminalStates(unittest.TestCase):
    """Verify TERMINAL_STATES is a consistent frozenset."""

    def test_contains_expected_states(self):
        expected = {"completed", "failed", "timeout", "cancelled"}
        self.assertEqual(TERMINAL_STATES, expected)

    def test_is_frozenset(self):
        self.assertIsInstance(TERMINAL_STATES, frozenset)

    def test_immutable(self):
        with self.assertRaises(AttributeError):
            TERMINAL_STATES.add("new_state")


if __name__ == "__main__":
    unittest.main()

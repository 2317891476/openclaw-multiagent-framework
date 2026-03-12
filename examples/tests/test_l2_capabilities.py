#!/usr/bin/env python3
"""
Unit tests for l2_capabilities.py — L2 enhancement layer.

Architecture intent:
    l2_capabilities.py implements L2 capabilities that sit above OpenClaw's
    default L1 primitives. Tests verify:
      - ACK gate correctness (timeout, duplicate, state transitions)
      - Handoff template formatting (three-phase protocol)
      - Deliverable structure (conclusion/evidence/action layers)
      - Single writer locking (mutual exclusion)
      - Follow-up bridge (task → action item pipeline)
      - Reflection pipeline (reflection → follow-up conversion)

    Each class is tested independently — they have no cross-dependencies.
"""

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from l2_capabilities import (
    AckGate, AckState, AckMessage,
    HandoffRequest,
    Deliverable,
    SingleWriter,
    FollowUpBridge, FollowUpItem,
    ReflectionEntry, ReflectionPipeline,
)


# ---------------------------------------------------------------------------
# ACK Protocol (2.1.1)
# ---------------------------------------------------------------------------

class TestAckMessage(unittest.TestCase):

    def test_construction(self):
        msg = AckMessage(ack_id="a-001", from_agent="main", to_agent="research")
        self.assertEqual(msg.state, AckState.PENDING.value)
        self.assertIsInstance(msg.timestamp, str)
        self.assertIsInstance(msg.payload, dict)

    def test_to_json_roundtrip(self):
        msg = AckMessage(ack_id="a-001", from_agent="main", to_agent="research",
                         payload={"key": "value"})
        data = json.loads(msg.to_json())
        self.assertEqual(data["ack_id"], "a-001")
        self.assertEqual(data["payload"]["key"], "value")


class TestAckGate(unittest.TestCase):

    def setUp(self):
        self.gate = AckGate(timeout_seconds=3)

    def test_send_request_creates_pending(self):
        self.gate.send_request("a-001", "main", "research")
        self.assertEqual(self.gate.status("a-001"), "pending")

    def test_receive_ack_confirmed(self):
        self.gate.send_request("a-001", "main", "research")
        ack = self.gate.receive_ack("a-001", "research", confirmed=True)
        self.assertIsNotNone(ack)
        self.assertEqual(self.gate.status("a-001"), "confirmed")

    def test_receive_ack_rejected(self):
        self.gate.send_request("a-001", "main", "research")
        ack = self.gate.receive_ack("a-001", "research", confirmed=False,
                                     reason="Busy")
        self.assertEqual(self.gate.status("a-001"), "rejected")
        self.assertEqual(ack.reason, "Busy")

    def test_receive_ack_unknown_id(self):
        result = self.gate.receive_ack("nonexistent", "research")
        self.assertIsNone(result)

    def test_timeout_detection(self):
        self.gate.send_request("a-001", "main", "research")
        self.gate._pending["a-001"].timestamp = (
            datetime.now() - timedelta(seconds=10)
        ).isoformat()
        timed_out = self.gate.check_timeouts()
        self.assertEqual(timed_out, ["a-001"])
        self.assertEqual(self.gate.status("a-001"), "timeout")

    def test_no_timeout_within_deadline(self):
        self.gate.send_request("a-001", "main", "research")
        timed_out = self.gate.check_timeouts()
        self.assertEqual(timed_out, [])
        self.assertEqual(self.gate.status("a-001"), "pending")

    def test_status_unknown_for_unseen_id(self):
        self.assertEqual(self.gate.status("never-sent"), "unknown")

    def test_multiple_requests_independent(self):
        self.gate.send_request("a-001", "main", "research")
        self.gate.send_request("a-002", "main", "writing")
        self.gate.receive_ack("a-001", "research")
        self.assertEqual(self.gate.status("a-001"), "confirmed")
        self.assertEqual(self.gate.status("a-002"), "pending")

    def test_history_tracks_all_messages(self):
        self.gate.send_request("a-001", "main", "research")
        self.gate.receive_ack("a-001", "research")
        self.assertEqual(len(self.gate._history), 2)


# ---------------------------------------------------------------------------
# Handoff Template (2.1.2)
# ---------------------------------------------------------------------------

class TestHandoffRequest(unittest.TestCase):

    def setUp(self):
        self.handoff = HandoffRequest(
            ack_id="20260312-001",
            from_agent="main",
            to_agent="research",
            topic="AI Analysis",
            ask="Generate report",
            due="18:00",
            priority="high",
            required_capabilities=["web_search"],
        )

    def test_format_request(self):
        result = self.handoff.format_request()
        self.assertIn("[Request]", result)
        self.assertIn("ack_id=20260312-001", result)
        self.assertIn("topic=AI Analysis", result)
        self.assertIn("priority=high", result)
        self.assertIn("caps=web_search", result)

    def test_format_ack(self):
        result = self.handoff.format_ack("confirmed", eta="2 hours")
        self.assertIn("[ACK]", result)
        self.assertIn("state=confirmed", result)
        self.assertIn("eta=2 hours", result)

    def test_format_ack_without_eta(self):
        result = self.handoff.format_ack("confirmed")
        self.assertIn("[ACK]", result)
        self.assertNotIn("eta=", result)

    def test_format_final(self):
        result = self.handoff.format_final("Report done", "report.md",
                                            ["Review", "Publish"])
        self.assertIn("[Final]", result)
        self.assertIn("state=final", result)
        self.assertIn("summary=Report done", result)
        self.assertIn("report=report.md", result)
        self.assertIn("Review; Publish", result)

    def test_format_final_minimal(self):
        result = self.handoff.format_final("Done")
        self.assertIn("[Final]", result)
        self.assertNotIn("report=", result)
        self.assertNotIn("next=", result)

    def test_no_capabilities_omits_caps(self):
        h = HandoffRequest(ack_id="x", from_agent="a", to_agent="b",
                           topic="t", ask="a", due="d")
        result = h.format_request()
        self.assertNotIn("caps=", result)


# ---------------------------------------------------------------------------
# Deliverable Layers (2.1.3)
# ---------------------------------------------------------------------------

class TestDeliverable(unittest.TestCase):

    def test_to_markdown_full(self):
        d = Deliverable(
            conclusion="Result A is better.",
            evidence=["Evidence 1", "Evidence 2"],
            actions=["Action 1", "Action 2"],
            confidence=0.8,
        )
        md = d.to_markdown()
        self.assertIn("## Conclusion", md)
        self.assertIn("Result A is better.", md)
        self.assertIn("80%", md)
        self.assertIn("## Evidence", md)
        self.assertIn("- Evidence 1", md)
        self.assertIn("## Actions", md)
        self.assertIn("- [ ] Action 1", md)

    def test_full_confidence_no_percentage(self):
        d = Deliverable(conclusion="X", evidence=[], actions=[], confidence=1.0)
        md = d.to_markdown()
        self.assertNotIn("Confidence", md)

    def test_actions_as_checkboxes(self):
        d = Deliverable(conclusion="X", evidence=[], actions=["Do A", "Do B"])
        md = d.to_markdown()
        self.assertEqual(md.count("- [ ]"), 2)


# ---------------------------------------------------------------------------
# Single Writer (2.1.4)
# ---------------------------------------------------------------------------

class TestSingleWriter(unittest.TestCase):

    def test_lock_creates_and_removes_lockfile(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name

        writer = SingleWriter("main")
        lock_path = path + ".lock"

        with writer.lock(path):
            self.assertTrue(os.path.exists(lock_path))
            with open(lock_path) as f:
                data = json.load(f)
            self.assertEqual(data["owner"], "main")

        self.assertFalse(os.path.exists(lock_path))
        os.unlink(path)

    def test_lock_is_context_manager(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name

        writer = SingleWriter("test")
        with writer.lock(path) as ctx:
            self.assertIsNotNone(ctx)

        os.unlink(path)

    def test_different_owners(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name

        w1 = SingleWriter("agent-A")
        w2 = SingleWriter("agent-B")

        with w1.lock(path):
            with open(path + ".lock") as f:
                data = json.load(f)
            self.assertEqual(data["owner"], "agent-A")

        with w2.lock(path):
            with open(path + ".lock") as f:
                data = json.load(f)
            self.assertEqual(data["owner"], "agent-B")

        os.unlink(path)


# ---------------------------------------------------------------------------
# Follow-up Bridge (2.2.2)
# ---------------------------------------------------------------------------

class TestFollowUpItem(unittest.TestCase):

    def test_to_row(self):
        item = FollowUpItem(
            topic="Review report",
            priority="P0",
            owner="main",
            evidence_path="reports/x.md",
        )
        row = item.to_row()
        self.assertIn("Review report", row)
        self.assertIn("P0", row)
        self.assertIn("main", row)
        self.assertIn("pending", row)
        self.assertIn("reports/x.md", row)


class TestFollowUpBridge(unittest.TestCase):

    def setUp(self):
        self.work_dir = tempfile.mkdtemp(prefix="test-followup-")
        self.bridge = FollowUpBridge(os.path.join(self.work_dir, "followups"))

    def test_creates_followup_file(self):
        path = self.bridge.generate_from_task(
            task_id="t-001",
            summary="Test",
            owner="main",
            follow_ups=[{"topic": "Review", "priority": "P0", "owner": "main"}],
        )
        self.assertTrue(os.path.exists(path))

    def test_file_contains_markdown_table(self):
        path = self.bridge.generate_from_task(
            task_id="t-001",
            summary="Test",
            owner="main",
            follow_ups=[{"topic": "Check results", "priority": "P1", "owner": "team"}],
        )
        with open(path) as f:
            content = f.read()
        self.assertIn("| Topic |", content)
        self.assertIn("Check results", content)
        self.assertIn("P1", content)

    def test_appends_to_existing_file(self):
        self.bridge.generate_from_task(
            task_id="t-001", summary="First", owner="main",
            follow_ups=[{"topic": "First item", "priority": "P0"}],
        )
        self.bridge.generate_from_task(
            task_id="t-002", summary="Second", owner="main",
            follow_ups=[{"topic": "Second item", "priority": "P1"}],
        )
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        path = os.path.join(self.bridge.followups_dir, f"{tomorrow}.md")
        with open(path) as f:
            content = f.read()
        self.assertIn("First item", content)
        self.assertIn("Second item", content)

    def test_pending_items(self):
        self.bridge.generate_from_task(
            task_id="t-001", summary="Test", owner="main",
            follow_ups=[
                {"topic": "A", "priority": "P0"},
                {"topic": "B", "priority": "P1"},
            ],
        )
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        pending = self.bridge.pending_items(tomorrow)
        self.assertEqual(len(pending), 2)

    def test_pending_items_no_file(self):
        result = self.bridge.pending_items("2099-01-01")
        self.assertEqual(result, [])


# ---------------------------------------------------------------------------
# Reflection Pipeline (2.4.1)
# ---------------------------------------------------------------------------

class TestReflectionEntry(unittest.TestCase):

    def test_to_markdown(self):
        entry = ReflectionEntry(
            date="2026-03-12",
            author="main",
            what_worked=["ACK protocol prevented duplicates"],
            what_didnt=["Timeout handled as failure"],
            action_items=[{"topic": "Fix timeout handling", "priority": "P0", "owner": "main"}],
        )
        md = entry.to_markdown()
        self.assertIn("# Daily Reflection", md)
        self.assertIn("ACK protocol prevented duplicates", md)
        self.assertIn("Timeout handled as failure", md)
        self.assertIn("[P0] Fix timeout handling", md)

    def test_to_markdown_without_author(self):
        entry = ReflectionEntry(
            date="2026-03-12",
            what_worked=[], what_didnt=[], action_items=[],
        )
        md = entry.to_markdown()
        self.assertNotIn("Author", md)


class TestReflectionPipeline(unittest.TestCase):

    def setUp(self):
        self.work_dir = tempfile.mkdtemp(prefix="test-reflection-")
        self.pipeline = ReflectionPipeline(
            os.path.join(self.work_dir, "reflections"),
            os.path.join(self.work_dir, "followups"),
        )

    def test_save_reflection(self):
        entry = ReflectionEntry(
            date="2026-03-12", author="main",
            what_worked=["X"], what_didnt=["Y"],
            action_items=[],
        )
        path = self.pipeline.save_reflection(entry)
        self.assertTrue(os.path.exists(path))
        with open(path) as f:
            self.assertIn("Daily Reflection", f.read())

    def test_process_generates_followups(self):
        entry = ReflectionEntry(
            date="2026-03-12", author="main",
            what_worked=[], what_didnt=[],
            action_items=[
                {"topic": "Fix X", "priority": "P0", "owner": "main"},
            ],
        )
        followup_path = self.pipeline.process_reflection(entry)
        self.assertTrue(os.path.exists(followup_path))
        with open(followup_path) as f:
            self.assertIn("Fix X", f.read())

    def test_process_no_actions_no_followup(self):
        entry = ReflectionEntry(
            date="2026-03-12", author="main",
            what_worked=["A"], what_didnt=["B"],
            action_items=[],
        )
        followup_path = self.pipeline.process_reflection(entry)
        self.assertEqual(followup_path, "")

    def test_creates_reflection_directory(self):
        self.assertTrue(os.path.isdir(
            os.path.join(self.work_dir, "reflections")))


if __name__ == "__main__":
    unittest.main()

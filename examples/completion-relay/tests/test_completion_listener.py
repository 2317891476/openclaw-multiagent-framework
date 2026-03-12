"""Unit tests for completion_listener.py"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'completion-relay'))

from completion_listener import (
    read_task_log,
    append_task_log,
    parse_completion,
)


class TestReadTaskLog(unittest.TestCase):
    def test_empty_file(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
            f.write("")
            path = f.name
        try:
            result = read_task_log(path)
            self.assertEqual(result, {})
        finally:
            os.unlink(path)

    def test_valid_entries(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
            f.write(json.dumps({"taskId": "t1", "status": "spawning"}) + "\n")
            f.write(json.dumps({"taskId": "t2", "status": "completed"}) + "\n")
            path = f.name
        try:
            result = read_task_log(path)
            self.assertEqual(len(result), 2)
            self.assertEqual(result["t1"]["status"], "spawning")
            self.assertEqual(result["t2"]["status"], "completed")
        finally:
            os.unlink(path)

    def test_latest_entry_wins(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
            f.write(json.dumps({"taskId": "t1", "status": "spawning"}) + "\n")
            f.write(json.dumps({"taskId": "t1", "status": "completed"}) + "\n")
            path = f.name
        try:
            result = read_task_log(path)
            self.assertEqual(len(result), 1)
            self.assertEqual(result["t1"]["status"], "completed")
        finally:
            os.unlink(path)

    def test_malformed_lines_skipped(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
            f.write("not json\n")
            f.write(json.dumps({"taskId": "t1", "status": "ok"}) + "\n")
            f.write("{broken\n")
            path = f.name
        try:
            result = read_task_log(path)
            self.assertEqual(len(result), 1)
        finally:
            os.unlink(path)

    def test_nonexistent_file(self):
        result = read_task_log("/tmp/nonexistent_task_log_12345.jsonl")
        self.assertEqual(result, {})


class TestAppendTaskLog(unittest.TestCase):
    def test_append_creates_file(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "sub", "task-log.jsonl")
            append_task_log(path, {"taskId": "t1", "status": "spawning"})
            self.assertTrue(os.path.exists(path))
            with open(path) as f:
                data = json.loads(f.read().strip())
            self.assertEqual(data["taskId"], "t1")

    def test_append_preserves_existing(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
            f.write(json.dumps({"taskId": "t1"}) + "\n")
            path = f.name
        try:
            append_task_log(path, {"taskId": "t2"})
            with open(path) as f:
                lines = [l for l in f.readlines() if l.strip()]
            self.assertEqual(len(lines), 2)
        finally:
            os.unlink(path)


class TestParseCompletion(unittest.TestCase):
    def test_valid_completion(self):
        msg = {"content": json.dumps({
            "type": "acp_completion",
            "taskId": "tsk_001",
            "status": "completed",
            "summary": "Done"
        })}
        result = parse_completion(msg)
        self.assertIsNotNone(result)
        self.assertEqual(result["taskId"], "tsk_001")
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["summary"], "Done")

    def test_failed_completion(self):
        msg = {"content": json.dumps({
            "type": "acp_completion",
            "taskId": "tsk_002",
            "status": "failed",
            "summary": "",
            "error": "timeout"
        })}
        result = parse_completion(msg)
        self.assertIsNotNone(result)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error"], "timeout")

    def test_non_completion_message(self):
        msg = {"content": json.dumps({"type": "chat", "text": "hello"})}
        result = parse_completion(msg)
        self.assertIsNone(result)

    def test_empty_message(self):
        result = parse_completion({})
        self.assertIsNone(result)
        result = parse_completion({"content": ""})
        self.assertIsNone(result)

    def test_json_embedded_in_text(self):
        msg = {"content": 'Here is the result: {"type": "acp_completion", "taskId": "t3", "status": "completed", "summary": "ok"}'}
        result = parse_completion(msg)
        self.assertIsNotNone(result)
        self.assertEqual(result["taskId"], "t3")

    def test_invalid_json(self):
        msg = {"content": "this is not json at all"}
        result = parse_completion(msg)
        self.assertIsNone(result)

    def test_dict_content(self):
        msg = {"content": {
            "type": "acp_completion",
            "taskId": "t4",
            "status": "completed",
            "summary": "direct dict"
        }}
        result = parse_completion(msg)
        self.assertIsNotNone(result)
        self.assertEqual(result["taskId"], "t4")

    def test_text_field_fallback(self):
        msg = {"text": json.dumps({
            "type": "acp_completion",
            "taskId": "t5",
            "status": "completed",
            "summary": "from text field"
        })}
        result = parse_completion(msg)
        self.assertIsNotNone(result)
        self.assertEqual(result["taskId"], "t5")


if __name__ == "__main__":
    unittest.main()

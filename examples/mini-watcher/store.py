"""JSONL-based task store with file locking — stdlib only."""

import json
import os
import fcntl
from datetime import datetime
from typing import Dict, List, Optional

from models import Task


class TaskStore:
    """Append-only JSONL store; latest version of each task wins."""

    def __init__(self, path: str):
        self.path = os.path.expanduser(path)
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        if not os.path.exists(self.path):
            open(self.path, "w").close()

    def _read_all(self) -> Dict[str, Task]:
        tasks: Dict[str, Task] = {}
        try:
            with open(self.path, "r") as f:
                fcntl.flock(f, fcntl.LOCK_SH)
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        t = Task.from_json(line)
                        tasks[t.task_id] = t
                    except (json.JSONDecodeError, KeyError, TypeError):
                        continue
                fcntl.flock(f, fcntl.LOCK_UN)
        except FileNotFoundError:
            pass
        return tasks

    def _append(self, task: Task) -> None:
        with open(self.path, "a") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            f.write(task.to_json() + "\n")
            f.flush()
            os.fsync(f.fileno())
            fcntl.flock(f, fcntl.LOCK_UN)

    def register(self, task: Task) -> Task:
        existing = self._read_all()
        if task.task_id in existing:
            raise ValueError(f"Task {task.task_id!r} already exists")
        task.created_at = datetime.now().isoformat()
        task.updated_at = task.created_at
        self._append(task)
        return task

    def get(self, task_id: str) -> Optional[Task]:
        return self._read_all().get(task_id)

    def active_tasks(self) -> List[Task]:
        return [t for t in self._read_all().values() if not t.is_terminal()]

    def update(self, task_id: str, **patch) -> Optional[Task]:
        task = self.get(task_id)
        if not task:
            return None
        d = task.to_dict()
        d.update({k: v for k, v in patch.items() if k != "task_id"})
        d["updated_at"] = datetime.now().isoformat()
        updated = Task.from_dict(d)
        self._append(updated)
        return updated

    def close(self, task_id: str, final_state: str) -> Optional[Task]:
        return self.update(task_id, current_state=final_state, terminal=True)

    def compact(self) -> int:
        """Rewrite file keeping only latest version of each task."""
        tasks = self._read_all()
        before = os.path.getsize(self.path) if os.path.exists(self.path) else 0
        with open(self.path, "w") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            for t in tasks.values():
                f.write(t.to_json() + "\n")
            f.flush()
            os.fsync(f.fileno())
            fcntl.flock(f, fcntl.LOCK_UN)
        after = os.path.getsize(self.path)
        return max(0, before - after)

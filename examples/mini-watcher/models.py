"""Minimal data models for task monitoring — no external dependencies."""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional, Dict, Any
import json


TERMINAL_STATES = frozenset(["completed", "failed", "timeout", "cancelled"])


@dataclass
class Task:
    """A monitored async task."""
    task_id: str
    owner: str = ""
    subject: str = ""
    current_state: str = "registered"
    last_notified_state: str = ""
    status_file: str = ""
    report_file: str = ""
    reply_to: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    expires_at: Optional[str] = None
    terminal: bool = False
    delivery_ok: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.last_notified_state:
            self.last_notified_state = self.current_state

    def is_terminal(self) -> bool:
        return self.terminal or self.current_state in TERMINAL_STATES

    def is_expired(self) -> bool:
        if not self.expires_at:
            return False
        try:
            return datetime.now() > datetime.fromisoformat(self.expires_at)
        except (ValueError, TypeError):
            return False

    def state_changed(self) -> bool:
        return self.current_state != self.last_notified_state

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Task":
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in data.items() if k in known})

    @classmethod
    def from_json(cls, line: str) -> "Task":
        return cls.from_dict(json.loads(line))


@dataclass
class StateResult:
    """Result of checking a task's current state."""
    state: str
    terminal: bool = False
    summary: str = ""
    error: str = ""

#!/usr/bin/env python3
"""OpenClaw Agent Protocol - Message Format Examples

This module demonstrates how to construct and parse messages
following the AGENT_PROTOCOL.md specification.

Usage:
    from protocol_messages import (
        create_handoff_message,
        create_status_update,
        parse_inbound_message,
        MessageType
    )
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any, List
import json


class MessageType(Enum):
    """Standard message types per AGENT_PROTOCOL.md Section 3."""
    HANDOFF = "handoff"
    ACK = "ack"
    STATUS_UPDATE = "status_update"
    REQUEST = "request"
    RESPONSE = "response"
    ERROR = "error"
    HEARTBEAT = "heartbeat"


class TaskState(Enum):
    """Task lifecycle states per AGENT_PROTOCOL.md Section 5."""
    PENDING = "pending"
    ACKNOWLEDGED = "acknowledged"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class AgentIdentity:
    """Agent identity per AGENT_PROTOCOL.md Section 2.

    Format: agent:<name>:<transport>:<channel>
    Example: agent:trading:discord:trading-room
    """
    name: str
    transport: str = "discord"  # discord, slack, webhook, etc.
    channel: str = "general"

    def to_address(self) -> str:
        return f"agent:{self.name}:{self.transport}:{self.channel}"

    @classmethod
    def from_address(cls, address: str) -> "AgentIdentity":
        """Parse agent address string."""
        parts = address.split(":")
        if len(parts) != 4 or parts[0] != "agent":
            raise ValueError(f"Invalid agent address: {address}")
        return cls(name=parts[1], transport=parts[2], channel=parts[3])


@dataclass
class HandoffContext:
    """Handoff context per AGENT_PROTOCOL.md Appendix A."""
    reason: str
    priority: str = "normal"  # critical, high, normal, low
    deadline: Optional[str] = None  # ISO 8601 format
    required_capabilities: List[str] = field(default_factory=list)
    constraints: Dict[str, Any] = field(default_factory=dict)
    history_summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "reason": self.reason,
            "priority": self.priority,
            "deadline": self.deadline,
            "required_capabilities": self.required_capabilities,
            "constraints": self.constraints,
            "history_summary": self.history_summary,
        }


@dataclass
class Message:
    """Standard message envelope per AGENT_PROTOCOL.md Section 3."""
    msg_type: MessageType
    from_agent: AgentIdentity
    to_agent: AgentIdentity
    payload: Dict[str, Any]
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    msg_id: str = field(default_factory=lambda: f"msg_{datetime.utcnow().timestamp()}")
    parent_msg_id: Optional[str] = None
    requires_ack: bool = True
    ack_timeout_seconds: int = 30

    def to_dict(self) -> Dict[str, Any]:
        return {
            "msg_id": self.msg_id,
            "msg_type": self.msg_type.value,
            "from": self.from_agent.to_address(),
            "to": self.to_agent.to_address(),
            "timestamp": self.timestamp,
            "payload": self.payload,
            "parent_msg_id": self.parent_msg_id,
            "requires_ack": self.requires_ack,
            "ack_timeout_seconds": self.ack_timeout_seconds,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Message":
        """Parse message from dictionary."""
        return cls(
            msg_type=MessageType(data["msg_type"]),
            from_agent=AgentIdentity.from_address(data["from"]),
            to_agent=AgentIdentity.from_address(data["to"]),
            payload=data.get("payload", {}),
            timestamp=data.get("timestamp", datetime.utcnow().isoformat()),
            msg_id=data.get("msg_id", f"msg_{datetime.utcnow().timestamp()}"),
            parent_msg_id=data.get("parent_msg_id"),
            requires_ack=data.get("requires_ack", True),
            ack_timeout_seconds=data.get("ack_timeout_seconds", 30),
        )


def create_handoff_message(
    from_agent: AgentIdentity,
    to_agent: AgentIdentity,
    task_id: str,
    task_description: str,
    context: HandoffContext,
    parent_msg_id: Optional[str] = None,
) -> Message:
    """Create a handoff message per AGENT_PROTOCOL.md Section 4.

    Example:
        >>> from_agent = AgentIdentity("trading", "discord", "trading-room")
        >>> to_agent = AgentIdentity("macro", "discord", "macro-room")
        >>> context = HandoffContext(
        ...     reason="Need macro analysis for trading signal",
        ...     priority="high",
        ...     required_capabilities=["macro_analysis", "economic_calendar"]
        ... )
        >>> msg = create_handoff_message(
        ...     from_agent, to_agent, "task_001", "Analyze FOMC impact", context
        ... )
    """
    payload = {
        "task_id": task_id,
        "task_description": task_description,
        "handoff_context": context.to_dict(),
        "expected_outcome": "Analysis report with actionable insights",
        "escalation_path": ["user:main"],  # Fallback if handoff fails
    }

    return Message(
        msg_type=MessageType.HANDOFF,
        from_agent=from_agent,
        to_agent=to_agent,
        payload=payload,
        parent_msg_id=parent_msg_id,
        requires_ack=True,
        ack_timeout_seconds=60,  # Handoffs get longer timeout
    )


def create_status_update(
    agent: AgentIdentity,
    task_id: str,
    state: TaskState,
    summary: str,
    details: Optional[Dict[str, Any]] = None,
    report_file: Optional[str] = None,
) -> Message:
    """Create a status update message per AGENT_PROTOCOL.md Section 5.

    Example:
        >>> msg = create_status_update(
        ...     agent=AgentIdentity("trading", "discord", "trading-room"),
        ...     task_id="task_001",
        ...     state=TaskState.IN_PROGRESS,
        ...     summary="Fetching market data...",
        ...     details={"progress_percent": 30}
        ... )
    """
    payload = {
        "task_id": task_id,
        "state": state.value,
        "summary": summary,
        "details": details or {},
    }

    if report_file:
        payload["report_file"] = report_file

    return Message(
        msg_type=MessageType.STATUS_UPDATE,
        from_agent=agent,
        to_agent=AgentIdentity("main", "discord", "control-room"),
        payload=payload,
        requires_ack=False,  # Status updates don't require ACK
    )


def create_ack_message(
    original_msg: Message,
    acknowledged_by: AgentIdentity,
    status: str = "accepted",  # accepted, rejected, queued
    reason: Optional[str] = None,
) -> Message:
    """Create an ACK response per AGENT_PROTOCOL.md Section 4.2.

    The ACK message follows the 2-phase commit pattern:
    1. Sender marks message as "pending"
    2. Receiver responds with ACK
    3. Sender updates status based on ACK response
    """
    payload = {
        "acknowledged_msg_id": original_msg.msg_id,
        "status": status,  # accepted, rejected, queued
        "original_msg_type": original_msg.msg_type.value,
    }

    if reason:
        payload["reason"] = reason

    if status == "queued":
        payload["estimated_start_time"] = (
            datetime.utcnow().isoformat()
        )

    return Message(
        msg_type=MessageType.ACK,
        from_agent=acknowledged_by,
        to_agent=original_msg.from_agent,
        payload=payload,
        parent_msg_id=original_msg.msg_id,
        requires_ack=False,
    )


def parse_inbound_message(raw_data: str) -> Message:
    """Parse an incoming message from JSON string.

    Raises:
        ValueError: If message format is invalid
    """
    try:
        data = json.loads(raw_data)
        return Message.from_dict(data)
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        raise ValueError(f"Invalid message format: {e}") from e


# Example usage
if __name__ == "__main__":
    print("=" * 60)
    print("OpenClaw Protocol Message Examples")
    print("=" * 60)

    # Example 1: Handoff message
    print("\n1. HANDOFF MESSAGE (Section 4)")
    print("-" * 40)

    trading = AgentIdentity("trading", "discord", "trading-room")
    macro = AgentIdentity("macro", "discord", "macro-room")

    handoff_ctx = HandoffContext(
        reason="FOMC announcement requires macro analysis",
        priority="critical",
        deadline="2024-03-15T14:00:00Z",
        required_capabilities=["macro_analysis", "economic_data"],
        history_summary="Trading signal generated, need confirmation",
    )

    handoff_msg = create_handoff_message(
        from_agent=trading,
        to_agent=macro,
        task_id="task_fomc_001",
        task_description="Analyze FOMC impact on tech stocks",
        context=handoff_ctx,
    )

    print(handoff_msg.to_json())

    # Example 2: Status update
    print("\n2. STATUS UPDATE (Section 5)")
    print("-" * 40)

    status_msg = create_status_update(
        agent=macro,
        task_id="task_fomc_001",
        state=TaskState.IN_PROGRESS,
        summary="Fetching economic calendar data...",
        details={"data_sources": ["bls", "fed"], "progress": 25},
    )

    print(status_msg.to_json())

    # Example 3: ACK message
    print("\n3. ACK MESSAGE (Section 4.2)")
    print("-" * 40)

    ack_msg = create_ack_message(
        original_msg=handoff_msg,
        acknowledged_by=macro,
        status="accepted",
    )

    print(ack_msg.to_json())

    # Example 4: Parse message
    print("\n4. PARSE MESSAGE")
    print("-" * 40)

    json_str = handoff_msg.to_json()
    parsed = parse_inbound_message(json_str)
    print(f"Parsed message type: {parsed.msg_type.value}")
    print(f"From: {parsed.from_agent.to_address()}")
    print(f"Task ID: {parsed.payload.get('task_id')}")

    print("\n" + "=" * 60)
    print("Examples complete. See source code for usage patterns.")
    print("=" * 60)

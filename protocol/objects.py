from dataclasses import dataclass
from typing import Any


@dataclass
class UserRequest:
    """
    Payload for USER_INPUT_SUBMITTED.
    """

    text: str
    source: str
    request_id: str
    timestamp: float


@dataclass
class AgentStatus:
    """
    Payload for STATUS_CHANGED.
    """

    status: str
    message: str


@dataclass
class ToolResult:
    """
    Payload for TOOL_RESULT.
    """

    tool_name: str
    tool_call_id: str
    output: Any
    success: bool

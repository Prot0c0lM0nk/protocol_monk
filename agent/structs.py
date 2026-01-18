from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List
import time
import uuid


@dataclass
class UserRequest:
    """Payload for USER_INPUT_SUBMITTED."""

    text: str
    source: str
    request_id: str
    timestamp: float
    context: Optional[Dict[str, Any]] = None


@dataclass
class ToolRequest:
    """Internal object representing a 'Need to run a tool'."""

    name: str
    parameters: Dict[str, Any]
    call_id: str
    requires_confirmation: bool = False


@dataclass
class ToolResult:
    """The outcome of an execution."""

    tool_name: str
    call_id: str
    success: bool
    output: Any
    duration: float
    error: Optional[str] = None


@dataclass
class ModelConfig:
    """Configuration for a specific model."""

    name: str
    provider: str
    context_window: int
    cost_per_token: Optional[float] = None

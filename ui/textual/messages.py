"""
ui/textual/messages.py
Custom Textual Messages for Agent-UI Communication
"""

from typing import Dict, Any
from textual.message import Message
from ui.base import ToolResult


class AgentStreamChunk(Message):
    """A chunk of streaming text from the agent."""

    def __init__(self, chunk: str):
        self.chunk = chunk
        super().__init__()


class AgentThinkingStatus(Message):
    """Indicates whether the agent is thinking/processing."""

    def __init__(self, is_thinking: bool):
        self.is_thinking = is_thinking
        super().__init__()


class AgentToolResult(Message):
    """Result of a tool execution."""

    def __init__(self, tool_name: str, result: ToolResult):
        self.tool_name = tool_name
        self.result = result
        super().__init__()


class AgentSystemMessage(Message):
    """System message (info, error, warning, etc.)."""

    def __init__(self, message: str, type: str = "info"):
        self.message = message
        self.type = type  # info, error, warning, response_complete
        super().__init__()


class AgentStatusUpdate(Message):
    """Carries updated agent statistics to the UI."""

    def __init__(self, stats: Dict[str, Any]):
        self.stats = stats
        super().__init__()

"""
ui/textual/messages.py
EDA Message Definitions for the Textual Bridge.
"""

from textual.message import Message
from typing import Any, Dict, Optional
from ui.base import ToolResult


class AgentStreamChunk(Message):
    """Real-time text from the LLM."""

    def __init__(self, chunk: str) -> None:
        self.chunk = chunk
        super().__init__()


class AgentThinkingStatus(Message):
    """Updates the thinking/processing state."""

    def __init__(self, is_thinking: bool) -> None:
        self.is_thinking = is_thinking
        super().__init__()


class AgentToolResult(Message):
    """The result of a tool execution."""

    def __init__(self, tool_name: str, result: ToolResult) -> None:
        self.tool_name = tool_name
        self.result = result
        super().__init__()


class AgentToolRequest(Message):
    """Request for user confirmation of a tool."""

    def __init__(self, tool_name: str, params: Dict[str, Any]) -> None:
        self.tool_name = tool_name
        self.params = params
        super().__init__()


class AgentSystemMessage(Message):
    """System notifications (Error, Info, Warning)."""

    def __init__(self, text: str, type: str = "info") -> None:
        self.text = text
        self.type = type  # 'info', 'error', 'warning', 'success', 'response_complete'
        super().__init__()

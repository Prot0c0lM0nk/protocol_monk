from textual.message import Message
from typing import Any, Dict


class StreamText(Message):
    """New text arriving from the model."""

    def __init__(self, text: str):
        self.text = text
        super().__init__()


class AgentMessage(Message):
    """Generic event from agent (error, info, tool_call)."""

    def __init__(self, type: str, data: Any):
        self.type = type
        self.data = data
        super().__init__()


class UpdateStatus(Message):
    """State change (thinking=True/False)."""

    def __init__(self, key: str, value: Any):
        self.key = key
        self.value = value
        super().__init__()

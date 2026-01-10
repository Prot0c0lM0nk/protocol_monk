from textual.message import Message
from typing import Any, Dict, Optional


class StreamChunkMsg(Message):
    """
    Carries a piece of streaming text from the model to the UI.
    """

    def __init__(self, chunk: str):
        self.chunk = chunk
        super().__init__()


class ThinkingStatusMsg(Message):
    """
    Signals the start or end of the "thinking" state (often used by reasoning models).
    """

    def __init__(self, is_thinking: bool, message: str = ""):
        self.is_thinking = is_thinking
        self.message = message
        super().__init__()


class ToolConfirmationRequestMsg(Message):
    """
    Triggers the Modal Dialog for user approval.
    """

    def __init__(self, tool_data: Dict[str, Any], auto_confirm: bool = False):
        self.tool_data = tool_data
        self.auto_confirm = auto_confirm
        super().__init__()


class ToolResultMsg(Message):
    """
    Displays the output of a tool execution in the chat.
    """

    def __init__(self, tool_name: str, result: Any):
        self.tool_name = tool_name
        self.result = result
        super().__init__()


class AgentLogMsg(Message):
    """
    Maps standard agent events (`INFO`, `WARNING`, `ERROR`) to UI notifications.
    """

    def __init__(self, level: str, message: str):
        self.level = level
        self.message = message
        super().__init__()


class StatusUpdateMsg(Message):
    """
    Updates the Header or Status Bar with non-chat state.
    """

    def __init__(
        self,
        model: Optional[str] = None,
        provider: Optional[str] = None,
        context_usage: Optional[str] = None,
    ):
        self.model = model
        self.provider = provider
        self.context_usage = context_usage
        super().__init__()

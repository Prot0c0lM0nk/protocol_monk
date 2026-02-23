"""Textual messages used by the Protocol Monk Textual app."""

from textual.message import Message


class AgentStreamChunk(Message):
    def __init__(self, chunk: str, channel: str = "content"):
        self.chunk = chunk
        self.channel = channel
        super().__init__()


class AgentStatusUpdate(Message):
    def __init__(
        self,
        status: str,
        detail: str = "",
        provider: str | None = None,
        model: str | None = None,
        auto_confirm: bool | None = None,
        working_dir: str | None = None,
    ):
        self.status = status
        self.detail = detail
        self.provider = provider
        self.model = model
        self.auto_confirm = auto_confirm
        self.working_dir = working_dir
        super().__init__()


class AgentToolResult(Message):
    def __init__(self, payload: dict):
        self.payload = payload
        super().__init__()


class AgentSystemMessage(Message):
    def __init__(self, message: str, level: str = "info"):
        self.message = message
        self.level = level
        super().__init__()

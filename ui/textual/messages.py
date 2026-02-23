"""Textual messages used by the Protocol Monk Textual app."""

from textual.message import Message


class AgentStreamChunk(Message):
    def __init__(
        self,
        chunk: str,
        channel: str = "content",
        pass_id: str | None = None,
        sequence: int | None = None,
    ):
        self.chunk = chunk
        self.channel = channel
        self.pass_id = pass_id
        self.sequence = sequence
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


class AgentResponseComplete(Message):
    def __init__(
        self,
        pass_id: str = "",
        content: str = "",
        tool_call_count: int = 0,
    ):
        self.pass_id = pass_id
        self.content = content
        self.tool_call_count = tool_call_count
        super().__init__()

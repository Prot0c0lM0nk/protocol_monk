"""Chat area using reference widget class names for CSS compatibility."""

from rich.markup import escape
from textual.containers import VerticalScroll
from textual.widgets import Markdown, Static


class UserMessage(Markdown):
    pass


class AIMessage(Markdown):
    pass


class ThinkingIndicator(Static):
    pass


class ToolResultWidget(Static):
    pass


class ChatArea(VerticalScroll):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._current_ai: AIMessage | None = None
        self._current_ai_text = ""
        self._thinking: ThinkingIndicator | None = None

    async def add_user_message(self, content: str) -> None:
        widget = UserMessage(escape(content))
        await self.mount(widget)
        widget.scroll_visible()

    def add_stream_chunk(self, chunk: str, is_thinking: bool = False) -> None:
        if not chunk:
            return

        if is_thinking:
            if self._thinking is None:
                self._thinking = ThinkingIndicator("")
                self.mount(self._thinking)
            self._thinking.update(f"☦ {escape(chunk)}")
            self.call_after_refresh(self.scroll_end, animate=False)
            return

        if self._current_ai is None:
            self._current_ai_text = chunk
            self._current_ai = AIMessage("")
            self.mount(self._current_ai)
        else:
            self._current_ai_text += chunk

        self._current_ai.update(escape(self._current_ai_text))
        self.call_after_refresh(self.scroll_end, animate=False)

    def show_thinking(self, is_thinking: bool, detail: str = "") -> None:
        if is_thinking:
            if self._thinking is None:
                self._thinking = ThinkingIndicator("")
                self.mount(self._thinking)
            self._thinking.update(f"☦ {escape(detail or 'Contemplating...')}")
            self.call_after_refresh(self.scroll_end, animate=False)
            return

        if self._thinking is not None:
            self._thinking.remove()
            self._thinking = None

    def add_tool_result(self, payload: dict) -> None:
        tool = str(payload.get("tool_name", "tool"))
        success = bool(payload.get("success", False))
        summary = payload.get("output") if success else payload.get("error")
        summary_text = str(summary) if summary is not None else ""
        marker = "OK" if success else "ERR"
        widget = ToolResultWidget(f"[{marker}] {escape(tool)} - {escape(summary_text)}")
        self.mount(widget)
        self.call_after_refresh(self.scroll_end, animate=False)

    def finalize_response(self) -> None:
        self._current_ai = None
        self._current_ai_text = ""

    async def clear_chat(self) -> None:
        await self.remove_children("*")
        self._current_ai = None
        self._current_ai_text = ""
        self._thinking = None

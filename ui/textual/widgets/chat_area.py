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
        self._current_ai_pass_id = ""
        self._thinking: ThinkingIndicator | None = None
        self._stream_flush_interval = 0.04
        self._stream_flush_scheduled = False
        self._stream_dirty = False

    async def add_user_message(self, content: str) -> None:
        widget = UserMessage(escape(content))
        await self.mount(widget)
        widget.scroll_visible()

    def add_stream_chunk(
        self,
        chunk: str,
        is_thinking: bool = False,
        pass_id: str | None = None,
        sequence: int | None = None,
    ) -> None:
        if not chunk:
            return

        if is_thinking:
            if self._thinking is None:
                self._thinking = ThinkingIndicator("")
                self.mount(self._thinking)
            self._thinking.update(f"☦ {escape(chunk)}")
            self.call_after_refresh(self.scroll_end, animate=False)
            return

        incoming_pass_id = str(pass_id or "").strip()
        if self._current_ai is None:
            self._current_ai_text = chunk
            self._current_ai_pass_id = incoming_pass_id
            self._current_ai = AIMessage("")
            self.mount(self._current_ai)
        elif (
            incoming_pass_id
            and self._current_ai_pass_id
            and incoming_pass_id != self._current_ai_pass_id
        ):
            self.finalize_response(pass_id=self._current_ai_pass_id, force=True)
            self._current_ai_text = chunk
            self._current_ai_pass_id = incoming_pass_id
            self._current_ai = AIMessage("")
            self.mount(self._current_ai)
        else:
            self._current_ai_text += chunk
            if incoming_pass_id and not self._current_ai_pass_id:
                self._current_ai_pass_id = incoming_pass_id

        self._stream_dirty = True
        self._schedule_stream_flush()

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

    def _schedule_stream_flush(self) -> None:
        if self._stream_flush_scheduled:
            return
        self._stream_flush_scheduled = True
        self.set_timer(self._stream_flush_interval, self._flush_stream_buffer)

    def _flush_stream_buffer(self) -> None:
        self._stream_flush_scheduled = False
        message = self._current_ai
        if message is None:
            self._stream_dirty = False
            return
        if not self._stream_dirty:
            return
        if not message.is_mounted:
            self._schedule_stream_flush()
            return
        message.update(escape(self._current_ai_text))
        self._stream_dirty = False
        message.scroll_visible()

    def _commit_pending_stream_text(self) -> None:
        message = self._current_ai
        if message is None:
            return
        if self._current_ai_text:
            message.update(escape(self._current_ai_text))
        if message.is_mounted:
            message.scroll_visible()

    def finalize_response(self, pass_id: str = "", force: bool = False) -> None:
        incoming_pass_id = str(pass_id or "").strip()
        if (
            not force
            and incoming_pass_id
            and self._current_ai_pass_id
            and incoming_pass_id != self._current_ai_pass_id
        ):
            return
        self._commit_pending_stream_text()
        self._current_ai = None
        self._current_ai_text = ""
        self._current_ai_pass_id = ""
        self._stream_dirty = False

    async def clear_chat(self) -> None:
        await self.remove_children("*")
        self._current_ai = None
        self._current_ai_text = ""
        self._current_ai_pass_id = ""
        self._thinking = None
        self._stream_dirty = False
        self._stream_flush_scheduled = False

"""
ui/textual/widgets/chat_area.py
Chat area widget for Protocol Monk TUI
"""

import json
from datetime import datetime
from typing import Dict, Optional

from rich.markup import escape
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Markdown, Static

from ..models import DetailRecord
from ..screens.modals.detail_viewer import DetailViewerModal


class UserMessage(Markdown):
    """User message bubble (Grey)."""

    pass


class AIMessage(Markdown):
    """AI message bubble (Monk Green)."""

    pass


class ThinkingIndicator(Static):
    """Animated prayer-rope inspired activity indicator."""

    THINKING_FRAMES = ("☦", "†", "✠", "☩")
    TOOL_FRAMES = ("✢", "✣", "✤", "✥")
    APPROVAL_FRAMES = ("◐", "◓", "◑", "◒")
    DEFAULT_TEXT = {
        "thinking": "Contemplating...",
        "tools": "Executing tools...",
        "approval": "Awaiting approval...",
    }

    def __init__(self, phase: str = "thinking", detail: str = ""):
        super().__init__("", classes="thinking-indicator")
        self.phase = phase
        self.detail = detail
        self._frame_index = 0
        self._timer = None

    def on_mount(self) -> None:
        self._timer = self.set_interval(0.18, self._advance_frame)
        self._render_frame()

    def on_unmount(self) -> None:
        if self._timer is not None:
            self._timer.stop()

    def update_phase(self, phase: str = "thinking", detail: str = "") -> None:
        self.phase = phase or "thinking"
        self.detail = detail
        self._frame_index = 0
        self._render_frame()

    def _frames(self) -> tuple[str, ...]:
        if self.phase == "tools":
            return self.TOOL_FRAMES
        if self.phase == "approval":
            return self.APPROVAL_FRAMES
        return self.THINKING_FRAMES

    def _advance_frame(self) -> None:
        self._frame_index += 1
        self._render_frame()

    def _render_frame(self) -> None:
        frames = self._frames()
        glyph = frames[self._frame_index % len(frames)]
        text = self.detail.strip() or self.DEFAULT_TEXT.get(self.phase, "Working...")
        self.update(f"{glyph} {escape(text)}")


class ToolResultWidget(Static):
    """Compact tool result bullet."""

    pass


class ThinkingSummaryWidget(Static):
    """Compact summary bullet for hidden reasoning."""

    pass


class ChatArea(VerticalScroll):
    """Main chat area that displays conversation history."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._current_ai_message: Optional[AIMessage] = None
        self._current_ai_text = ""
        self._thinking_indicator: Optional[ThinkingIndicator] = None
        self._current_thinking_text = ""
        self._stream_flush_interval = 0.04
        self._stream_flush_scheduled = False
        self._stream_dirty = False
        self._details: Dict[str, DetailRecord] = {}
        self._detail_order: list[str] = []
        self._detail_counter = 0

    def compose(self) -> ComposeResult:
        """Create the initial chat area content."""
        yield from ()

    async def add_user_message(self, content: str) -> None:
        """Add a user message to the chat."""
        msg = UserMessage(content)
        await self.mount(msg)
        msg.scroll_visible()

    async def add_ai_message(self, content: str) -> None:
        """Add a new AI message to the chat."""
        # Finalize any previous AI message first
        self.finalize_response()

        # Create new AI message
        self._current_ai_text = content
        self._current_ai_message = AIMessage(content)
        await self.mount(self._current_ai_message)
        self._current_ai_message.scroll_visible()

    def add_stream_chunk(self, chunk: str, is_thinking: bool = False) -> None:
        """Add a streaming chunk to the current AI message."""
        if not chunk:
            return

        if is_thinking:
            self._current_thinking_text += chunk
            return

        if self._current_ai_message is None:
            # Start a new AI message if none exists
            self._current_ai_text = chunk
            self._current_ai_message = AIMessage("")
            self.mount(self._current_ai_message)
        else:
            # Append to existing message
            self._current_ai_text += chunk
        self._stream_dirty = True
        self._schedule_stream_flush()

    def _schedule_stream_flush(self) -> None:
        if self._stream_flush_scheduled:
            return
        self._stream_flush_scheduled = True
        self.set_timer(self._stream_flush_interval, self._flush_stream_buffer)

    def _flush_stream_buffer(self) -> None:
        self._stream_flush_scheduled = False
        message = self._current_ai_message
        if message is None:
            self._stream_dirty = False
            return
        if not self._stream_dirty:
            return
        if not message.is_mounted:
            self._schedule_stream_flush()
            return
        message.update(self._current_ai_text)
        self._stream_dirty = False
        message.scroll_visible()

    def _sync_current_ai_message(self) -> None:
        """Flush buffered text once the streaming markdown widget is mounted."""
        self._flush_stream_buffer()

    def show_thinking(
        self,
        is_thinking: bool,
        phase: str = "thinking",
        detail: str = "",
    ) -> None:
        """Show or hide the thinking indicator."""
        if is_thinking:
            if self._thinking_indicator is None:
                self._thinking_indicator = ThinkingIndicator(phase=phase, detail=detail)
                self.mount(self._thinking_indicator)
            else:
                self._thinking_indicator.update_phase(phase=phase, detail=detail)
            self.call_after_refresh(self.scroll_end, animate=False)
        else:
            if self._thinking_indicator is not None:
                self._thinking_indicator.remove()
                self._thinking_indicator = None

    def add_tool_result(self, tool_name: str, result) -> None:
        """Add a compact tool result bullet with expandable detail."""
        success_icon = "✅" if result.success else "❌"
        raw_output = str(getattr(result, "output", "") or "")
        summary = self._summarize_text(raw_output) or "No output"
        syntax_hint = self._infer_tool_syntax(tool_name)

        detail_parts = [raw_output]
        result_data = getattr(result, "data", None)
        if isinstance(result_data, dict) and result_data:
            detail_parts.extend(["", "Metadata:", json.dumps(result_data, indent=2)])

        record = self.register_detail(
            kind="tool_result",
            title=f"Tool Result: {tool_name}",
            summary=summary,
            full_text="\n".join(detail_parts).strip(),
            syntax_hint=syntax_hint,
            tool_name=tool_name,
        )
        view_link = self._view_link(record.id)
        tool_widget = ToolResultWidget(
            f"{success_icon} {escape(tool_name)} - {escape(summary)} {view_link}"
        )
        self.mount(tool_widget)
        self.call_after_refresh(self.scroll_end, animate=False)

    def register_detail(
        self,
        *,
        kind: str,
        title: str,
        summary: str,
        full_text: str,
        syntax_hint: Optional[str] = None,
        tool_name: Optional[str] = None,
    ) -> DetailRecord:
        """Register and return a session-scoped detail record."""
        self._detail_counter += 1
        record_id = f"d{self._detail_counter:04d}"
        record = DetailRecord(
            id=record_id,
            kind=kind,
            title=title,
            summary=summary,
            full_text=full_text,
            syntax_hint=syntax_hint,
            tool_name=tool_name,
            created_at=datetime.now(),
        )
        self._details[record_id] = record
        self._detail_order.append(record_id)
        return record

    def get_detail(self, detail_id: str) -> Optional[DetailRecord]:
        """Get a detail record by ID."""
        return self._details.get(detail_id)

    def last_detail_id(self) -> Optional[str]:
        """Return the most recently added detail ID."""
        if not self._detail_order:
            return None
        return self._detail_order[-1]

    def open_detail(self, detail_id: Optional[str] = None) -> None:
        """Open the detail modal for a record."""
        target_id = detail_id or self.last_detail_id()
        if not target_id:
            self.app.notify("No detail available.", severity="warning")
            return

        record = self._details.get(target_id)
        if not record:
            self.app.notify(f"Detail '{target_id}' not found.", severity="error")
            return

        self.app.push_screen(DetailViewerModal(record))

    def _emit_thinking_summary(self) -> None:
        """Store one hidden reasoning detail per assistant turn."""
        full_text = self._current_thinking_text.strip()
        if not full_text:
            return

        summary = f"Thinking captured ({len(full_text)} chars)"
        record = self.register_detail(
            kind="thinking",
            title="Reasoning Detail",
            summary=summary,
            full_text=full_text,
            syntax_hint=None,
        )
        bullet = ThinkingSummaryWidget(f"🧠 {escape(summary)} {self._view_link(record.id)}")
        self.mount(bullet)
        self.call_after_refresh(self.scroll_end, animate=False)

    def _view_link(self, detail_id: str) -> str:
        return f"[@click=app.open_detail('{detail_id}')]View[/]"

    @staticmethod
    def _summarize_text(text: str, max_len: int = 120) -> str:
        stripped = text.strip()
        if not stripped:
            return ""
        line = stripped.splitlines()[0]
        if len(line) <= max_len:
            return line
        return f"{line[: max_len - 1]}..."

    @staticmethod
    def _infer_tool_syntax(tool_name: str) -> Optional[str]:
        if tool_name in {"replace_lines", "delete_lines", "insert_in_file", "append_to_file"}:
            return "diff"
        if tool_name == "run_python":
            return "python"
        if tool_name in {"execute_command", "git_operation"}:
            return "bash"
        return None

    def finalize_response(self) -> None:
        """Finalize the current AI response."""
        # Hide thinking indicator
        self.show_thinking(False)
        self._emit_thinking_summary()
        self._commit_pending_stream_text()

        # Reset current AI message pointer and accumulated text
        self._current_ai_message = None
        self._current_ai_text = ""
        self._current_thinking_text = ""
        self._stream_dirty = False

    def _commit_pending_stream_text(self) -> None:
        """Flush remaining stream text before finalizing a turn."""
        message = self._current_ai_message
        if message is None:
            return
        if self._current_ai_text:
            message.update(self._current_ai_text)
        if message.is_mounted:
            message.scroll_visible()

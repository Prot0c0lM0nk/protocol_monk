"""Rich renderer for streaming, status, and tool event output."""

from __future__ import annotations

import time
from collections import deque
from typing import Any, Mapping

from rich import box
from rich.console import Console, Group, RenderableType
from rich.live import Live
from rich.markdown import Markdown
from rich.table import Column, Table
from rich.text import Text

from .styles import console as default_console
from .styles import panel, state_style


class RichRenderer:
    """Render Protocol Monk events in a Rich-first terminal experience."""

    def __init__(
        self,
        *,
        output_console: Console | None = None,
        render_interval: float = 0.08,
        body_history_limit: int = 200,
    ) -> None:
        self._console = output_console or default_console
        self._render_interval = max(render_interval, 0.01)
        self._body_entries: deque[RenderableType] = deque(maxlen=max(body_history_limit, 20))
        self._history_dropped = 0

        self._live: Live | None = None
        self._live_suspended = False
        self._locked_for_input = False
        self._last_render_time = 0.0

        self._thinking_text = ""
        self._content_text = ""
        self._header_state: dict[str, Any] = {}
        self._header_renderable = self._build_header_renderable()

    def render_banner(self) -> None:
        self._console.print("=" * 60, style="muted")
        self._console.print("Protocol Monk Rich UI", style="info")
        self._console.print("Enter submits | /aa toggles auto-approve | quit exits", style="muted")
        self._console.print("=" * 60, style="muted")
        self._console.print()

    def start_live_session(self) -> None:
        if self._live is not None:
            self.refresh_frame(force=True)
            return
        self._live_suspended = False
        self._live = Live(
            self._build_frame(),
            console=self._console,
            auto_refresh=True,
            refresh_per_second=8,
            vertical_overflow="crop",
            transient=False,
        )
        self._live.start()
        self.refresh_frame(force=True)

    def stop_live_session(self) -> None:
        if self._live is None:
            self._live_suspended = False
            return
        try:
            self._live.stop()
        except Exception:
            pass
        self._live = None
        self._live_suspended = False

    def suspend_live_session(self) -> None:
        self._locked_for_input = True
        if self._live is None:
            self._live_suspended = True
            return
        try:
            self._live.stop()
        except Exception:
            pass
        self._live = None
        self._live_suspended = True

    def resume_live_session(self) -> None:
        self._locked_for_input = False
        if not self._live_suspended and self._live is None:
            return
        self._live_suspended = False
        if self._live is None:
            self._live = Live(
                self._build_frame(),
                console=self._console,
                auto_refresh=True,
                refresh_per_second=8,
                vertical_overflow="crop",
                transient=False,
            )
            self._live.start()
        self.refresh_frame(force=True)

    def lock_for_input(self) -> None:
        self.suspend_live_session()

    def unlock_for_input(self) -> None:
        self.resume_live_session()

    def update_header(self, **header_updates: Any) -> bool:
        """Merge header state and return True when values changed."""
        changed = False
        for key, value in header_updates.items():
            if self._header_state.get(key) != value:
                self._header_state[key] = value
                changed = True
        if changed:
            self._header_renderable = self._build_header_renderable()
        return changed

    def refresh_frame(self, *, force: bool = False) -> None:
        if self._live is None or self._locked_for_input:
            return
        now = time.monotonic()
        if not force and now - self._last_render_time < self._render_interval:
            return
        self._last_render_time = now
        self._live.update(self._build_frame(), refresh=True)

    def render_header_if_changed(self, *, force: bool = False) -> None:
        """Backward compatible no-print shim for prior renderer contract."""
        self.refresh_frame(force=force)

    def append_event_line(
        self,
        kind: str,
        text: str,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        if metadata and "renderable" in metadata:
            renderable = metadata["renderable"]
        else:
            renderable = self._format_event_line(kind, text)
        self._append_body_entry(renderable)
        self.refresh_frame(force=False)

    def render_status(self, status: str, message: str = "") -> None:
        normalized = (status or "idle").strip().lower()
        self.update_header(state=normalized)
        self.refresh_frame(force=False)

    def clear_stream_visual_state(self) -> None:
        """Clear transient stream visuals before modal input flows."""
        self._thinking_text = ""
        self._content_text = ""
        self.refresh_frame(force=True)

    def update_stream(self, *, thinking: str, content: str) -> None:
        self._thinking_text = thinking
        self._content_text = content
        self.refresh_frame(force=False)

    def finalize_response(
        self,
        *,
        thinking: str,
        content: str,
        empty_marker: bool = False,
    ) -> None:
        normalized_thinking = thinking.strip()
        normalized_content = content.strip()
        if self._is_reasoning_duplicate(normalized_thinking, normalized_content):
            normalized_thinking = ""

        if normalized_thinking:
            self._append_body_entry(
                panel(
                    Text(normalized_thinking, style="thinking"),
                    title="Reasoning",
                    border_style="muted",
                )
            )
        if normalized_content:
            body = (
                Markdown(normalized_content)
                if self._looks_like_markdown(normalized_content)
                else Text(normalized_content, style="agent.text")
            )
            self._append_body_entry(panel(body, title="Assistant", border_style="agent.border"))
        elif empty_marker:
            self._append_body_entry(
                panel(Text("[Empty pass]", style="muted"), title="Assistant", border_style="muted")
            )

        self._thinking_text = ""
        self._content_text = ""
        self.refresh_frame(force=True)

    def render_tool_confirmation(self, tool_name: str, parameters: Mapping[str, Any]) -> None:
        table = Table(box=None, show_header=False, padding=(0, 1))
        table.add_column("k", style="muted", no_wrap=True)
        table.add_column("v", style="agent.text")
        if parameters:
            for key, value in parameters.items():
                text = str(value)
                if len(text) > 240:
                    text = f"{text[:240]}... [truncated {len(text) - 240} chars]"
                table.add_row(str(key), text)
        else:
            table.add_row("params", "(none)")
        self._append_body_entry(
            panel(
                Group(
                    Text(f"Tool request: {tool_name}", style="tool"),
                    Text("Respond with y (yes), a (yes + auto), or n (reject).", style="muted"),
                    table,
                ),
                title="Tool Confirmation",
                border_style="tool",
            )
        )
        self.refresh_frame(force=True)

    def render_tool_start(self, tool_name: str) -> None:
        self.append_event_line("tool", f"{tool_name}")

    def render_tool_output_preview(
        self,
        *,
        success: bool,
        output: Any = None,
        error: Any = None,
        full_output_available: bool = False,
    ) -> None:
        if output is not None and output != "":
            text = str(output)
            summary = text if len(text) <= 160 else f"{text[:160]}... ({len(text)} chars)"
            if full_output_available:
                summary = f"{summary} [preview truncated; full output available]"
            self.append_event_line("success" if success else "error", f"{summary}")
        if not success and error:
            self.append_event_line("error", str(error))

    def render_tool_output_full(
        self,
        *,
        tool_name: str,
        output_text: str,
        truncated: bool = False,
        omitted_chars: int = 0,
    ) -> None:
        body = Text(output_text, style="agent.text")
        if truncated and omitted_chars > 0:
            body.append(
                f"\n\n[truncated: omitted {omitted_chars} chars]",
                style="warning",
            )
        self._append_body_entry(
            panel(
                body,
                title=f"Tool Output: {tool_name}",
                border_style="tool",
            )
        )
        self.refresh_frame(force=True)

    def render_tool_progress(self, *, tool_name: str, progress: Any, message: str) -> None:
        label = f"{tool_name} progress"
        if progress is not None:
            label = f"{label} {progress}%"
        if message:
            label = f"{label}: {message}"
        self.append_event_line("muted", label)

    def render_tool_complete(self, *, tool_name: str, success: bool, duration: float) -> None:
        style = "success" if success else "error"
        symbol = "✓" if success else "✗"
        self.append_event_line(style, f"{symbol} {tool_name} ({duration:.2f}s)")

    def render_warning(self, message: str) -> None:
        self.append_event_line("warning", message)

    def render_error(self, message: str, *, recovered: bool = False) -> None:
        suffix = " (recovered)" if recovered else ""
        self.append_event_line("error", f"{message}{suffix}")

    def render_info(self, message: str) -> None:
        self.append_event_line("info", message)

    def shutdown(self) -> None:
        self.stop_live_session()

    def _build_frame(self):
        return Group(self._header_renderable, self._build_body_panel())

    def _build_body_panel(self):
        renderables: list[RenderableType] = list(self._body_entries)

        thinking = self._thinking_text.strip()
        content = self._content_text.strip()
        if thinking:
            renderables.append(
                panel(Text(thinking, style="thinking"), title="Thinking", border_style="muted")
            )
        if content:
            body = Markdown(content) if self._looks_like_markdown(content) else Text(content, style="agent.text")
            renderables.append(panel(body, title="Assistant", border_style="agent.border"))

        if not renderables:
            renderables.append(Text("Waiting for input...", style="muted"))

        title = "Session"
        if self._history_dropped > 0:
            title = f"Session (history capped, dropped={self._history_dropped})"
        return panel(Group(*renderables), title=title, border_style="muted")

    def _append_body_entry(self, renderable: RenderableType) -> None:
        if self._body_entries.maxlen and len(self._body_entries) >= self._body_entries.maxlen:
            self._history_dropped += 1
        self._body_entries.append(renderable)

    def _format_event_line(self, kind: str, text: str) -> Text:
        normalized = (kind or "info").strip().lower()
        style_map = {
            "info": ("info", "ℹ "),
            "warning": ("warning", "⚠ "),
            "error": ("error", "✗ "),
            "tool": ("tool", "▶ "),
            "success": ("success", "✓ "),
            "assistant": ("agent.text", ""),
            "thinking": ("thinking", ""),
            "muted": ("muted", ""),
        }
        style, prefix = style_map.get(normalized, ("agent.text", ""))
        return Text(f"{prefix}{text}", style=style)

    @staticmethod
    def _looks_like_markdown(text: str) -> bool:
        return any(token in text for token in ("```", "#", "*", "_", ">", "- ", "1. "))

    @staticmethod
    def _normalize_for_dedupe(text: str) -> str:
        return " ".join((text or "").strip().split()).lower()

    @classmethod
    def _is_reasoning_duplicate(cls, thinking: str, content: str) -> bool:
        if not thinking or not content:
            return False
        return cls._normalize_for_dedupe(thinking) == cls._normalize_for_dedupe(content)

    def _build_header_renderable(self):
        header = self._header_state
        provider = str(header.get("provider", "?") or "?")
        model = str(header.get("model", "?") or "?")
        state = str(header.get("state", "idle") or "idle")
        auto_confirm = bool(header.get("auto_confirm", False))
        tokens = int(header.get("total_tokens", 0) or 0)
        context_limit = int(header.get("context_limit", 0) or 0)
        message_count = int(header.get("message_count", 0) or 0)
        loaded_files = int(header.get("loaded_files_count", 0) or 0)
        usage = f"{tokens}/{context_limit}" if context_limit > 0 else f"{tokens}/?"
        auto_text = "on" if auto_confirm else "off"

        table = Table(
            Column("state", style=state_style(state), no_wrap=True),
            Column("provider", style="info", no_wrap=True),
            Column("model", style="agent.text", no_wrap=False),
            Column("context", style="muted", no_wrap=True),
            Column("messages", style="muted", no_wrap=True),
            Column("files", style="muted", no_wrap=True),
            Column("auto", style="tool", no_wrap=True),
            show_header=False,
            box=box.MINIMAL,
            padding=(0, 1),
            expand=True,
        )
        table.add_row(
            f"state={state}",
            f"provider={provider}",
            f"model={model}",
            f"context={usage}",
            f"messages={message_count}",
            f"files={loaded_files}",
            f"auto={auto_text}",
        )
        return panel(table, title="Status", border_style="muted")

"""Rich renderer for streaming, status, and tool event output."""

from __future__ import annotations

import time
from typing import Any, Mapping

from rich import box
from rich.console import Console, Group
from rich.live import Live
from rich.markdown import Markdown
from rich.table import Column
from rich.table import Table
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
    ) -> None:
        self._console = output_console or default_console
        self._render_interval = max(render_interval, 0.01)
        self._live: Live | None = None
        self._last_render_time = 0.0
        self._locked_for_input = False
        self._thinking_text = ""
        self._content_text = ""
        self._last_status: tuple[str, str] = ("", "")
        self._header_state: dict[str, Any] = {}
        self._header_signature: tuple[Any, ...] = ()
        self._header_renderable = self._build_header_renderable()
        self._header_printed = False

    def render_banner(self) -> None:
        self._console.print("=" * 60, style="muted")
        self._console.print("Protocol Monk Rich UI", style="info")
        self._console.print("Enter submits | /aa toggles auto-approve | quit exits", style="muted")
        self._console.print("=" * 60, style="muted")
        self._console.print()

    def update_header(self, **header_updates: Any) -> bool:
        """Merge header state and return True when values changed."""
        changed = False
        for key, value in header_updates.items():
            if self._header_state.get(key) != value:
                self._header_state[key] = value
                changed = True
        if changed:
            self._header_renderable = self._build_header_renderable()
            if self._live is not None and not self._locked_for_input:
                self._render_live(force=True)
        return changed

    def render_header_if_changed(self, *, force: bool = False) -> None:
        """
        Render the scrollback header once at startup unless explicitly forced.

        We avoid printing a new header panel for every state transition.
        """
        signature = self._header_signature_tuple()
        if not force and self._header_printed:
            self._header_signature = signature
            return
        if not force and signature == self._header_signature and self._header_printed:
            return
        self._header_signature = signature
        self._console.print(self._header_renderable)
        self._header_printed = True

    def render_status(self, status: str, message: str = "") -> None:
        normalized = (status or "idle").strip().lower()
        key = (normalized, message or "")
        if key == self._last_status:
            return
        self._last_status = key
        style = state_style(normalized)
        if message:
            self._console.print(f"[{style}]state={normalized}[/] [muted]- {message}[/]")
        else:
            self._console.print(f"[{style}]state={normalized}[/]")

    def lock_for_input(self) -> None:
        self._locked_for_input = True
        self._stop_live()

    def unlock_for_input(self) -> None:
        self._locked_for_input = False

    def clear_stream_visual_state(self) -> None:
        """Clear transient stream visuals before modal input flows."""
        self._stop_live()
        self._thinking_text = ""
        self._content_text = ""

    def update_stream(self, *, thinking: str, content: str) -> None:
        if self._locked_for_input:
            return
        self._thinking_text = thinking
        self._content_text = content
        if not thinking and not content:
            return
        self._ensure_live()
        self._render_live(force=False)

    def finalize_response(
        self,
        *,
        thinking: str,
        content: str,
        empty_marker: bool = False,
    ) -> None:
        self._thinking_text = thinking
        self._content_text = content
        self._render_live(force=True)
        self._stop_live()

        normalized_thinking = thinking.strip()
        normalized_content = content.strip()
        if self._is_reasoning_duplicate(normalized_thinking, normalized_content):
            normalized_thinking = ""

        if normalized_thinking:
            self._console.print(
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
            self._console.print(panel(body, title="Assistant", border_style="agent.border"))
        elif empty_marker:
            self._console.print(
                panel(Text("[Empty pass]", style="muted"), title="Assistant", border_style="muted")
            )

        self._console.print()
        self._thinking_text = ""
        self._content_text = ""

    def render_tool_confirmation(self, tool_name: str, parameters: Mapping[str, Any]) -> None:
        self._stop_live()
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
        self._console.print(
            panel(
                Group(
                    Text(f"Tool request: {tool_name}", style="tool"),
                    Text("Select Yes, Yes+Auto, or No in the confirmation dialog.", style="muted"),
                    table,
                ),
                title="Tool Confirmation",
                border_style="tool",
            )
        )

    def render_tool_start(self, tool_name: str) -> None:
        self._console.print(f"[tool]▶ {tool_name}[/]")

    def render_tool_output_preview(
        self,
        *,
        success: bool,
        output: Any = None,
        error: Any = None,
    ) -> None:
        if output is not None and output != "":
            text = str(output)
            summary = text if len(text) <= 160 else f"{text[:160]}... ({len(text)} chars)"
            style = "success" if success else "error"
            self._console.print(f"[{style}]  → {summary}[/{style}]")
        if not success and error:
            self._console.print(f"[error]  ✗ {error}[/]")

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
        self._console.print(
            panel(
                body,
                title=f"Tool Output: {tool_name}",
                border_style="tool",
            )
        )

    def render_tool_complete(self, *, tool_name: str, success: bool, duration: float) -> None:
        style = "success" if success else "error"
        symbol = "✓" if success else "✗"
        self._console.print(f"[{style}]  {symbol} {tool_name} ({duration:.2f}s)[/{style}]")

    def render_warning(self, message: str) -> None:
        self._console.print(f"[warning]⚠ {message}[/]")

    def render_error(self, message: str, *, recovered: bool = False) -> None:
        suffix = " (recovered)" if recovered else ""
        self._console.print(f"[error]✗ {message}{suffix}[/]")

    def render_info(self, message: str) -> None:
        self._console.print(f"[info]ℹ {message}[/]")

    def shutdown(self) -> None:
        self._stop_live()

    def _ensure_live(self) -> None:
        if self._live is not None:
            return
        self._live = Live(
            Group(self._header_renderable, panel(Text("", style="agent.text"), title="Assistant")),
            console=self._console,
            refresh_per_second=8,
            vertical_overflow="ellipsis",
            transient=True,
        )
        self._live.start()

    def _render_live(self, *, force: bool) -> None:
        if self._live is None:
            return
        now = time.monotonic()
        if not force and now - self._last_render_time < self._render_interval:
            return
        self._last_render_time = now

        renderables = []
        renderables.append(self._header_renderable)
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
            renderables.append(panel(Text("", style="agent.text"), title="Assistant"))

        self._live.update(Group(*renderables))

    def _stop_live(self) -> None:
        if self._live is None:
            return
        try:
            self._live.stop()
        except Exception:
            pass
        self._live = None

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

    def _header_signature_tuple(self) -> tuple[Any, ...]:
        header = self._header_state
        return (
            header.get("provider"),
            header.get("model"),
            header.get("state"),
            bool(header.get("auto_confirm", False)),
            int(header.get("total_tokens", 0) or 0),
            int(header.get("context_limit", 0) or 0),
            int(header.get("message_count", 0) or 0),
            int(header.get("loaded_files_count", 0) or 0),
        )

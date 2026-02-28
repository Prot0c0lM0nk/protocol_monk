"""Rich renderer for streaming, status, and tool event output."""

from __future__ import annotations

import time
from typing import Any, Mapping

from rich.console import Console, Group
from rich.live import Live
from rich.markdown import Markdown
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

    def render_banner(self) -> None:
        self._console.print("=" * 60, style="muted")
        self._console.print("Protocol Monk Rich UI", style="info")
        self._console.print("Enter submits | /aa toggles auto-approve | quit exits", style="muted")
        self._console.print("=" * 60, style="muted")
        self._console.print()

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

    def render_tool_result(self, *, success: bool, output: Any = None, error: Any = None) -> None:
        if output:
            text = str(output)
            summary = text if len(text) <= 160 else f"{text[:160]}... ({len(text)} chars)"
            style = "success" if success else "error"
            self._console.print(f"[{style}]  → {summary}[/{style}]")
        if not success and error:
            self._console.print(f"[error]  ✗ {error}[/]")

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
            panel(Text("", style="agent.text"), title="Assistant"),
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

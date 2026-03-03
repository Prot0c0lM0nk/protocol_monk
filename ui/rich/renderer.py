"""Rich renderer for streaming, status, and tool event output.

Implements a scrollback-native approach where:
- Content prints to terminal scrollback naturally
- Live streaming shows in a transient panel that disappears cleanly
- Thinking streams in dim+italic, transitions to normal response with separator
- No header pinned to top (status becomes modal via /status command)
"""

from __future__ import annotations

import re
import time
from collections import deque
from typing import Any, Mapping

from rich import box
from rich.console import Console, Group, RenderableType
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.status import Status
from rich.table import Column, Table
from rich.text import Text

from .styles import console as default_console
from .styles import THINKING_STYLE, create_monk_panel, panel, state_style


class StreamingPanel:
    """Handles streaming display separately from scrollback.

    Key insight: streaming and final render phases have different constraints.
    During streaming we keep rendering stable (plain text body), while final
    commit can render markdown for richer presentation.
    """

    def __init__(self, console: Console, render_interval: float = 0.08) -> None:
        self._console = console
        self._render_interval = render_interval
        self._live: Live | None = None
        self._status: Status | None = None
        self._thinking: str = ""
        self._content: str = ""
        self._last_render_time = 0.0
        self._started = False

    def begin_thinking(self, message: str = "Contemplating...") -> None:
        """Start a new pass with a spinner while waiting for stream content."""
        self.clear()
        self._started = True
        self._status = self._console.status(
            f"[dim]{message}[/]",
            spinner="dots",
            spinner_style="monk.border",
        )
        self._status.start()

    def stop_thinking(self) -> None:
        """Stop spinner if currently active."""
        if self._status is not None:
            self._status.stop()
            self._status = None

    def set_buffers(self, *, thinking: str, content: str) -> None:
        """Replace internal stream buffers with caller-managed aggregates."""
        self._thinking = thinking
        self._content = content
        self._started = True

    def update_buffers(self, *, thinking: str, content: str) -> None:
        """Update panel buffers and refresh a Live display."""
        self.set_buffers(thinking=thinking, content=content)

        if not (thinking.strip() or content.strip()):
            return

        self.stop_thinking()

        if self._live is None:
            self._live = Live(
                self._build_panel(final=False),
                console=self._console,
                auto_refresh=False,
                refresh_per_second=12,
                transient=False,
            )
            self._live.start()
            # Allow the first update to render immediately.
            self._last_render_time = 0.0

        self.refresh()

    def refresh(self, *, force: bool = False) -> None:
        """Refresh Live panel with throttling."""
        if self._live is None:
            return

        now = time.monotonic()
        if force or now - self._last_render_time >= self._render_interval:
            self._live.update(self._build_panel(final=False), refresh=True)
            self._last_render_time = now

    def finish(self) -> bool:
        """Finish streaming - stop Live and print final panel to scrollback."""
        had_content = bool(self._thinking.strip() or self._content.strip())
        self.stop_thinking()

        if self._live is not None:
            # Push one final committed frame before stopping Live.
            self._live.update(self._build_panel(final=True), refresh=True)
            self._live.stop()
            self._live = None
        elif had_content:
            # Fallback-only path: response completed without opening Live.
            self._console.print(self._build_panel(final=True))

        self._thinking = ""
        self._content = ""
        self._started = False
        return had_content

    def clear(self) -> None:
        """Clear streaming state without printing."""
        self.stop_thinking()
        if self._live is not None:
            self._live.stop()
            self._live = None
        self._thinking = ""
        self._content = ""
        self._started = False

    def _build_panel(self, *, final: bool) -> RenderableType:
        """Build separate panels for thinking and response content."""
        panels: list[RenderableType] = []

        thinking = self._clean_think_tags(self._thinking).strip()
        content = self._clean_think_tags(self._content).strip()

        # Deduplicate: if thinking matches content, skip showing thinking
        if self._is_duplicate(thinking, content):
            thinking = ""

        # The Cell panel for reasoning (grey border, grey italic text)
        if thinking:
            panels.append(
                Panel(
                    Text(thinking, style=THINKING_STYLE),
                    title="The Cell",
                    title_align="left",
                    border_style="grey50",
                    box=box.ROUNDED,
                    padding=(0, 1),
                )
            )

        # Response panel (normal styling)
        if content:
            if final and self._looks_like_markdown(content):
                body = Markdown(content)
            else:
                body = Text(content, style="monk.text")
            panels.append(
                Panel(
                    body,
                    title="✠ Monk",
                    title_align="left",
                    border_style="monk.border",
                    box=box.ROUNDED,
                    padding=(0, 1),
                )
            )

        if not panels:
            return Panel(
                Text("Waiting...", style="muted"),
                title="✠ Monk",
                title_align="left",
                border_style="monk.border",
                box=box.ROUNDED,
                padding=(0, 1),
            )

        return Group(*panels)

    @staticmethod
    def _is_duplicate(thinking: str, content: str) -> bool:
        """Check if thinking content duplicates response content."""
        if not thinking or not content:
            return False
        # Normalize for comparison
        norm_thinking = " ".join(thinking.lower().split())
        norm_content = " ".join(content.lower().split())
        return norm_thinking == norm_content

    @staticmethod
    def _clean_think_tags(text: str) -> str:
        """Clean up raw XML tags if they leak into the stream."""
        text = re.sub(r"<think>", "", text)
        text = re.sub(r"</think>", "\n\n", text)
        return text

    @staticmethod
    def _looks_like_markdown(text: str) -> bool:
        return any(token in text for token in ("```", "#", "*", "_", ">", "- ", "1. "))


class RichRenderer:
    """Render Protocol Monk events in a Rich-first terminal experience.

    Uses scrollback-native approach:
    - Content prints directly to terminal for natural scrollback
    - StreamingPanel handles transient live display during AI response
    - No persistent header (status available via /status command)
    """

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

        # Streaming panel for live display
        self._streaming = StreamingPanel(self._console, self._render_interval)

        # State tracking
        self._input_lock_depth = 0

    # --- Banner and Lifecycle ---

    def render_banner(self) -> None:
        """Print the startup banner to scrollback."""
        self._console.print()
        self._console.print("═" * 50, style="monk.border")
        self._console.print("  Protocol Monk", style="monk.text")
        self._console.print(
            "  Enter submits | /aa /reset /status /compact | quit|exit|bye sign off",
            style="muted",
        )
        self._console.print("═" * 50, style="monk.border")
        self._console.print()

    def start_live_session(self) -> None:
        """No-op for compatibility. Scrollback is always active."""
        pass

    def stop_live_session(self) -> None:
        """Stop any active streaming."""
        self._streaming.clear()

    def suspend_live_session(self) -> None:
        """Lock for input - clears streaming state."""
        self.lock_for_input()

    def resume_live_session(self) -> None:
        """Unlock after input."""
        self.unlock_for_input()

    def lock_for_input(self) -> None:
        """Call before asking for user input."""
        self._input_lock_depth += 1
        if self._input_lock_depth == 1:
            self._streaming.clear()

    def unlock_for_input(self) -> None:
        """Call after user input is received."""
        if self._input_lock_depth > 0:
            self._input_lock_depth -= 1
        if self._input_lock_depth < 0:
            self._input_lock_depth = 0

    def refresh_frame(self, *, force: bool = False) -> None:
        """No-op for compatibility. No persistent Live display."""
        pass

    def render_header_if_changed(self, *, force: bool = False) -> None:
        """No-op for compatibility. No header to render."""
        pass

    def update_header(self, **header_updates: Any) -> bool:
        """No-op for compatibility. No header state maintained."""
        return False

    # --- Streaming ---

    def clear_stream_visual_state(self) -> None:
        """Clear transient stream visuals before modal input flows."""
        self._streaming.clear()

    def start_thinking(self, message: str = "Contemplating...") -> None:
        """Start spinner while the model is thinking before stream content arrives."""
        if self._input_lock_depth > 0:
            return
        self._streaming.begin_thinking(message)

    def stop_thinking(self) -> None:
        """Stop the thinking spinner."""
        self._streaming.stop_thinking()

    def update_stream(self, *, thinking: str, content: str) -> None:
        """Update streaming display with current buffers."""
        if self._input_lock_depth > 0:
            return

        self._streaming.update_buffers(thinking=thinking, content=content)

    def finalize_response(
        self,
        *,
        thinking: str,
        content: str,
        empty_marker: bool = False,
    ) -> None:
        """Commit the completed response to scrollback.

        Prints the EXACT SAME panel that was shown during streaming,
        ensuring visual consistency with no artifacts on transition.
        """
        # Final content may arrive via RESPONSE_COMPLETE even when no stream chunks were sent.
        self._streaming.set_buffers(thinking=thinking, content=content)

        # Stop streaming and print the final panel
        self._streaming.finish()

        # Handle empty response case
        if empty_marker and not thinking.strip() and not content.strip():
            self._console.print(
                create_monk_panel(Text("[Empty pass]", style="muted"))
            )

        self._console.print()  # Add spacing after response

    def render_status(self, status: str, message: str = "") -> None:
        """Render a status message (used for state changes)."""
        normalized = (status or "idle").strip().lower()
        style = state_style(normalized)
        text = f"[{style}]{normalized}[/{style}]"
        if message:
            text = f"{text}: {message}"
        self._console.print(text)

    def render_status_snapshot(self, payload: Mapping[str, Any]) -> None:
        """Render a concise status snapshot for /status command."""
        rows = [
            ("Provider", str(payload.get("provider", ""))),
            ("Model", str(payload.get("model", ""))),
            ("Working Dir", str(payload.get("working_directory", ""))),
            ("State", str(payload.get("state", ""))),
            ("Tokens", str(payload.get("total_tokens", ""))),
            ("Context Limit", str(payload.get("context_limit", ""))),
            ("Messages", str(payload.get("message_count", ""))),
            ("Loaded Files", str(payload.get("loaded_files_count", ""))),
            (
                "Auto-Approve",
                "enabled" if bool(payload.get("auto_confirm", False)) else "disabled",
            ),
        ]

        table = Table(
            Column("Field", style="user.text", no_wrap=True),
            Column("Value", style="monk.text"),
            show_header=False,
            box=None,
            padding=(0, 2),
        )
        for label, value in rows:
            table.add_row(label, value)

        self._console.print(
            Panel(
                table,
                title="[tech.cyan]Status[/]",
                border_style="tech.cyan",
                box=box.ROUNDED,
                padding=(0, 1),
            )
        )

    # --- Event Lines (for tool output, messages, etc.) ---

    def append_event_line(
        self,
        kind: str,
        text: str,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        """Append an event line to scrollback and print immediately."""
        if metadata and "renderable" in metadata:
            renderable = metadata["renderable"]
        else:
            renderable = self._format_event_line(kind, text)
        self._console.print(renderable)

    def render_tool_confirmation(self, tool_name: str, parameters: Mapping[str, Any]) -> None:
        """Render a tool confirmation request panel."""
        self._streaming.clear()

        # Separate simple and complex params
        simple_params = {}
        complex_params = {}
        for key, value in parameters.items():
            text = str(value)
            if "\n" in text or len(text) > 60:
                complex_params[key] = text
            else:
                simple_params[key] = value

        items: list[RenderableType] = [
            Text(f"I must invoke: {tool_name}", style="monk.text"),
            Text(""),
        ]

        if simple_params:
            table = Table(box=None, show_header=False, padding=(0, 2))
            table.add_column("Key", style="user.text")
            table.add_column("Val", style="tech.cyan")
            for k, v in simple_params.items():
                table.add_row(f"• {k}", str(v))
            items.append(table)
            items.append(Text(""))

        for k, v in complex_params.items():
            items.append(Text(f"• {k}:", style="user.text"))
            items.append(Panel(Text(v, style="muted"), border_style="dim"))
            items.append(Text(""))

        panel_content = Group(*items)
        self._console.print(
            Panel(
                panel_content,
                title="[tech.cyan]🛠 Sacred Action[/]",
                border_style="tech.cyan",
                box=box.ROUNDED,
            )
        )

    def render_tool_start(self, tool_name: str) -> None:
        """Print a tool start indicator."""
        self._console.print(f"  [tool]▶ {tool_name}[/]")

    def render_tool_output_preview(
        self,
        *,
        success: bool,
        output: Any = None,
        error: Any = None,
        full_output_available: bool = False,
    ) -> None:
        """Print a brief tool output preview."""
        style = "success" if success else "error"
        symbol = "✓" if success else "✗"

        if output is not None and output != "":
            text = str(output)
            summary = text if len(text) <= 160 else f"{text[:160]}... ({len(text)} chars)"
            if full_output_available:
                summary = f"{summary} [preview truncated; full output available]"
            self._console.print(f"  [{style}]{symbol}[/] [dim]{summary}[/]")
        if not success and error:
            self._console.print(f"  [error]✗ {error}[/]")

    def render_tool_output_full(
        self,
        *,
        tool_name: str,
        output_text: str,
        truncated: bool = False,
        omitted_chars: int = 0,
    ) -> None:
        """Print the full tool output in a panel."""
        body = Text(output_text, style="monk.text")
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

    def render_tool_progress(self, *, tool_name: str, progress: Any, message: str) -> None:
        """Print a tool progress update."""
        label = f"{tool_name} progress"
        if progress is not None:
            label = f"{label} {progress}%"
        if message:
            label = f"{label}: {message}"
        self._console.print(f"  [muted]{label}[/]")

    def render_tool_complete(self, *, tool_name: str, success: bool, duration: float) -> None:
        """Print a tool completion indicator."""
        style = "success" if success else "error"
        symbol = "✓" if success else "✗"
        self._console.print(f"  [{style}]{symbol} {tool_name} ({duration:.2f}s)[/]")

    def render_warning(self, message: str) -> None:
        """Print a warning message."""
        self._console.print(f"[warning]Warning:[/] [monk.text]{message}[/]")

    def render_error(self, message: str, *, recovered: bool = False) -> None:
        """Print an error message."""
        suffix = " (recovered)" if recovered else ""
        self._console.print(f"[error]✗ {message}{suffix}[/]")

    def render_info(self, message: str) -> None:
        """Print an info message."""
        self._console.print(f"[info]ℹ {message}[/]")

    def shutdown(self) -> None:
        """Clean up resources."""
        self._streaming.clear()

    # --- Private Helpers ---

    def _append_body_entry(self, renderable: RenderableType) -> None:
        """Store entry in history (for potential future use)."""
        if self._body_entries.maxlen and len(self._body_entries) >= self._body_entries.maxlen:
            self._history_dropped += 1
        self._body_entries.append(renderable)

    def _format_event_line(self, kind: str, text: str) -> Text:
        """Format an event line with appropriate styling."""
        normalized = (kind or "info").strip().lower()
        style_map = {
            "info": ("info", "ℹ "),
            "warning": ("warning", "⚠ "),
            "error": ("error", "✗ "),
            "tool": ("tool", "▶ "),
            "success": ("success", "✓ "),
            "assistant": ("monk.text", ""),
            "thinking": ("thinking", ""),
            "muted": ("muted", ""),
        }
        style, prefix = style_map.get(normalized, ("monk.text", ""))
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

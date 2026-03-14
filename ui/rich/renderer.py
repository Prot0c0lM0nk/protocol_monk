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
from typing import Any, Iterable, Mapping

from rich import box
from rich.console import Console, Group, RenderableType
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.status import Status
from rich.table import Column, Table
from rich.text import Text

from protocol_monk.ui.tool_output_presenter import ToolOutputView
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

    def is_live_active(self) -> bool:
        """Return True when Live rendering is currently active."""
        return self._live is not None

    def print_above_live(self, renderable: RenderableType | str) -> None:
        """Print above active Live frame when possible."""
        if self._live is not None:
            self._live.console.print(renderable)
            return
        self._console.print(renderable)

    def finish(self, *, final: bool = True) -> bool:
        """Finish streaming and commit the current frame.

        Args:
            final: If True, render final-phase view (allows markdown upgrade).
                If False, preserve the stream-phase frame exactly as displayed.
        """
        had_content = bool(self._thinking.strip() or self._content.strip())
        self.stop_thinking()

        if self._live is not None:
            # Push one final committed frame before stopping Live.
            self._live.update(self._build_panel(final=final), refresh=True)
            self._live.stop()
            self._live = None
        elif had_content:
            # Fallback-only path: response completed without opening Live.
            self._console.print(self._build_panel(final=final))

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
            "  Enter submits | /aa /reset /status /compact /orthocal | quit|exit|bye sign off",
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
        """Freeze/reset active stream visuals before tool/input flows."""
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
        self._streaming.finish(final=True)

        # Handle empty response case
        if empty_marker and not thinking.strip() and not content.strip():
            self._emit(
                create_monk_panel(Text("[Empty pass]", style="muted"))
            )

        self._emit("")  # Add spacing after response

    def finalize_tool_transition(
        self,
        *,
        thinking: str,
        content: str,
    ) -> None:
        """Freeze stream visuals before tool events without final render promotion."""
        self._streaming.set_buffers(thinking=thinking, content=content)
        self._streaming.finish(final=False)

    def render_status(self, status: str, message: str = "") -> None:
        """Render a status message (used for state changes)."""
        normalized = (status or "idle").strip().lower()
        style = state_style(normalized)
        text = f"[{style}]{normalized}[/{style}]"
        if message:
            text = f"{text}: {message}"
        self._emit(text)

    def render_status_snapshot(self, payload: Mapping[str, Any]) -> None:
        """Render a concise status snapshot for /status command."""
        rows = [
            ("Provider", str(payload.get("provider", ""))),
            ("Model", str(payload.get("model", ""))),
            ("Working Dir", str(payload.get("working_directory", ""))),
            ("State", str(payload.get("state", ""))),
            ("Stored History", self._metric_value(payload.get("stored_history_tokens"))),
            (
                "Next Request",
                self._metric_value(payload.get("estimated_next_request_tokens")),
            ),
            (
                "Reserved Output",
                self._metric_value(payload.get("reserved_completion_tokens")),
            ),
            ("Last Prompt", self._metric_value(payload.get("last_prompt_tokens"))),
            (
                "Last Completion",
                self._metric_value(payload.get("last_completion_tokens")),
            ),
            ("Last Total", self._metric_value(payload.get("last_total_tokens"))),
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

        self._emit(
            Panel(
                table,
                title="[tech.cyan]Status[/]",
                border_style="tech.cyan",
                box=box.ROUNDED,
                padding=(0, 1),
            )
        )

    def render_metrics_snapshot(self, payload: Mapping[str, Any]) -> None:
        """Render a detailed metrics snapshot for /metrics command."""
        summary_rows = [
            ("Provider", str(payload.get("provider", ""))),
            ("Model", str(payload.get("model", ""))),
            ("State", str(payload.get("state", ""))),
            ("Stored History", self._metric_value(payload.get("stored_history_tokens"))),
            (
                "Next Request",
                self._metric_value(payload.get("estimated_next_request_tokens")),
            ),
            (
                "Reserved Output",
                self._metric_value(payload.get("reserved_completion_tokens")),
            ),
            ("Last Prompt", self._metric_value(payload.get("last_prompt_tokens"))),
            (
                "Last Completion",
                self._metric_value(payload.get("last_completion_tokens")),
            ),
            ("Last Total", self._metric_value(payload.get("last_total_tokens"))),
            ("Context Limit", self._metric_value(payload.get("context_limit"))),
        ]

        summary = Table(
            Column("Field", style="user.text", no_wrap=True),
            Column("Value", style="monk.text"),
            show_header=False,
            box=None,
            padding=(0, 2),
        )
        for label, value in summary_rows:
            summary.add_row(label, value)

        renderables: list[RenderableType] = [summary]
        recent_records = payload.get("recent_records")
        if isinstance(recent_records, list) and recent_records:
            recent_table = Table(
                Column("Pass", style="user.text", no_wrap=True),
                Column("Prompt", style="monk.text", justify="right"),
                Column("Completion", style="monk.text", justify="right"),
                Column("Total", style="monk.text", justify="right"),
                Column("Delta", style="monk.text", justify="right"),
                Column("TPS", style="monk.text", justify="right"),
                show_header=True,
                box=box.SIMPLE_HEAD,
                padding=(0, 1),
            )
            for record in recent_records[:5]:
                if not isinstance(record, Mapping):
                    continue
                recent_table.add_row(
                    str(record.get("pass_id", "")),
                    self._metric_value(record.get("prompt_tokens")),
                    self._metric_value(record.get("completion_tokens")),
                    self._metric_value(record.get("total_tokens")),
                    self._metric_value(record.get("prompt_token_delta")),
                    self._metric_value(record.get("tokens_per_second")),
                )
            renderables.extend([Text(""), recent_table])

        self._emit(
            Panel(
                Group(*renderables),
                title="[tech.cyan]Metrics[/]",
                border_style="tech.cyan",
                box=box.ROUNDED,
                padding=(0, 1),
            )
        )

    @staticmethod
    def _metric_value(value: Any) -> str:
        if value is None:
            return "n/a"
        return str(value)

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
        self._emit(renderable)

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
        self._emit(
            Panel(
                panel_content,
                title="[tech.cyan]🛠 Sacred Action[/]",
                border_style="tech.cyan",
                box=box.ROUNDED,
            )
        )

    def render_tool_start(self, tool_name: str) -> None:
        """Tool start marker intentionally suppressed to reduce scrollback noise."""
        _ = tool_name

    def render_tool_output_preview(
        self,
        *,
        success: bool,
        preview_text: str = "",
        error: Any = None,
        full_output_available: bool = False,
    ) -> None:
        """Print a brief tool output preview."""
        style = "success" if success else "error"
        symbol = "✓" if success else "✗"

        if preview_text:
            summary = (
                preview_text
                if len(preview_text) <= 160
                else f"{preview_text[:160]}... ({len(preview_text)} chars)"
            )
            if full_output_available:
                summary = f"{summary} [preview truncated; full output available]"
            self._emit(f"  [{style}]{symbol}[/] [dim]{summary}[/]")
        if not success and error:
            self._emit(f"  [error]✗ {error}[/]")

    def render_tool_output_full(
        self,
        *,
        view: ToolOutputView,
        duration: float = 0.0,
        truncated: bool = False,
        omitted_chars: int = 0,
    ) -> None:
        """Print the full tool output in a panel."""
        body = self._build_tool_output_body(
            view=view,
            duration=duration,
            truncated=truncated,
            omitted_chars=omitted_chars,
        )
        self._emit(
            panel(
                body,
                title=view.viewer_title,
                border_style="tool",
            )
        )

    def render_tool_progress(self, *, tool_name: str, progress: Any, message: str) -> None:
        """Tool progress line intentionally suppressed to reduce UI noise."""
        _ = tool_name, progress, message

    def render_tool_complete(self, *, tool_name: str, success: bool, duration: float) -> None:
        """Print a tool completion indicator."""
        style = "success" if success else "error"
        symbol = "✓" if success else "✗"
        self._emit(f"  [{style}]{symbol} {tool_name} ({duration:.2f}s)[/]")

    def render_warning(self, message: str) -> None:
        """Print a warning message."""
        self._emit(f"[warning]Warning:[/] [monk.text]{message}[/]")

    def render_error(self, message: str, *, recovered: bool = False) -> None:
        """Print an error message."""
        suffix = " (recovered)" if recovered else ""
        self._emit(f"[error]✗ {message}{suffix}[/]")

    def render_info(self, message: str) -> None:
        """Print an info message."""
        self._emit(f"[info]ℹ {message}[/]")

    def shutdown(self) -> None:
        """Clean up resources."""
        self._streaming.clear()

    def _build_tool_output_body(
        self,
        *,
        view: ToolOutputView,
        duration: float,
        truncated: bool,
        omitted_chars: int,
    ) -> RenderableType:
        renderables: list[RenderableType] = []

        if view.preview_text:
            renderables.append(Text(view.preview_text, style="monk.text"))

        metadata_lines = list(view.metadata_lines)
        metadata_lines.append(f"Success: {view.success}")
        metadata_lines.append(f"Duration: {duration:.2f}s")
        renderables.append(self._build_tool_section("Common Metadata", metadata_lines))

        for section in view.sections:
            renderables.append(self._build_tool_section(section.title, section.lines))

        if view.raw_json_text:
            renderables.append(
                self._build_tool_section("Raw JSON", view.raw_json_text.splitlines())
            )

        if truncated and omitted_chars > 0:
            renderables.append(
                Text(f"[truncated: omitted {omitted_chars} chars]", style="warning")
            )

        return Group(*renderables)

    @staticmethod
    def _build_tool_section(
        title: str,
        lines: Iterable[str],
    ) -> RenderableType:
        line_list = [str(line) for line in lines if str(line)]
        heading = Text(title, style="tool")
        if not line_list:
            body = Text("(empty)", style="muted")
        else:
            body = Text("\n".join(line_list), style="monk.text")
        return Group(heading, body)

    # --- Private Helpers ---

    def _emit(self, renderable: RenderableType | str, *, prefer_live: bool = True) -> None:
        """Emit output through active Live console when appropriate."""
        if (
            prefer_live
            and self._input_lock_depth == 0
            and self._streaming.is_live_active()
        ):
            self._streaming.print_above_live(renderable)
            return
        self._console.print(renderable)

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

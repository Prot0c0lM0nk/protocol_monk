"""
ui/rich/renderer.py
Visual component manager. Handles Live displays and Thinking states.
"""

import re
from typing import Dict, Any

from rich.live import Live
from rich.markdown import Markdown
from rich.text import Text
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.console import Group
from rich.align import Align
from rich import box

from ui.base import ToolResult
from .styles import console, create_monk_panel


class RichRenderer:
    def __init__(self):
        self._live_display = None
        self._thinking_status = None

        # Split Buffers for "Inner Voice" vs "Outer Voice"
        self._reasoning_text = ""
        self._response_text = ""

    # --- COMMANDS & STATUS ---
    def render_command_result(self, success: bool, message: str):
        """Render the output of a slash command."""
        self.end_streaming()

        if not success:
            console.print(f"[error]🚫 {message}[/]")
            return

        # Check if message is complex (multiline)
        if "\n" in message or len(message) > 80:
            if any(c in message for c in ["#", "*", "-", "`"]):
                content = Markdown(message)
            else:
                content = Text(message, style="monk.text")

            panel = Panel(
                content,
                title="[tech.cyan]⚡ System Command[/]",
                border_style="tech.cyan",
                box=box.ROUNDED,
                padding=(0, 1),
            )
            console.print(panel)
        else:
            # Simple line output
            console.print(f"[tech.cyan]⚡ {message}[/]")
        console.print()

    def render_selection_list(self, title: str, items: list):
        """Render a themed selection table (1-based)."""
        self.end_streaming()

        t = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
        t.add_column("ID", style="tech.cyan", justify="right")
        t.add_column("Option", style="monk.text")

        for idx, item in enumerate(items, 1):
            if hasattr(item, "name"):
                name = getattr(item, "name", str(item))
                extra = ""
                if hasattr(item, "provider"):
                    extra = f" [dim]({item.provider})[/]"
                t.add_row(str(idx), name + extra)
            else:
                t.add_row(str(idx), str(item))

        panel = Panel(
            t, title=f"[monk.border]{title}[/]", border_style="dim", box=box.ROUNDED
        )
        console.print(panel)

    # --- BANNER ---
    def render_banner(self, greeting: str):
        self.end_streaming()
        ascii_art = """
 ███╗   ███╗ ██████╗ ███╗   ██╗██╗  ██╗
 ████╗ ████║██╔═══██╗████╗  ██║██║ ██╔╝
 ██╔████╔██║██║   ██║██╔██╗ ██║█████╔╝ 
 ██║╚██╔╝██║██║   ██║██║╚██╗██║██╔═██╗ 
 ██║ ╚═╝ ██║╚██████╔╝██║ ╚████║██║  ██╗
 ╚═╝     ╚═╝ ╚═════╝ ╚═╝  ╚═══╝╚═╝  ╚═╝
        """
        panel = Panel(
            Align.center(
                Group(
                    Text(ascii_art, style="monk.border", justify="center"),
                    Text(greeting, style="monk.text", justify="center"),
                )
            ),
            box=box.DOUBLE,
            border_style="monk.border",
            subtitle="[dim]v1.0 Orthodox Protocol[/]",
        )
        console.print(panel)

    # --- STREAMING ---
    def start_streaming(self):
        """Begin a Live context for streaming text."""
        if self._live_display:
            return

        self._reasoning_text = ""
        self._response_text = ""

        self._live_display = Live(
            create_monk_panel("", title="✠ Monk"),
            console=console,
            refresh_per_second=8,
            vertical_overflow="visible",
            transient=False,
        )
        self._live_display.start()

    def update_streaming(self, chunk: str, is_thinking: bool = False):
        """Add text to the correct buffer and update the live panel."""
        if not self._live_display:
            # Don't start live display for empty signals
            if not chunk and not self._reasoning_text and not self._response_text:
                return
            self.start_streaming()

        # 1. Route Chunk to Correct Buffer
        if is_thinking:
            self._reasoning_text += chunk
        else:
            self._response_text += chunk

        # 2. Prepare Display Components
        renderables = []

        # Clean tags from both buffers
        clean_reasoning = self._clean_think_tags(self._reasoning_text)
        clean_response = self._clean_think_tags(self._response_text)

        # A. Inner Voice (Reasoning) -> Text Component (Forced Style)
        if clean_reasoning.strip():
            # We force "dim italic" here, bypassing Markdown completely
            renderables.append(Text(clean_reasoning, style="dim italic"))
            # Add a spacer if we also have a response coming
            if clean_response.strip():
                renderables.append(Text(""))

        # B. Outer Voice (Response) -> Markdown Component (Rich Syntax)
        if clean_response.strip():
            # If it looks like Markdown, render as Markdown
            if any(c in clean_response for c in ["`", "#", "*", "_", ">"]):
                renderables.append(Markdown(clean_response))
            else:
                renderables.append(Text(clean_response, style="monk.text"))

        # 3. Update Live Panel
        if renderables:
            self._live_display.update(create_monk_panel(Group(*renderables)))

    def end_streaming(self):
        """Finalize the live display."""
        if self._live_display:
            try:
                self._live_display.stop()
            except Exception:
                pass
            self._live_display = None
            console.print()

    # --- THINKING SPINNER ---
    def start_thinking(self, message: str = "Contemplating..."):
        self.end_streaming()
        if not self._thinking_status:
            self._thinking_status = console.status(
                f"[dim]{message}[/]", spinner="dots", spinner_style="monk.border"
            )
            self._thinking_status.start()

    def stop_thinking(self):
        if self._thinking_status:
            self._thinking_status.stop()
            self._thinking_status = None

    # --- TOOLS ---
    def render_tool_confirmation(self, tool_name: str, params: Dict[str, Any]):
        self.end_streaming()
        self.stop_thinking()

        items = []
        items.append(Text(f"I must invoke: {tool_name}", style="monk.text"))
        items.append(Text(""))

        simple_params = {}
        complex_params = {}

        for k, v in params.items():
            s_val = str(v)
            if "\n" in s_val or len(s_val) > 60:
                complex_params[k] = s_val
            else:
                simple_params[k] = v

        if simple_params:
            t = Table(box=None, show_header=False, padding=(0, 2))
            t.add_column("Key", style="user.text")
            t.add_column("Val", style="tech.cyan")
            for k, v in simple_params.items():
                t.add_row(f"• {k}", str(v))
            items.append(t)
            items.append(Text(""))

        for k, v in complex_params.items():
            items.append(Text(f"• {k}:", style="user.text"))
            lexer = "python" if "py" in k else "bash"
            code = Syntax(v, lexer, theme="monokai", word_wrap=True)
            items.append(Panel(code, border_style="dim"))
            items.append(Text(""))

        panel = Panel(
            Group(*items),
            title="[tech.cyan]🛠 Sacred Action[/]",
            border_style="tech.cyan",
            box=box.ROUNDED,
        )
        console.print(panel)

    def render_tool_result(self, result: ToolResult, tool_name: str):
        self.end_streaming()
        style = "success" if result.success else "error"
        icon = "✓" if result.success else "✗"

        console.print(f"  [{style}]{icon} {tool_name}[/] [user.text]result:[/]")

        output = result.output or ""
        lines = output.splitlines()
        if len(lines) > 10:
            preview = "\n".join(lines[:10])
            preview += f"\n... ({len(lines)-10} more lines)"
            content = Text(preview, style="dim")
        else:
            content = Text(output, style="dim")

        console.print(Panel(content, box=box.MINIMAL, border_style=style))
        console.print()

    # --- HELPERS ---
    def _clean_think_tags(self, text: str) -> str:
        """
        Clean up raw XML tags if they leak into the stream.
        We preserve the content but remove the <think> wrapper.
        """
        text = re.sub(r"<think>", "", text)
        text = re.sub(r"</think>", "\n\n", text)
        return text

    def print_error(self, msg):
        console.print(f"[error]Error: {msg}[/]")

    def print_system(self, msg):
        console.print(f"[monk.text]System: {msg}[/]")

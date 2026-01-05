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
from rich import box

from ui.base import ToolResult
from .styles import console, create_monk_panel, create_task_completion_panel

class RichRenderer:
    def __init__(self):
        self._live_display = None
        self._thinking_status = None
        self._accumulated_text = ""

    # --- STREAMING ---
    def start_streaming(self):
        """Begin a Live context for streaming text."""
        if self._live_display:
            return

        self._accumulated_text = ""
        # transient=False -> Panel stays visible after we stop
        self._live_display = Live(
            create_monk_panel("", title="✠ Monk"),
            console=console,
            refresh_per_second=8,
            vertical_overflow="visible",
            transient=False 
        )
        self._live_display.start()

    def update_streaming(self, chunk: str):
        """Add text to the buffer and update the live panel."""
        if not self._live_display:
            self.start_streaming()

        self._accumulated_text += chunk
        
        # Clean <think> tags for display
        clean_text = self._clean_think_tags(self._accumulated_text)
        
        if clean_text.strip():
            # Auto-detect markdown vs plain text
            if any(c in clean_text for c in ["`", "#", "*", "_"]):
                content = Markdown(clean_text)
            else:
                content = Text(clean_text, style="monk.text")
            
            self._live_display.update(create_monk_panel(content))

    def end_streaming(self):
        """Finalize the live display."""
        if self._live_display:
            try:
                self._live_display.stop()
            except Exception:
                pass
            self._live_display = None
            console.print() # Spacer

    # --- THINKING ---
    def start_thinking(self, message: str = "Contemplating..."):
        """Show spinner."""
        self.end_streaming() # Safety
        if not self._thinking_status:
            self._thinking_status = console.status(
                f"[dim]{message}[/]",
                spinner="dots",
                spinner_style="monk.border" # Use the purple for spinner
            )
            self._thinking_status.start()

    def stop_thinking(self):
        if self._thinking_status:
            self._thinking_status.stop()
            self._thinking_status = None

    # --- TOOLS ---
    def render_tool_confirmation(self, tool_name: str, params: Dict[str, Any]):
        """Render the 'Sacred Action' request panel."""
        self.end_streaming()
        self.stop_thinking()

        items = []
        items.append(Text(f"I must invoke: {tool_name}", style="monk.text"))
        items.append(Text(""))

        # Simple params vs Complex (Code)
        simple_params = {}
        complex_params = {}
        
        for k, v in params.items():
            s_val = str(v)
            if "\n" in s_val or len(s_val) > 60:
                complex_params[k] = s_val
            else:
                simple_params[k] = v

        # 1. Table for simple params
        if simple_params:
            t = Table(box=None, show_header=False, padding=(0, 2))
            t.add_column("Key", style="user.text") # Grey keys
            t.add_column("Val", style="tech.cyan")
            for k, v in simple_params.items():
                t.add_row(f"• {k}", str(v))
            items.append(t)
            items.append(Text(""))

        # 2. Syntax blocks for code
        for k, v in complex_params.items():
            items.append(Text(f"• {k}:", style="user.text"))
            # Guess lexer
            lexer = "python" if "py" in k else "bash"
            code = Syntax(v, lexer, theme="monokai", word_wrap=True)
            items.append(Panel(code, border_style="dim"))
            items.append(Text(""))

        panel = Panel(
            *items,
            title="[tech.cyan]🛠 Sacred Action[/]",
            border_style="tech.cyan",
            box=box.ROUNDED
        )
        console.print(panel)

    def render_tool_result(self, result: ToolResult, tool_name: str):
        """Render success/fail output."""
        self.end_streaming()
        
        style = "success" if result.success else "error"
        icon = "✓" if result.success else "✗"
        
        # Header
        console.print(f"  [{style}]{icon} {tool_name}[/] [user.text]result:[/]")
        
        # Output Body (Truncated/Dimmed)
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
        """Remove <think> blocks for clean display."""
        return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)

    def print_error(self, msg):
        console.print(f"[error]Error: {msg}[/]")
    
    def print_system(self, msg):
        console.print(f"[monk.text]System: {msg}[/]")
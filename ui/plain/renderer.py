"""
ui/plain/renderer.py - The View Layer

Responsible for all Rich console operations and formatting.
Never handles input - only rendering.
"""

from rich.console import Console
from rich.markdown import Markdown
from rich.syntax import Syntax
from typing import Dict, Any

from ui.base import ToolResult
from ui.common import render_shared_error


class PlainRenderer:
    """
    Handles all visual output for Plain UI.
    Manages console state, thinking indicators, and code block detection.
    """

    def __init__(self):
        self.console = Console(
            force_terminal=True, color_system="truecolor", highlight=False
        )

        # State tracking
        self._thinking_active = False
        self._in_code_block = False
        self._code_lang = "text"
        self._in_thinking_block = False
        self._has_printed_thinking_header = False

    def print_system(self, message: str):
        """Print [SYS] tag in blue/grey"""
        self.console.print(f"[bold blue][SYS] {message}[/bold blue]")

    def print_error(self, message: str):
        """Use shared utility for clear red text."""
        render_shared_error(self.console, message, use_panel=False)

    def print_warning(self, message: str):
        """Print [WARN] tag in yellow"""
        self.console.print(f"[bold yellow][WARN] {message}[/bold yellow]")

    def start_thinking(self, message: str = "Thinking..."):
        """
        Start ephemeral thinking indicator.
        Prints [MONK] tag in green with no newline (uses \r).
        """
        self._thinking_active = True
        # Print newline first to ensure clean start
        self.console.print(f"\n[bold green][MONK][/bold green] {message}", end="\r")

    def stop_thinking(self):
        """Clear the ephemeral thinking line if active"""
        if self._thinking_active:
            self.console.print("\x1b[2K\r", end="")
            self._thinking_active = False

    def print_stream(self, text: str):
        """
        Stream text with thinking state handling.
        Clears ephemeral thinking line if active before printing.
        """
        if self._thinking_active:
            self.console.print("\x1b[2K\r", end="")
            self._thinking_active = False
            self.console.print("[bold green][MONK][/bold green] ", end="")

        self.console.print(text, end="", highlight=False)

    def render_line(self, line: str, is_thinking: bool = False):
        """
        Render a single line with appropriate formatting.
        Handles thinking blocks, code blocks, and markdown.
        """
        # 1. Cleanup old spinner if active
        if self._thinking_active:
            self.console.print("\x1b[2K\r", end="")
            self._thinking_active = False

        # 2. Thinking Block Rendering
        if is_thinking:
            # Handle the Header for the very first line of thinking
            if not self._has_printed_thinking_header:
                self.console.print("[bold green][MONK][/bold green] ", end="")
                self._has_printed_thinking_header = True

            # Print the line dimmed
            self.console.print(line, style="dim italic")
            return

        # 3. Code Block Toggles
        if line.strip().startswith("```"):
            if self._in_code_block:
                self._in_code_block = False
                self.console.print(line, style="dim")
            else:
                self._in_code_block = True
                lang = line.strip().lstrip("`")
                self._code_lang = lang if lang else "text"
                self.console.print(line, style="dim")
            return

        # 4. Content Rendering
        if self._in_code_block:
            syntax = Syntax(
                line,
                self._code_lang,
                theme="ansi_dark",
                word_wrap=False,
                padding=0,
                background_color="default",
            )
            self.console.print(syntax)
        else:
            safe_line = line.replace("<", "\\<")
            md = Markdown(safe_line)
            self.console.print(md)

    def render_tool_confirmation(self, tool_name: str, params: Dict[str, Any]):
        """
        Render tool confirmation prompt with context-aware formatting.
        This is the exact formatting logic from the old _on_tool_confirmation_requested.
        """
        # 1. Render Header
        self.console.print()
        self.console.print(
            f"[bold white][TOOL] PROPOSED ACTION: {tool_name}[/bold white]"
        )

        # 2. Context-Aware Rendering (Mapped to Schema)
        if tool_name == "execute_command":
            cmd = params.get("command", "")
            desc = params.get("description", "")
            self.console.print(f"Command:   [bold yellow]{cmd}[/bold yellow]")
            if desc:
                self.console.print(f"Reason:    [dim]{desc}[/dim]")

        elif tool_name == "read_file":
            path = params.get("filepath", "N/A")
            start = params.get("line_start")
            end = params.get("line_end")
            self.console.print(f"File:      [bold cyan]{path}[/bold cyan]")
            if start and end:
                self.console.print(f"Lines:     {start} - {end}")
            else:
                self.console.print(f"Lines:     [dim]All[/dim]")

        elif tool_name in ["create_file", "append_to_file"]:
            path = params.get("filepath", "N/A")
            content = params.get("content", "")
            scratch_id = params.get("content_from_scratch") or params.get(
                "content_from_memory"
            )
            self.console.print(f"File:      [bold cyan]{path}[/bold cyan]")
            self.console.print(
                f"Operation: [bold green]{tool_name.replace('_', ' ').title()}[/bold green]"
            )
            if scratch_id:
                self.console.print(
                    f"Source:    [yellow]Scratch Pad ({scratch_id})[/yellow]"
                )
            else:
                self.console.print(f"Size:      {len(content)} characters")

        elif tool_name == "replace_lines":
            path = params.get("filepath", "N/A")
            start = params.get("line_start", "?")
            end = params.get("line_end", "?")
            new_content = params.get("new_content", "")
            self.console.print(f"File:      [bold cyan]{path}[/bold cyan]")
            self.console.print(f"Target:    Lines {start} - {end}")
            preview = (
                (new_content[:75] + "...") if len(new_content) > 75 else new_content
            )
            self.console.print(f"Insert:    [green]{repr(preview)}[/green]")

        elif tool_name == "delete_lines":
            path = params.get("filepath", "N/A")
            start = params.get("line_start", "?")
            end = params.get("line_end", "?")
            self.console.print(f"File:      [bold cyan]{path}[/bold cyan]")
            self.console.print(f"Delete:    [red]Lines {start} - {end}[/red]")

        elif tool_name == "insert_in_file":
            path = params.get("filepath", "N/A")
            after = params.get("after_line", "")
            self.console.print(f"File:      [bold cyan]{path}[/bold cyan]")
            self.console.print(f"After:     [dim]{repr(after)}[/dim]")

        elif tool_name == "git_operation":
            op = params.get("operation", "unknown")
            msg = params.get("commit_message", "")
            self.console.print(f"Git Op:    [bold magenta]{op.upper()}[/bold magenta]")
            if msg and op == "commit":
                self.console.print(f"Message:   '{msg}'")

        elif tool_name == "run_python":
            name = params.get("script_name", "temp.py")
            content = params.get("script_content", "")
            self.console.print(f"Script:    [cyan]{name}[/cyan]")
            self.console.print(f"Size:      {len(content)} chars")

        else:
            for k, v in params.items():
                if (
                    k in ["content", "file_text", "script_content"]
                    and len(str(v)) > 200
                ):
                    v = f"<{len(str(v))} chars hidden>"
                self.console.print(f"{k}: {v}")

        self.console.print("-" * 50, style="dim")

    def render_tool_result(self, tool_name: str, result: ToolResult):
        """Render tool result output with indentation"""
        content = str(result.output) if hasattr(result, "output") else str(result)

        self.console.print(f"[bold white][TOOL] Result ({tool_name}):[/bold white]")
        # Indent slightly for readability
        for line in content.splitlines():
            self.console.print(f"  {line}", style="dim")

    def print_startup_banner(self):
        """Print the initial startup banner"""
        self.console.print(
            "[bold green]Protocol Monk EDA - PlainUI[/bold green]\n"
            "[dim]Standard Output Mode Active[/dim]"
        )

    def reset_thinking_state(self):
        """Reset thinking block state after response complete"""
        self._in_thinking_block = False
        self._has_printed_thinking_header = False

    def render_selection_list(self, title: str, items: list):
        """
        Render a selection list with numbered items.

        Args:
            title: Title for the list
            items: List of items to display (can be strings or objects with __str__)
        """
        self.console.print()
        self.console.print(f"[bold cyan]{title}[/bold cyan]")
        self.console.print("=" * len(title), style="dim")

        for idx, item in enumerate(items, 1):
            # Handle both string items and objects
            if hasattr(item, "name"):
                # ModelInfo objects have name attribute
                name = getattr(item, "name", str(item))
                context_window = getattr(item, "context_window", None)
                provider = getattr(item, "provider", None)

                if context_window and provider:
                    self.console.print(
                        f"  [bold white]{idx}.[/bold white] [cyan]{name}[/cyan] "
                        f"[dim]({provider}, {context_window:,} tokens)[/dim]"
                    )
                else:
                    self.console.print(
                        f"  [bold white]{idx}.[/bold white] [cyan]{name}[/cyan]"
                    )
            else:
                # Simple string items
                self.console.print(
                    f"  [bold white]{idx}.[/bold white] [cyan]{str(item)}[/cyan]"
                )

        self.console.print()

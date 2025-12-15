#!/usr/bin/env python3
"""
Rich UI Implementation - Orthodox Matrix Theme
"""

import asyncio
from rich.console import Group
from rich.live import Live
from typing import Any, Dict, List, Union

from prompt_toolkit import PromptSession
from prompt_toolkit.patch_stdout import patch_stdout

# --- IMPORTS ---
from .base import UI, ToolResult
from .renderers.message import render_agent_message, render_user_message
from .renderers.models import render_model_table, render_switch_report
from .renderers.streaming import generate_stream_panel
from .renderers.tools import render_tool_call_pretty, render_tool_result
from .stream_processor import StreamProcessor

# ADD: Import the new factory function
from .styles import console, create_monk_panel


class RichUI(UI):
    """Rich-enhanced UI with proper display sequencing."""

    def __init__(self):
        self._auto_confirm = False
        self._live_display = None
        self._streaming_active = False
        self._thinking_status = None
        self.processor = None
        # Unified Input Session with Unicode support
        from prompt_toolkit.output import create_output
        from prompt_toolkit.input import create_input
        
        # Ensure proper Unicode handling
        self.session = PromptSession(
            input=create_input(),
            output=create_output(),
            mouse_support=False,
            complete_while_typing=False
        )
    # --- 1. STREAMING ---

    def _start_streaming(self):
        """Start the live display for streaming responses."""
        self._stop_thinking()
        self._streaming_active = True

        self.processor = StreamProcessor()

        self._live_display = Live(
            generate_stream_panel("", False, 0),
            console=console,
            refresh_per_second=12,
            vertical_overflow="visible",
        )
        self._live_display.start()

    async def print_stream(self, text: str):
        if not self._streaming_active:
            self._start_streaming()

        self.processor.feed(text)
        self.processor.tick()

        visible_text, is_tool, tool_len = self.processor.get_view_data()

        if self._live_display:
            self._live_display.update(
                generate_stream_panel(visible_text, is_tool, tool_len)
            )

    def _end_streaming(self):
        if self._streaming_active and self._live_display:
            if self.processor:
                self.processor.flush()
                visible_text, is_tool, tool_len = self.processor.get_view_data()
                # Final update to ensure text completes
                self._live_display.update(
                    generate_stream_panel(visible_text, is_tool, tool_len)
                )

            self._streaming_active = False
            self._live_display.stop()
            self._live_display = None
            self.processor = None
            console.print()

    # --- 2. THINKING & STATUS ---

    async def start_thinking(self):
        """Display the thinking spinner."""
        self._end_streaming()
        if not self._thinking_status:
            self._thinking_status = console.status(
                "[success]Contemplating the Logos...[/]",
                spinner="dots",
                spinner_style="#ffaa44",  # Orthodox gold color
            )
            self._thinking_status.start()

    def _stop_thinking(self):
        if self._thinking_status:
            self._thinking_status.stop()
            self._thinking_status = None

    # --- 3. INPUT HANDLING (New) ---

    async def prompt_user(self, prompt: str) -> str:
        """Prompt user for input using prompt_toolkit inside Rich."""
        self._end_streaming()
        self._stop_thinking()

        # Display the prompt question nicely
        console.print()
        console.print(f"  [holy.gold]?[/] {prompt}")

        # Use prompt_toolkit with patch_stdout to play nice with async printing
        # Format: "  You › " (with Unicode fallback)
        
        # Check if terminal supports Unicode
        import sys
        try:
            # Test if we can encode the Orthodox cross
            '☦'.encode(sys.stdout.encoding or 'utf-8')
            prompt_symbol = '☦'
        except (UnicodeEncodeError, AttributeError):
            # Fallback to ASCII
            prompt_symbol = '>'
        
        pt_prompt = f"  {prompt_symbol}> "
        try:
            with patch_stdout():
                return await self.session.prompt_async(pt_prompt)
        except UnicodeEncodeError as e:
            # Fallback to simple ASCII prompt if Unicode fails
            console.print(f"[warning]Unicode prompt failed, falling back to ASCII: {e}[/]")
            fallback_prompt = "  > "
            return await self.session.prompt_async(fallback_prompt)
        except (KeyboardInterrupt, EOFError):
            return ""

    # --- 4. DELEGATED RENDERING ---

    async def confirm_tool_call(
        self, tool_call: Dict, auto_confirm: bool = False
    ) -> Union[bool, Dict]:
        self._end_streaming()
        self._stop_thinking()

        if auto_confirm or self._auto_confirm:
            return True

        # Render the full, safe confirmation screen
        render_tool_call_pretty(
            tool_call.get("action"), tool_call.get("parameters", {})
        )

        # Simple input for confirmation
        response = await self.prompt_user("Execute this action? [Y/n/m]")
        response = response.strip().lower()

        if response in ["y", "yes", ""]:
            console.print("  [success]✓ Approved[/]")
            return True
        elif response == "m":
            console.print()
            console.print(
                "  [dim white](Describe your suggestion in natural language)[/]"
            )
            suggestion = await self.prompt_user("Suggestion")

            if not suggestion.strip():
                return False

            return {
                "modified": {
                    "action": tool_call.get("action", ""),
                    "parameters": tool_call.get("parameters", {}),
                    "reasoning": tool_call.get("reasoning", ""),
                    "human_suggestion": suggestion,
                }
            }
        else:
            return False

    async def display_tool_result(self, result: ToolResult, tool_name: str):
        self._end_streaming()
        render_tool_result(tool_name, result.success, result.output)

    # --- 5. MODEL MANAGER RENDERERS ---

    async def display_model_list(self, models: List[Any], current_model: str):
        self._end_streaming()
        self._stop_thinking()
        render_model_table(models, current_model)

    async def display_switch_report(
        self, report: Any, current_model: str, target_model: str
    ):
        self._end_streaming()
        self._stop_thinking()
        render_switch_report(report, current_model, target_model)

    # --- 6. STANDARD OUTPUT ---

    async def print_error(self, message: str):
        self._end_streaming()
        console.print(f"[error]Error: {message}[/]")

    async def print_warning(self, message: str):
        self._end_streaming()
        console.print(f"[warning]Warning: {message}[/]")

    async def print_info(self, message: str):
        self._end_streaming()
        console.print(f"[monk.text]{message}[/]")

    async def display_tool_call(self, tool_call: Dict, auto_confirm: bool = False):
        pass

    async def display_execution_start(self, count: int):
        pass

    async def display_progress(self, current: int, total: int):
        pass

    async def display_task_complete(self, summary: str = ""):
        self._end_streaming()
        self._stop_thinking()
        from rich.text import Text
        from ui.styles import create_task_completion_panel

        content = Text(summary if summary else "Mission Complete.", style="monk.text")
        panel = create_task_completion_panel(content)
        console.print()
        console.print(panel)
        console.print()

    async def set_auto_confirm(self, value: bool):
        self._auto_confirm = value

    async def display_startup_banner(self, greeting: str):
        console.print(create_monk_panel(greeting, title="✠ Protocol Monk Online"))

    async def display_startup_frame(self, frame: str):
        pass

    async def print_error_stderr(self, message: str):
        pass

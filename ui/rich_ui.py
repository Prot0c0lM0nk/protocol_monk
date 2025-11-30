#!/usr/bin/env python3
"""
Rich UI Implementation - Orthodox Matrix Theme
"""

import asyncio
from rich.console import Group
from rich.live import Live
from typing import Any, Dict, List, Union

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
        """
        Display the thinking spinner.
        NOTE: We use internal logic here because it's non-blocking and persistent,
        unlike 'thinking.py' which is a fixed-duration pause.
        """
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

    # --- NEW: MODEL MANAGER RENDERERS ---

    async def display_model_list(self, models: List[Any], current_model: str):
        """Render a matrix-style table of available models."""
        self._end_streaming()
        self._stop_thinking()

        render_model_table(models, current_model)

    async def display_switch_report(
        self, report: Any, current_model: str, target_model: str
    ):
        """Render the Context Guardrail report."""
        self._end_streaming()
        self._stop_thinking()
        render_switch_report(report, current_model, target_model)
        if self._thinking_status:
            self._thinking_status.stop()
            self._thinking_status = None

    # --- 3. DELEGATED RENDERING ---
    # (Keep the rest of the methods as they were...)
    async def confirm_tool_call(
        self, tool_call: Dict, auto_confirm: bool = False
    ) -> Union[bool, Dict]:
        self._end_streaming()
        self._stop_thinking()

        if auto_confirm or self._auto_confirm:
            return True

        render_tool_call_pretty(
            tool_call.get("action"), tool_call.get("parameters", {})
        )

        # Prompt with available options like plain UI
        response = await asyncio.to_thread(
            console.input,
            "  [dim white]Execute this action?[/] [Y/n/m] (m = suggest modification) [holy.gold]›[/] ",
        )
        response = response.strip().lower()

        if response in ["y", "yes"]:
            console.print("  [success]✓ Approved[/]")
            return True
        elif response == "m":
            # Modify option - get human suggestion
            console.print()
            console.print(
                "  [holy.gold]What would you like to suggest to the model?[/]"
            )
            console.print(
                "  [dim white](Describe your suggestion in natural language)[/]"
            )
            suggestion = await asyncio.to_thread(
                console.input, "  [dim white]Suggestion[/] [holy.gold]›[/] "
            )

            if not suggestion.strip():
                return False

            # Return the suggestion as a modification request
            return {
                "modified": {
                    "action": tool_call.get("action", ""),
                    "parameters": tool_call.get("parameters", {}),
                    "reasoning": tool_call.get("reasoning", ""),
                    "human_suggestion": suggestion,
                }
            }
        else:
            # Handle 'n' and any other response as rejection
            return False

    async def display_tool_result(self, result: ToolResult, tool_name: str):
        self._end_streaming()
        render_tool_result(tool_name, result.success, result.output)

    async def print_error(self, message: str):
        self._end_streaming()
        console.print(f"[error]Error: {message}[/]")

    async def print_warning(self, message: str):
        self._end_streaming()
        console.print(f"[warning]Warning: {message}[/]")

    async def print_info(self, message: str):
        self._end_streaming()
        console.print(f"[monk.text]{message}[/]")

    async def prompt_user(self, prompt: str) -> str:
        self._end_streaming()
        self._stop_thinking()

        # FIX: Actually display the question!
        console.print()
        console.print(f"  [holy.gold]?[/] {prompt}")

        # Then show the input cursor
        return await asyncio.to_thread(
            console.input, f"  [dim white]You[/] [holy.gold]›[/] "
        )

    async def display_tool_call(self, tool_call: Dict, auto_confirm: bool = False):
        pass

    async def display_execution_start(self, count: int):
        pass

    async def display_progress(self, current: int, total: int):
        pass

    async def display_task_complete(self, summary: str = ""):
        self._end_streaming()
        self._stop_thinking()

        # Create a nice summary panel
        from rich.console import Group
        from rich.text import Text

        from ui.styles import console, create_monk_panel, create_task_completion_panel

        # If the summary is a JSON-like string or complex, we could parse it here.
        # For now, we assume 'summary' contains the text message from the finish tool.
        content = Text(summary if summary else "Mission Complete.", style="monk.text")

        # Use the task completion panel factory function
        panel = create_task_completion_panel(content)
        console.print()
        console.print(panel)
        console.print()
        console.print()

    async def set_auto_confirm(self, value: bool):
        self._auto_confirm = value

    async def display_startup_banner(self, greeting: str):
        # Use the factory, but maybe override the title for the banner
        console.print(create_monk_panel(greeting, title="✠ Protocol Monk Online"))

    async def display_startup_frame(self, frame: str):
        pass

    async def print_error_stderr(self, message: str):
        pass

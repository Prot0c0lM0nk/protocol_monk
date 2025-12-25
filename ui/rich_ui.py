#!/usr/bin/env python3
"""
Rich UI Implementation - Orthodox Matrix Theme
"""

import asyncio
import logging
from rich.console import Group
from rich.live import Live
from typing import Any, Dict, List, Union

from prompt_toolkit import PromptSession
from prompt_toolkit.patch_stdout import patch_stdout

# --- IMPORTS ---
from .base import UI, ToolResult
from .renderers.message import render_agent_message, render_user_message, clean_think_tags
from .renderers.models import render_model_table, render_switch_report
from .renderers.streaming import generate_stream_panel
from .renderers.tools import render_tool_call_pretty, render_tool_result
# ADD: Import the think tag cleanser

# ADD: Import the new factory function
from .styles import console, create_monk_panel


class RichUI(UI):
    """Rich-enhanced UI with proper display sequencing."""

    def __init__(self):
        super().__init__()  # Initialize base UI with thread safety
        self._auto_confirm = False
        self._live_display = None
        self._streaming_active = False
        self._thinking_status = None
        self._accumulated_text = (
            ""  # Store accumulated streaming content like StreamProcessor
        )
        self._state_lock: asyncio.Lock = (
            asyncio.Lock()
        )  # Additional state lock for RichUI-specific operations
        from prompt_toolkit.output import create_output
        from prompt_toolkit.input import create_input

        # Ensure proper Unicode handling
        self.session = PromptSession(
            input=create_input(),
            output=create_output(),
            mouse_support=False,
            complete_while_typing=False,
        )

    # --- 1. STREAMING ---

    def _start_streaming(self):
        """Start the live display for streaming responses with scrollback protection."""
        self._stop_thinking()
        self._streaming_active = True


        # CRITICAL FIX: Enhanced Live display configuration to prevent artifacts
        # transient=False: Live display stays visible on exit (no panel transition artifacts)
        # refresh_per_second=6: Increased for smoother animation
        # vertical_overflow="visible": Panel stays visible, so show full content
        # NO fixed width constraints - panels now adapt to terminal width
        self._live_display = Live(
            generate_stream_panel(""),
            console=console,
            refresh_per_second=6,  # Increased for smoother animation
            vertical_overflow="visible",  # Show full content since panel stays visible
            transient=False,  # Panel stays visible on exit (no transition artifacts)
            redirect_stdout=False,  # Prevent stdout interference
            redirect_stderr=False,  # Prevent stderr interference
        )
        self._live_display.start()

    async def print_stream(self, text: str):
        if not self._streaming_active:
            self._start_streaming()

        try:
            # Simply accumulate and display (no tool detection needed)
            if len(text) > 0:
                self._accumulated_text += text
                
                # Clean think tags for display
                display_content = clean_think_tags(self._accumulated_text)
                
                # Update display if there's content
                if display_content.strip() and self._live_display:
                    self._live_display.update(
                        generate_stream_panel(display_content)
                    )
        except asyncio.CancelledError:
            # Handle cancellation gracefully
            self._streaming_active = False
            if self._live_display:
                try:
                    self._live_display.stop()
                except Exception:
                    pass
                self._live_display = None
        except Exception as e:
            await self.print_error(f"Stream processing error: {e}")
                
    async def _end_streaming(self):
        """End streaming safely - panel stays visible with transient=False."""
        if not self._streaming_active:
            return

        if self._live_display:
            # With transient=False, the panel stays visible
            # Just need to ensure clean cursor positioning
            try:
                # Move cursor to a new blank line after the panel
                console.print("\n")
            except Exception:
                pass  # Best effort only

            # Stop the live display (panel remains visible)
            try:
                self._live_display.stop()
            except Exception as e:
                logging.getLogger(__name__).warning(f"Error stopping live display: {e}")

            self._live_display = None

        self._accumulated_text = ""
        self._streaming_active = False

    async def start_thinking(self):
        """Display the thinking spinner."""
        await self._end_streaming()
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

    async def stop_thinking(self):
        """Public method to stop the thinking spinner."""
        self._stop_thinking()

    # --- 3. INPUT HANDLING (New) ---

    async def prompt_user(self, prompt: str) -> str:
        """Prompt user for input using prompt_toolkit inside Rich."""
        await self._end_streaming()
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
            "☦".encode(sys.stdout.encoding or "utf-8")
            prompt_symbol = "☦"
        except (UnicodeEncodeError, AttributeError):
            # Fallback to ASCII
            prompt_symbol = ">"

        pt_prompt = f"  {prompt_symbol}> "
        try:
            with patch_stdout():
                return await self.session.prompt_async(pt_prompt)
        except UnicodeEncodeError as e:
            # Fallback to simple ASCII prompt if Unicode fails
            console.print(
                f"[warning]Unicode prompt failed, falling back to ASCII: {e}[/]"
            )
            fallback_prompt = "  > "
            return await self.session.prompt_async(fallback_prompt)
        except (KeyboardInterrupt, EOFError):
            return ""

    # --- 4. DELEGATED RENDERING ---

    async def confirm_tool_call(
        self, tool_call: Dict, auto_confirm: bool = False
    ) -> Union[bool, Dict]:
        await self._end_streaming()
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
        await self._end_streaming()
        render_tool_result(tool_name, result.success, result.output)

    # --- 5. MODEL MANAGER RENDERERS ---

    async def display_model_list(self, models: List[Any], current_model: str):
        await self._end_streaming()
        self._stop_thinking()
        render_model_table(models, current_model)

    async def display_switch_report(
        self, report: Any, current_model: str, target_model: str
    ):
        await self._end_streaming()
        self._stop_thinking()
        render_switch_report(report, current_model, target_model)

    # --- 6. STANDARD OUTPUT ---

    async def print_error(self, message: str):
        await self._end_streaming()
        self._stop_thinking()
        console.print(f"[error]Error: {message}[/]")

    async def print_warning(self, message: str):
        await self._end_streaming()
        console.print(f"[warning]Warning: {message}[/]")

    async def print_info(self, message: str):
        await self._end_streaming()
        console.print(f"[monk.text]{message}[/]")

    async def display_tool_call(self, tool_call: Dict, auto_confirm: bool = False):
        """Display tool call using Rich renderer"""
        from .renderers.tools import render_tool_call_pretty
        
        action = tool_call.get("action", "unknown")
        params = tool_call.get("parameters", {})
        
        # Use the Rich renderer to display the tool call
        render_tool_call_pretty(action, params)

    async def display_execution_start(self, count: int):
        """Display execution start notification using Rich"""
        from rich.panel import Panel
        from rich.text import Text
        
        message = Text(f"Executing {count} tool(s)...", style="bold green")
        panel = Panel(message, border_style="green")
        console.print(panel)

    async def display_progress(self, current: int, total: int):
        """Display progress using Rich progress bar"""
        from rich.progress import ProgressBar
        
        if not hasattr(self, "_progress_bar"):
            self._progress_bar = ProgressBar(total=total, width=50)
        
        self._progress_bar.update(current)
        console.print(self._progress_bar)

    async def display_task_complete(self, summary: str = ""):
        await self._end_streaming()
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
        """Display startup frame using Rich"""
        from rich.panel import Panel
        
        console.print(Panel(frame, border_style="dim"))

    async def print_error_stderr(self, message: str):
        """Print error to stderr using Rich"""
        from rich.panel import Panel
        from rich.text import Text
        
        error_panel = Panel(
            Text(message, style="red"),
            title="[bold red]Error[/]",
            border_style="red"
        )
        console.print(error_panel, stderr=True)

    async def close(self):
        """Clean up all UI resources including live displays and thinking status."""
        logger = logging.getLogger(__name__)
        try:
            # Stop any active streaming first (with timeout protection)
            await self._end_streaming()
            # Stop thinking status if active
            self._stop_thinking()
            logger.debug("RichUI resources cleaned up successfully")
        except asyncio.CancelledError:
            # Handle cancellation gracefully - still try to clean up what we can
            logger.warning("RichUI cleanup cancelled, performing best-effort cleanup")
            self._stop_thinking()
            raise  # Re-raise the cancellation
        except Exception as e:
            logger.error(f"Error during RichUI cleanup: {e}", exc_info=True)
            raise
            

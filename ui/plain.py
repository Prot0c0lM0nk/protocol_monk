#!/usr/bin/env python3
"""
ui/plain.py - Event-Driven Plain CLI for Protocol Monk EDA

Purpose: Professional "Standard Output" interface.
- "Flat" text blocks for tools (No panels/boxes).
- Ephemeral "Thinking..." indicator.
- Strict [TAG] prefixes ([USER], [SYS], [MONK], [TOOL]).
- Event-driven architecture with background input handling.
"""

import asyncio
import re
from typing import Any, Dict, List, Optional
from datetime import datetime

from prompt_toolkit import PromptSession
from prompt_toolkit.patch_stdout import patch_stdout
from prompt_toolkit.formatted_text import HTML
from rich.console import Console
from rich.markdown import Markdown
from rich.syntax import Syntax

from ui.base import UI, ToolResult
from agent.events import AgentEvents, get_event_bus


class PlainUI(UI):
    """
    Event-Driven Plain CLI - Standard Output Aesthetic
    """

    def __init__(self):
        super().__init__()
        self.auto_confirm = False
        self._thinking = False
        self._event_bus = get_event_bus()
        self.session = PromptSession()
        self._lock: asyncio.Lock = asyncio.Lock()

        # NEW: Robust Line Buffer
        self._stream_line_buffer = ""

        # NEW: Track code block state
        self._in_code_block = False
        self._code_lang = "text"

        # Traffic Controller State
        self.pending_confirmation: Optional[Dict[str, Any]] = None

        # Buffer for markdown processing
        self._response_buffer = ""
        self._in_markdown_block = False

        # Initialize Rich Console (Force terminal for colors, but keep layout plain)
        self.console = Console(
            force_terminal=True, color_system="truecolor", highlight=False
        )
        self._setup_event_listeners()

    def _setup_event_listeners(self):
        """Subscribe to all agent events"""
        # Core agent events
        self._event_bus.subscribe(AgentEvents.ERROR.value, self._on_agent_error)
        self._event_bus.subscribe(AgentEvents.WARNING.value, self._on_agent_warning)
        self._event_bus.subscribe(AgentEvents.INFO.value, self._on_agent_info)

        # Thinking events
        self._event_bus.subscribe(
            AgentEvents.THINKING_STARTED.value, self._on_thinking_started
        )
        self._event_bus.subscribe(
            AgentEvents.THINKING_STOPPED.value, self._on_thinking_stopped
        )

        # Tool execution events
        self._event_bus.subscribe(
            AgentEvents.TOOL_EXECUTION_START.value, self._on_tool_start
        )
        self._event_bus.subscribe(
            AgentEvents.TOOL_EXECUTION_PROGRESS.value, self._on_tool_progress
        )
        self._event_bus.subscribe(
            AgentEvents.TOOL_EXECUTION_COMPLETE.value, self._on_tool_complete
        )
        self._event_bus.subscribe(AgentEvents.TOOL_ERROR.value, self._on_tool_error)
        self._event_bus.subscribe(AgentEvents.TOOL_RESULT.value, self._on_tool_result)

        # Tool Confirmation
        self._event_bus.subscribe(
            AgentEvents.TOOL_CONFIRMATION_REQUESTED.value,
            self._on_tool_confirmation_requested,
        )

        # Stream events
        self._event_bus.subscribe(AgentEvents.STREAM_CHUNK.value, self._on_stream_chunk)
        self._event_bus.subscribe(
            AgentEvents.RESPONSE_COMPLETE.value, self._on_response_complete
        )

        # Context events
        self._event_bus.subscribe(
            AgentEvents.CONTEXT_OVERFLOW.value, self._on_context_overflow
        )
        self._event_bus.subscribe(
            AgentEvents.MODEL_SWITCHED.value, self._on_model_switched
        )
        self._event_bus.subscribe(
            AgentEvents.PROVIDER_SWITCHED.value, self._on_provider_switched
        )

        # Status events
        self._event_bus.subscribe(
            AgentEvents.COMMAND_RESULT.value, self._on_command_result
        )
        self._event_bus.subscribe(
            AgentEvents.STATUS_CHANGED.value, self._on_status_changed
        )

    # --- Tool Confirmation Logic ---
    async def _on_tool_confirmation_requested(self, data: Dict[str, Any]):
        """
        Handle tool approval requests using a Flat Text Block.
        Spawns background task for input to keep Event Bus free.
        """
        tool_call = data.get("tool_call", {})
        tool_call_id = data.get("tool_call_id")
        tool_name = tool_call.get("action", "Unknown Tool")
        params = tool_call.get("parameters", {})

        # Extract common parameters for cleaner display
        path = params.get("path", params.get("filename", "N/A"))
        command = params.get("command", params.get("operation", "execute"))

        # Determine lines if available
        lines = "N/A"
        if "start_line" in params and "end_line" in params:
            lines = f"{params['start_line']} - {params['end_line']}"
        elif "line" in params:
            lines = str(params["line"])

        # Render the Flat Block
        self.console.print()
        self.console.print("[bold white][TOOL] PROPOSED ACTION[/bold white]")
        self.console.print(f"Tool:      [cyan]{tool_name}[/cyan]")
        self.console.print(f"Path:      [yellow]{path}[/yellow]")
        self.console.print(f"Command:   [yellow]{command}[/yellow]")
        if lines != "N/A":
            self.console.print(f"Lines:     {lines}")

        self.console.print("-" * 50, style="dim")

        # Spawn background task
        asyncio.create_task(self._get_confirmation_input(tool_call_id, tool_name))

    async def _get_confirmation_input(self, tool_call_id: str, tool_name: str):
        """
        Background input loop for confirmation.
        """
        await asyncio.sleep(0.1)  # Allow render to finish

        try:
            # Using prompt_user for consistent styling
            # The prompt_user method handles the [SYS] tag
            response = await self.prompt_user("Approve execution? (y/n)")
            approved = response.lower().startswith("y")
        except Exception as e:
            self.console.print(f"[bold red][ERR] Input Error: {e}[/bold red]")
            approved = False

        # Feedback
        if approved:
            self.console.print(f"[bold green]✓ Approved {tool_name}[/bold green]")
        else:
            self.console.print(f"[bold red]✗ Rejected {tool_name}[/bold red]")

        # Send result
        await self._event_bus.emit(
            "ui.tool_confirmation", {"tool_call_id": tool_call_id, "approved": approved}
        )

    # --- Event Handler Methods ---
    async def _on_agent_error(self, data: Dict[str, Any]):
        message = data.get("message", "Unknown error")
        self.console.print(f"[bold red][ERR] {message}[/bold red]")

    async def _on_agent_warning(self, data: Dict[str, Any]):
        message = data.get("message", "Unknown warning")
        self.console.print(f"[bold yellow][WARN] {message}[/bold yellow]")

    async def _on_agent_info(self, data: Dict[str, Any]):
        message = data.get("message", "Info message")
        payload = data.get("data")

        if message.strip():
            self.console.print(f"[bold blue][SYS] {message}[/bold blue]")

        if payload and isinstance(payload, list):
            self._display_info_list(payload)

    async def _on_thinking_started(self, data: Dict[str, Any]):
        message = data.get("message", "Thinking...")
        await self.start_thinking(message)

    async def _on_thinking_stopped(self, data: Dict[str, Any]):
        await self.stop_thinking()

    async def _on_tool_start(self, data: Dict[str, Any]):
        if "tools" in data and isinstance(data["tools"], list):
            names = ", ".join(data["tools"])
            self.console.print(f"[dim][SYS] Executing: {names}...[/dim]")
        else:
            tool_name = data.get("tool_name", "Unknown tool")
            self.console.print(f"[dim][SYS] Executing: {tool_name}...[/dim]")

    async def _on_tool_progress(self, data: Dict[str, Any]):
        # User Feedback: This is usually noise. Silenced.
        pass

    async def _on_tool_complete(self, data: Dict[str, Any]):
        # Minimal noise on completion, specific results handled by _on_tool_result
        pass

    async def _on_tool_error(self, data: Dict[str, Any]):
        tool_name = data.get("tool_name", "Unknown tool")
        error = data.get("error", "Unknown error")
        self.console.print(f"[bold red][TOOL] Error ({tool_name}): {error}[/bold red]")

    async def _on_tool_result(self, data: Dict[str, Any]):
        result = data.get("result", "")
        tool_name = data.get("tool_name", "Unknown tool")
        await self._display_tool_result_markdown(tool_name, result)

    async def _on_stream_chunk(self, data: Dict[str, Any]):
        chunk = data.get("chunk", "")
        
        # Append to buffer safely (asyncio is single-threaded)
        self._stream_line_buffer += chunk

        # Process all complete lines immediately
        while "\n" in self._stream_line_buffer:
            line, self._stream_line_buffer = self._stream_line_buffer.split("\n", 1)
            await self._print_markdown_line(line)

    async def _on_response_complete(self, data: Dict[str, Any]):
        # Flush any remaining text in the buffer (e.g. text without final newline)
        if self._stream_line_buffer:
            await self._print_markdown_line(self._stream_line_buffer)
            self._stream_line_buffer = ""
        
        # Print a final newline to separate from the next prompt
        self.console.print()

    async def _print_markdown_line(self, line: str):
        """Render a single line, handling code blocks with tighter spacing"""
        async with self._lock:
            # 1. Handle Thinking Cleanup
            if self._thinking:
                self.console.print("\x1b[2K\r", end="")
                self.console.print("[bold green][MONK][/bold green] ", end="")
                self._thinking = False

            # 2. Check for Code Block Toggles
            if line.strip().startswith("```"):
                if self._in_code_block:
                    # Closing the block
                    self._in_code_block = False
                    # Print the closing fence dimly
                    self.console.print(line, style="dim")
                else:
                    # Opening the block
                    self._in_code_block = True
                    # Extract language if present (e.g. ```python -> python)
                    lang = line.strip().lstrip("`")
                    self._code_lang = lang if lang else "text"
                    # Print the opening fence dimly
                    self.console.print(line, style="dim")
                return

            # 3. Render Content
            if self._in_code_block:
                # CODE MODE: Use Syntax to highlight, but print directly to avoid margins
                # We use 'background_color="default"' to prevent "striping" artifacts
                syntax = Syntax(
                    line, 
                    self._code_lang, 
                    theme="ansi_dark",  # Uses terminal colors (safe)
                    word_wrap=False,
                    padding=0,
                    background_color="default"
                )
                self.console.print(syntax)
            else:
                # TEXT MODE: Render Markdown
                # Note: Single lines of text will still have small margins, 
                # but this is acceptable for prose.
                md = Markdown(line)
                self.console.print(md)

    async def _on_context_overflow(self, data: Dict[str, Any]):
        current = data.get("current_tokens", 0)
        max_t = data.get("max_tokens", 0)
        self.console.print(
            f"[bold yellow][WARN] Context: {current}/{max_t}[/bold yellow]"
        )

    async def _on_model_switched(self, data: Dict[str, Any]):
        self.console.print(
            f"[bold blue][SYS] Model: {data.get('old_model')} → {data.get('new_model')}[/bold blue]"
        )

    async def _on_provider_switched(self, data: Dict[str, Any]):
        self.console.print(
            f"[bold blue][SYS] Provider: {data.get('old_provider')} → {data.get('new_provider')}[/bold blue]"
        )

    async def _on_command_result(self, data: Dict[str, Any]):
        success = data.get("success", True)
        message = data.get("message", "")

        if not message:
            return

        if success:
            await self.print_info(message)
        else:
            await self.print_error(message)

    async def _on_status_changed(self, data: Dict[str, Any]):
        pass

    # --- Display Logic ---

    async def _display_tool_result_markdown(self, tool_name: str, result: Any):
        """Display tool result as clean text"""
        content = str(result.output) if hasattr(result, "output") else str(result)

        self.console.print(f"[bold white][TOOL] Result ({tool_name}):[/bold white]")
        # Indent slightly for readability
        for line in content.splitlines():
            self.console.print(f"  {line}", style="dim")

    async def print_stream(self, text: str):
        """Stream text, handling the ephemeral thinking state"""
        async with self._lock:
            if self._thinking:
                # FIX: Use ANSI \x1b[2K to clear the WHOLE line properly, then \r
                self.console.print("\x1b[2K\r", end="")
                self._thinking = False
                
                # Print the MONK tag once at the start
                self.console.print("[bold green][MONK][/bold green] ", end="")

            self.console.print(text, end="", highlight=False)

    async def start_thinking(self, message: str = "Thinking..."):
        async with self._lock:
            self._thinking = True
            # FIX: Changed magenta to green to match the response tag
            self.console.print(
                f"\n[bold green][MONK][/bold green] {message}", end="\r"
            )

    async def stop_thinking(self):
        async with self._lock:
            if self._thinking:
                # Clear the line
                self.console.print("\r" + " " * 50 + "\r", end="")
                self._thinking = False

    async def prompt_user(self, prompt: str) -> str:
        """Prompt user with standard output styling"""
        async with self._lock:
            is_main_loop = prompt == "" or prompt.strip() == ">>>"

            if is_main_loop:
                # White (default) label for Main User Input
                label = HTML("\nUSER &gt; ")
            else:
                # FIX: Changed fg='blue' to fg='ansibrightblack' to match the [dim] style
                # of the other system logs.
                clean_prompt = prompt.rstrip(" :>")
                label = HTML(f"\n<style fg='ansibrightblack'>[SYS] {clean_prompt}</style> &gt; ")

            try:
                with patch_stdout():
                    return await self.session.prompt_async(label)
            except (KeyboardInterrupt, EOFError):
                self.console.print("\n[dim]Cancelled.[/dim]")
                return ""

    def _display_info_list(self, items: List[Any]):
        """Render a numbered list cleanly"""
        for i, item in enumerate(items, 1):
            if isinstance(item, dict):
                name = item.get("name", str(item))
                extra = f" ({item.get('provider')})" if item.get("provider") else ""
                self.console.print(f"  {i}. [cyan]{name}[/cyan][dim]{extra}[/dim]")
            else:
                self.console.print(f"  {i}. [cyan]{item}[/cyan]")

    async def display_selection_list(self, title: str, items: List[Any]) -> Any:
        """Interactive selection list if requested by agent"""
        self.console.print(f"\n[bold blue][SYS] {title}[/bold blue]")
        self._display_info_list(items)

        while True:
            # Local input loop for selection
            self.console.print("[bold blue][SYS] Select #[/bold blue] > ", end="")
            try:
                with patch_stdout():
                    choice = await self.session.prompt_async("")

                index = int(choice) - 1
                if 0 <= index < len(items):
                    return items[index]
            except ValueError:
                pass
            except (KeyboardInterrupt, EOFError):
                return None

            self.console.print("[red]Invalid selection[/red]")

    # --- Boilerplate Implementations ---
    async def confirm_action(self, message: str) -> bool:
        response = await self.prompt_user(f"{message} (y/n)")
        return response.lower().startswith("y")

    async def display_tool_result(self, result: ToolResult):
        await self._display_tool_result_markdown(
            result.tool_name or "Tool", result.output
        )

    async def get_input(self) -> str:
        # Main loop calls this with empty prompt
        return await self.prompt_user("")

    async def print_error(self, message: str):
        self.console.print(f"[bold red][ERR] {message}[/bold red]")

    async def print_info(self, message: str):
        self.console.print(f"[bold blue][SYS] {message}[/bold blue]")

    async def run_async(self):
        """Main UI Loop"""
        self.console.print(
            "[bold green]Protocol Monk EDA - PlainUI[/bold green]\n"
            "[dim]Standard Output Mode Active[/dim]"
        )

        try:
            while True:
                user_input = await self.get_input()

                if not user_input.strip():
                    continue

                if self.pending_confirmation:
                    await self._handle_pending_confirmation(user_input)
                    continue

                await self._event_bus.emit(
                    AgentEvents.COMMAND_RESULT.value,
                    {"input": user_input, "timestamp": datetime.now().isoformat()},
                )

        except KeyboardInterrupt:
            self.console.print("\n[bold red]Shutting down...[/bold red]")

    async def _handle_pending_confirmation(self, user_input: str):
        # Fallback if manual confirmation handling is needed outside the background task
        # (Usually handled by _get_confirmation_input, but kept for safety)
        data = self.pending_confirmation
        tool_call_id = data["tool_call_id"]
        approved = user_input.lower().startswith("y")

        await self._event_bus.emit(
            "ui.tool_confirmation", {"tool_call_id": tool_call_id, "approved": approved}
        )
        self.pending_confirmation = None


def create_plain_ui() -> PlainUI:
    return PlainUI()

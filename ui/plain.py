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
        
        # Concurrency Flags
        self._is_prompt_active = False
        self._agent_is_busy = False 

        # NEW: Track thinking block state
        self._in_thinking_block = False
        self._has_printed_thinking_header = False  # Track if [MONK] header is visible

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
        # Flush pending stream text
        await self._flush_stream_buffer()
        
        """
        Handle tool approval requests using Exact Schema Keys.
        """
        tool_call = data.get("tool_call", {})
        tool_call_id = data.get("tool_call_id")
        tool_name = tool_call.get("action", "Unknown Tool")
        params = tool_call.get("parameters", {})

        # Use lock only for printing, release before input
        async with self._lock:
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
                scratch_id = params.get("content_from_scratch") or params.get("content_from_memory")
                self.console.print(f"File:      [bold cyan]{path}[/bold cyan]")
                self.console.print(
                    f"Operation: [bold green]{tool_name.replace('_', ' ').title()}[/bold green]"
                )
                if scratch_id:
                    self.console.print(f"Source:    [yellow]Scratch Pad ({scratch_id})[/yellow]")
                else:
                    self.console.print(f"Size:      {len(content)} characters")

            elif tool_name == "replace_lines":
                path = params.get("filepath", "N/A")
                start = params.get("line_start", "?")
                end = params.get("line_end", "?")
                new_content = params.get("new_content", "")
                self.console.print(f"File:      [bold cyan]{path}[/bold cyan]")
                self.console.print(f"Target:    Lines {start} - {end}")
                preview = (new_content[:75] + "...") if len(new_content) > 75 else new_content
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
                    if k in ["content", "file_text", "script_content"] and len(str(v)) > 200:
                        v = f"<{len(str(v))} chars hidden>"
                    self.console.print(f"{k}: {v}")

            self.console.print("-" * 50, style="dim")

        # Spawn background task for user input
        # NOTE: We set pending_confirmation so run_async loop knows not to overlap prompts
        self.pending_confirmation = {"tool_call_id": tool_call_id, "tool_name": tool_name}
        asyncio.create_task(self._get_confirmation_input(tool_call_id, tool_name))

    async def _get_confirmation_input(self, tool_call_id: str, tool_name: str):
        """
        Background input loop for confirmation.
        """
        await asyncio.sleep(0.1)  # Allow render to finish

        try:
            # Using prompt_user for consistent styling
            # prompt_user releases lock while waiting, so events can still flow
            response = await self.prompt_user("Approve execution? (y/n)")
            approved = response.lower().startswith("y")
        except Exception as e:
            async with self._lock:
                self.console.print(f"[bold red][ERR] Input Error: {e}[/bold red]")
            approved = False

        # Feedback
        async with self._lock:
            if approved:
                self.console.print(f"[bold green]✓ Approved {tool_name}[/bold green]")
            else:
                self.console.print(f"[bold red]✗ Rejected {tool_name}[/bold red]")

        # Clear pending state
        self.pending_confirmation = None

        # Send result
        await self._event_bus.emit(
            "ui.tool_confirmation", {"tool_call_id": tool_call_id, "approved": approved}
        )

    # --- Event Handler Methods ---
    async def _on_agent_error(self, data: Dict[str, Any]):
        message = data.get("message", "Unknown error")
        async with self._lock:
            self.console.print(f"[bold red][ERR] {message}[/bold red]")

    async def _on_agent_warning(self, data: Dict[str, Any]):
        message = data.get("message", "Unknown warning")
        async with self._lock:
            self.console.print(f"[bold yellow][WARN] {message}[/bold yellow]")

    async def _on_agent_info(self, data: Dict[str, Any]):
        message = data.get("message", "Info message")
        payload = data.get("data")

        async with self._lock:
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
        await self._flush_stream_buffer()
        async with self._lock:
            if "tools" in data and isinstance(data["tools"], list):
                names = ", ".join(data["tools"])
                self.console.print(f"[dim][SYS] Executing: {names}...[/dim]")
            else:
                tool_name = data.get("tool_name", "Unknown tool")
                self.console.print(f"[dim][SYS] Executing: {tool_name}...[/dim]")

    async def _on_tool_progress(self, data: Dict[str, Any]):
        pass

    async def _on_tool_complete(self, data: Dict[str, Any]):
        pass

    async def _on_tool_error(self, data: Dict[str, Any]):
        tool_name = data.get("tool_name", "Unknown tool")
        error = data.get("error", "Unknown error")
        async with self._lock:
            self.console.print(f"[bold red][TOOL] Error ({tool_name}): {error}[/bold red]")

    async def _on_tool_result(self, data: Dict[str, Any]):
        result = data.get("result", "")
        tool_name = data.get("tool_name", "Unknown tool")
        await self._display_tool_result_markdown(tool_name, result)

    async def _on_stream_chunk(self, data: Dict[str, Any]):
        async with self._lock:
            thinking_chunk = data.get("thinking")
            answer_chunk = data.get("chunk", "")

            if thinking_chunk:
                self._in_thinking_block = True
                self._stream_line_buffer += thinking_chunk
            elif answer_chunk:
                # If we were thinking, we are strictly NOT anymore
                if self._in_thinking_block:
                    if self._stream_line_buffer:
                        self._render_line(self._stream_line_buffer, is_thinking=True)
                        self._stream_line_buffer = ""
                    
                    self.console.print()
                    self._in_thinking_block = False
                    self._has_printed_thinking_header = False

                self._stream_line_buffer += answer_chunk

            # Process complete lines
            while "\n" in self._stream_line_buffer:
                line, self._stream_line_buffer = self._stream_line_buffer.split("\n", 1)
                self._render_line(line, is_thinking=self._in_thinking_block)

    async def _on_response_complete(self, data: Dict[str, Any]):
        if self._stream_line_buffer:
            await self._print_stream_line(
                self._stream_line_buffer, is_thinking=self._in_thinking_block
            )
            self._stream_line_buffer = ""

        # Reset states
        async with self._lock:
            self.console.print()
            self._in_thinking_block = False
            self._has_printed_thinking_header = False
            self._agent_is_busy = False # Response done, agent is idle

    def _render_line(self, line: str, is_thinking: bool = False):
        """
        Internal render logic. Assumes self._lock is ALREADY held.
        """
        # 1. Cleanup old spinner if active
        if self._thinking:
            self.console.print("\x1b[2K\r", end="")
            self._thinking = False

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

    async def _flush_stream_buffer(self):
        """Force print any remaining text in the buffer."""
        async with self._lock:
            if self._stream_line_buffer:
                self._render_line(self._stream_line_buffer, is_thinking=self._in_thinking_block)
                self._stream_line_buffer = ""
                
                if self._in_thinking_block:
                    self.console.print()
                    self._in_thinking_block = False
                    self._has_printed_thinking_header = False

    async def _print_stream_line(self, line: str, is_thinking: bool = False):
        """Public wrapper that acquires the lock"""
        async with self._lock:
            self._render_line(line, is_thinking)

    async def _on_context_overflow(self, data: Dict[str, Any]):
        current = data.get("current_tokens", 0)
        max_t = data.get("max_tokens", 0)
        async with self._lock:
            self.console.print(
                f"[bold yellow][WARN] Context: {current}/{max_t}[/bold yellow]"
            )

    async def _on_model_switched(self, data: Dict[str, Any]):
        async with self._lock:
            self.console.print(
                f"[bold blue][SYS] Model: {data.get('old_model')} → {data.get('new_model')}[/bold blue]"
            )

    async def _on_provider_switched(self, data: Dict[str, Any]):
        async with self._lock:
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
        
        async with self._lock:
            self.console.print(f"[bold white][TOOL] Result ({tool_name}):[/bold white]")
            # Indent slightly for readability
            for line in content.splitlines():
                self.console.print(f"  {line}", style="dim")

    async def print_stream(self, text: str):
        """Stream text, handling the ephemeral thinking state"""
        async with self._lock:
            if self._thinking:
                self.console.print("\x1b[2K\r", end="")
                self._thinking = False
                self.console.print("[bold green][MONK][/bold green] ", end="")

            self.console.print(text, end="", highlight=False)

    async def start_thinking(self, message: str = "Thinking..."):
        async with self._lock:
            self._thinking = True
            # Print newline first to ensure clean start
            self.console.print(f"\n[bold green][MONK][/bold green] {message}", end="\r")

    async def stop_thinking(self):
        async with self._lock:
            if self._thinking:
                self.console.print("\x1b[2K\r", end="")
                self._thinking = False

    async def prompt_user(self, prompt: str) -> str:
        """Prompt user with standard output styling"""
        # 1. Prepare Label (Needs Lock)
        async with self._lock:
            is_main_loop = prompt == "" or prompt.strip() == ">>>"
            
            if is_main_loop:
                # If we are in "Main Loop" mode, but we have a pending confirmation,
                # we should NOT show the prompt yet. Return empty to spin the loop.
                if self.pending_confirmation is not None:
                    return ""
                
                label = HTML("\nUSER &gt; ")
            else:
                clean_prompt = prompt.rstrip(" :>")
                label = HTML(
                    f"\n<style fg='ansibrightblack'>[SYS] {clean_prompt}</style> &gt; "
                )
            
            # Mark prompt active so we don't double-render
            if self._is_prompt_active:
                 # Already prompting? This shouldn't happen with proper control flow, 
                 # but if it does, fallback
                 return ""
            self._is_prompt_active = True

        # 2. Wait for Input (RELEASE LOCK)
        # We release the lock here so background events (tool results, logs)
        # can print to the console via patch_stdout while we wait for user.
        try:
            with patch_stdout():
                return await self.session.prompt_async(label)
        except (KeyboardInterrupt, EOFError):
            async with self._lock:
                self.console.print("\n[dim]Cancelled.[/dim]")
            return ""
        finally:
            # Re-acquire lock to update state
            async with self._lock:
                self._is_prompt_active = False

    def _display_info_list(self, items: List[Any]):
        """Render a numbered list cleanly (Model + Context only)"""
        # Assumes Lock is HELD
        for i, item in enumerate(items, 1):
            if isinstance(item, dict):
                name = item.get("name", "Unknown")
                ctx = item.get("context_window", "N/A")
            else:
                name = getattr(item, "name", str(item))
                ctx = getattr(item, "context_window", "N/A")

            try:
                if isinstance(ctx, (int, float)) and ctx > 1000:
                    ctx_str = f"{int(ctx/1024)}k"
                else:
                    ctx_str = str(ctx)
            except (ValueError, TypeError):
                ctx_str = str(ctx)

            self.console.print(
                f"  {i}. [cyan]{name}[/cyan] [dim](Context: {ctx_str})[/dim]"
            )

    async def display_selection_list(self, title: str, items: List[Any]) -> Any:
        """Interactive selection list if requested by agent"""
        async with self._lock:
            self.console.print(f"\n[bold blue][SYS] {title}[/bold blue]")
            self._display_info_list(items)

        while True:
            # Use prompt_user logic (handles locks)
            choice = await self.prompt_user("Select #")
            
            try:
                index = int(choice) - 1
                if 0 <= index < len(items):
                    return items[index]
            except ValueError:
                pass

            async with self._lock:
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
        async with self._lock:
            self.console.print(f"[bold red][ERR] {message}[/bold red]")

    async def print_info(self, message: str):
        async with self._lock:
            self.console.print(f"[bold blue][SYS] {message}[/bold blue]")

    async def run_async(self):
        """Main UI Loop"""
        self.console.print(
            "[bold green]Protocol Monk EDA - PlainUI[/bold green]\n"
            "[dim]Standard Output Mode Active[/dim]"
        )

        try:
            while True:
                # If we are waiting for a confirmation (traffic control), 
                # DON'T ask for main user input. Just sleep briefly.
                if self.pending_confirmation:
                    await asyncio.sleep(0.1)
                    continue

                user_input = await self.get_input()

                if not user_input.strip():
                    continue

                await self._event_bus.emit(
                    AgentEvents.COMMAND_RESULT.value,
                    {"input": user_input, "timestamp": datetime.now().isoformat()},
                )
                
                # Assume agent is busy now
                self._agent_is_busy = True

        except KeyboardInterrupt:
            self.console.print("\n[bold red]Shutting down...[/bold red]")

    async def _handle_pending_confirmation(self, user_input: str):
        # Kept for backward compat, but pending_confirmation is handled via tasks now
        pass


def create_plain_ui() -> PlainUI:
    return PlainUI()

#!/usr/bin/env python3
"""
ui/plain.py - Event-Driven Plain CLI for Protocol Monk EDA

Purpose: Professional, developer-focused interface with clean formatting,
visible think tags, and event-driven architecture.

Features:
- Event-driven communication with agent
- Rich Markdown rendering for responses
- Visible think tag parsing (<Thought>, <Contemplation>)
- Interactive Tool Confirmation (Y/N)
- Professional indicators: [MONK], [SYS], [TOOL]
"""

import asyncio
import re
from typing import Any, Dict, List, Optional
from datetime import datetime

from prompt_toolkit import PromptSession
from prompt_toolkit.patch_stdout import patch_stdout
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text
from rich.style import Style

from ui.base import UI, ToolResult
from agent.events import AgentEvents, get_event_bus


class PlainUI(UI):
    """
    Event-Driven Plain CLI - Professional developer interface with Rich support
    """

    def __init__(self):
        super().__init__()
        self.auto_confirm = False
        self._thinking = False
        self._event_bus = get_event_bus()
        self.session = PromptSession()
        self._lock: asyncio.Lock = asyncio.Lock()

        # NEW: State variable for the Traffic Controller
        # Stores {tool_call_id, tool_name} when waiting for user
        self.pending_confirmation: Optional[Dict[str, Any]] = None

        # Initialize Rich Console
        self.console = Console()

        # Subscribe to all agent events
        self._setup_event_listeners()

    def _setup_event_listeners(self):
        """Subscribe to all agent events for professional display"""
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

        # CRITICAL FIX: Tool Confirmation Listener
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

    # --- FIXED: Background Task for Confirmation ---
    async def _on_tool_confirmation_requested(self, data: Dict[str, Any]):
        """
        Handle tool approval requests.
        Action: Spawns a background input task to avoid blocking the Event Bus.
        """
        tool_call = data.get("tool_call", {})
        tool_call_id = data.get("tool_call_id")
        tool_name = tool_call.get("action", "Unknown Tool")
        params = tool_call.get("parameters", {})

        # Display the Request Panel
        self.console.print(
            Panel(
                f"[bold yellow]Tool Execution Request[/bold yellow]\n"
                f"Tool: [cyan]{tool_name}[/cyan]\n"
                f"Params: {params}",
                title="[SYS] Permission Required",
                border_style="yellow",
            )
        )

        # CRITICAL FIX: Spawn a background task to handle input.
        # This allows this handler to return IMMEDIATELY, releasing the Event Bus lock.
        # The Agent is waiting for the 'ui.tool_confirmation' event, which the task will emit.
        asyncio.create_task(self._get_confirmation_input(tool_call_id, tool_name))

    async def _get_confirmation_input(self, tool_call_id: str, tool_name: str):
        """
        Input loop specifically for tool confirmation.
        Runs in background to keep Event Bus free.
        """
        # Small delay to let the panel render and bus unlock
        await asyncio.sleep(0.1)

        try:
            # We can safely call prompt_user here because the Agent
            # is waiting for us and is NOT asking for chat input.
            response = await self.prompt_user(
                f"Approve execution of '{tool_name}'? (y/n)"
            )
            approved = response.lower().startswith("y")
        except Exception as e:
            self.console.print(f"[red]Input Error: {e}[/red]")
            approved = False

        # Feedback
        if approved:
            self.console.print(f"[green]✓ Approved {tool_name}[/green]")
        else:
            self.console.print(f"[red]✗ Rejected {tool_name}[/red]")

        # Send the result event to wake up the Agent
        await self._event_bus.emit(
            "ui.tool_confirmation", {"tool_call_id": tool_call_id, "approved": approved}
        )

    # --- Event Handler Methods ---
    async def _on_agent_error(self, data: Dict[str, Any]):
        message = data.get("message", "Unknown error")
        self.console.print(f"[bold red][ERR][/bold red] {message}")

    async def _on_agent_warning(self, data: Dict[str, Any]):
        message = data.get("message", "Unknown warning")
        self.console.print(f"[bold yellow][WARN][/bold yellow] {message}")

    async def _on_agent_info(self, data: Dict[str, Any]):
        message = data.get("message", "Info message")
        if message.strip():
            self.console.print(f"[bold blue][SYS][/bold blue] {message}")

    async def _on_thinking_started(self, data: Dict[str, Any]):
        message = data.get("message", "Thinking...")
        await self.start_thinking(message)

    async def _on_thinking_stopped(self, data: Dict[str, Any]):
        await self.stop_thinking()

    async def _on_tool_start(self, data: Dict[str, Any]):
        # Handle both single tool and list of tools
        if "tools" in data and isinstance(data["tools"], list):
            names = ", ".join(data["tools"])
            self.console.print(f"[dim][SYS] Executing: {names}...[/dim]")
        else:
            tool_name = data.get("tool_name", "Unknown tool")
            self.console.print(f"[dim][SYS] Executing: {tool_name}...[/dim]")

    async def _on_tool_progress(self, data: Dict[str, Any]):
        message = data.get("message", "Progress update")
        progress = data.get("progress", 0)
        self.console.print(f"[dim][SYS] {message} ({progress}%)[/dim]")

    async def _on_tool_complete(self, data: Dict[str, Any]):
        tool_name = data.get("tool_name", "Unknown tool")
        self.console.print(f"[dim][SYS] Completed: {tool_name}[/dim]")

    async def _on_tool_error(self, data: Dict[str, Any]):
        tool_name = data.get("tool_name", "Unknown tool")
        error = data.get("error", "Unknown error")
        self.console.print(
            f"[bold red][ERR] Tool Error ({tool_name}):[/bold red] {error}"
        )

    async def _on_tool_result(self, data: Dict[str, Any]):
        result = data.get("result", "")
        tool_name = data.get("tool_name", "Unknown tool")
        await self._display_tool_result_markdown(tool_name, result)

    async def _on_stream_chunk(self, data: Dict[str, Any]):
        chunk = data.get("chunk", "")
        await self.print_stream(chunk)

    async def _on_response_complete(self, data: Dict[str, Any]):
        response = data.get("response", "")
        metadata = data.get("metadata", {})
        self.console.print()  # Newline after stream
        if metadata:
            await self._display_metadata(metadata)

    async def _on_context_overflow(self, data: Dict[str, Any]):
        current = data.get("current_tokens", 0)
        max_t = data.get("max_tokens", 0)
        self.console.print(
            f"[bold yellow][WARN] Context overflow: {current}/{max_t}[/bold yellow]"
        )

    async def _on_model_switched(self, data: Dict[str, Any]):
        self.console.print(
            f"[dim][SYS] Model switched: {data.get('old_model')} → {data.get('new_model')}[/dim]"
        )

    async def _on_provider_switched(self, data: Dict[str, Any]):
        self.console.print(
            f"[dim][SYS] Provider switched: {data.get('old_provider')} → {data.get('new_provider')}[/dim]"
        )

    async def _on_command_result(self, data: Dict[str, Any]):
        success = data.get("success", False)
        message = data.get("message", "")
        if success:
            self.console.print(f"[bold green]✓ {message}[/bold green]")
        else:
            self.console.print(f"[bold red]✗ {message}[/bold red]")

    async def _on_status_changed(self, data: Dict[str, Any]):
        self.console.print(
            f"[dim][SYS] Status: {data.get('old_status')} → {data.get('new_status')}[/dim]"
        )

    # --- Display Logic ---
    async def _display_tool_result_markdown(self, tool_name: str, result: Any):
        """Display tool result in a Rich panel"""
        if hasattr(result, "output"):
            content = str(result.output)
        else:
            content = str(result)

        panel = Panel(
            content,  # Simple text for now, could be Markdown(content) if tool output is MD
            title=f"[TOOL] {tool_name}",
            border_style="blue",
            expand=False,
        )
        self.console.print(panel)

    async def _display_metadata(self, metadata: Dict[str, Any]):
        """Display metadata nicely"""
        text = Text()
        for k, v in metadata.items():
            text.append(f"{k}: ", style="bold")
            text.append(f"{v}\n")

        self.console.print(
            Panel(text, title="[SYS] Metadata", border_style="dim white", expand=False)
        )

    async def print_stream(self, text: str):
        """Stream text with Rich support and think tag visibility"""
        async with self._lock:
            if self._thinking:
                self.console.print("\r" + " " * 50 + "\r", end="")
                self._thinking = False
                self.console.print()
                self.console.print("[bold green][MONK][/bold green] ", end="")

            # Simple streaming for now - complex Rich streaming is harder to mix with regex
            # We stick to print(end="") for the stream to keep it fluid
            self.console.print(text, end="", highlight=False)

    async def start_thinking(self, message: str = "Thinking..."):
        async with self._lock:
            self._thinking = True
            self.console.print(
                f"\n[bold magenta][MONK] {message}[/bold magenta]", end=""
            )

    async def stop_thinking(self):
        async with self._lock:
            if self._thinking:
                self.console.print("\r" + " " * 50 + "\r", end="")
                self._thinking = False

    async def prompt_user(self, prompt: str) -> str:
        async with self._lock:
            formatted_prompt = f"\n[bold green]>>> {prompt}:[/bold green] "
            self.console.print(formatted_prompt, end="")
            try:
                with patch_stdout():
                    return await self.session.prompt_async("")
            except (KeyboardInterrupt, EOFError):
                return ""

    # --- Boilerplate Implementations ---
    async def confirm_action(self, message: str) -> bool:
        response = await self.prompt_user(f"{message} (y/n)")
        return response.lower().startswith("y")

    async def display_selection_list(self, title: str, items: List[Any]) -> Any:
        self.console.print(f"\n[bold underline]{title}[/bold underline]")
        for i, item in enumerate(items, 1):
            self.console.print(f"  {i}. {item}")

        while True:
            choice = await self.prompt_user("Select (number)")
            try:
                index = int(choice) - 1
                if 0 <= index < len(items):
                    return items[index]
            except ValueError:
                pass
            self.console.print("[red]Invalid selection[/red]")

    async def display_tool_result(self, result: ToolResult):
        # Redirected to _on_tool_result via event bus usually, but here as fallback
        await self._display_tool_result_markdown(
            result.tool_name or "Tool", result.output
        )

    async def get_input(self) -> str:
        return await self.prompt_user("")

    async def print_error(self, message: str):
        self.console.print(f"[bold red]{message}[/bold red]")

    async def print_info(self, message: str):
        self.console.print(f"[blue]{message}[/blue]")

    async def run_async(self):
        """Main UI loop - Acts as the Traffic Controller for user input"""
        self.console.print(
            Panel.fit(
                "[bold green]Protocol Monk EDA - PlainUI[/bold green]\n"
                "Event-Driven Architecture Active\n"
                "Professional Mode",
                border_style="green",
            )
        )

        try:
            while True:
                # Single point of input entry
                user_input = await self.get_input()

                if not user_input.strip():
                    continue

                # PRIORITY 1: Check for Tool Confirmation (Traffic Controller)
                # This MUST be checked locally to prevent 'y/n' from going to the model
                if self.pending_confirmation:
                    await self._handle_pending_confirmation(user_input)
                    continue

                # PRIORITY 2: Standard Input (Chat & Commands)
                # We send EVERYTHING else to the Agent.
                # The Agent is responsible for detecting slash commands (e.g., /help)
                await self._event_bus.emit(
                    AgentEvents.COMMAND_RESULT.value,
                    {"input": user_input, "timestamp": datetime.now().isoformat()},
                )

        except KeyboardInterrupt:
            self.console.print("\n[bold red]Shutting down...[/bold red]")

    async def _handle_pending_confirmation(self, user_input: str):
        """Process input specifically for tool confirmation"""
        # Retrieve the context we stored
        data = self.pending_confirmation
        tool_call_id = data["tool_call_id"]
        tool_name = data["tool_name"]

        # Determine approval
        approved = user_input.lower().startswith("y")

        # Feedback to user
        if approved:
            self.console.print(f"[green]✓ Approved {tool_name}[/green]")
        else:
            self.console.print(f"[red]✗ Rejected {tool_name}[/red]")

        # Emit the result event
        await self._event_bus.emit(
            "ui.tool_confirmation", {"tool_call_id": tool_call_id, "approved": approved}
        )

        # Reset the Traffic Controller Flag
        self.pending_confirmation = None


def create_plain_ui() -> PlainUI:
    return PlainUI()

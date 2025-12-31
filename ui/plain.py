#!/usr/bin/env python3
"""
ui/plain.py - Event-Driven Plain CLI for Protocol Monk EDA

Purpose: Professional, developer-focused interface with clean formatting,
visible think tags, and event-driven architecture. No emojis, pure functionality.

Features:
- Event-driven communication with agent
- Markdown rendering for model responses  
- Visible think tag parsing (<Thought>, <Contemplation>)
- Professional indicators: [MONK], >>>(user), [TOOL], [SYS]
- Static "Thinking..." indicator during processing
- Clean tool approval menu system
- Thread-safe operations with prompt_toolkit
"""

import asyncio
import sys
import re
from typing import Any, Dict, List, Optional
from datetime import datetime

from prompt_toolkit import PromptSession
from prompt_toolkit.patch_stdout import patch_stdout
import markdown

from ui.base import UI, ToolResult
from agent.events import AgentEvents, get_event_bus


class PlainUI(UI):
    """
    Event-Driven Plain CLI - Professional developer interface
    """
    
    def __init__(self):
        super().__init__()
        self.auto_confirm = False
        self._thinking = False
        self._event_bus = get_event_bus()
        self.session = PromptSession()
        self._lock: asyncio.Lock = asyncio.Lock()
        
        # Subscribe to all agent events for clean event-driven architecture
        self._setup_event_listeners()
        
        # Markdown processor for enhanced display
        self._markdown = markdown.Markdown(extensions=['extra', 'codehilite'])
        
    def _setup_event_listeners(self):
        """Subscribe to all agent events for professional display"""
        # Core agent events
        self._event_bus.subscribe(AgentEvents.ERROR.value, self._on_agent_error)
        self._event_bus.subscribe(AgentEvents.WARNING.value, self._on_agent_warning)
        self._event_bus.subscribe(AgentEvents.INFO.value, self._on_agent_info)
        
        # Thinking events
        self._event_bus.subscribe(AgentEvents.THINKING_STARTED.value, self._on_thinking_started)
        self._event_bus.subscribe(AgentEvents.THINKING_STOPPED.value, self._on_thinking_stopped)
        
        # Tool execution events
        self._event_bus.subscribe(AgentEvents.TOOL_EXECUTION_START.value, self._on_tool_start)
        self._event_bus.subscribe(AgentEvents.TOOL_EXECUTION_PROGRESS.value, self._on_tool_progress)
        self._event_bus.subscribe(AgentEvents.TOOL_EXECUTION_COMPLETE.value, self._on_tool_complete)
        self._event_bus.subscribe(AgentEvents.TOOL_ERROR.value, self._on_tool_error)
        self._event_bus.subscribe(AgentEvents.TOOL_RESULT.value, self._on_tool_result)
        
        # Stream events
        self._event_bus.subscribe(AgentEvents.STREAM_CHUNK.value, self._on_stream_chunk)
        self._event_bus.subscribe(AgentEvents.RESPONSE_COMPLETE.value, self._on_response_complete)
        
        # Context events
        self._event_bus.subscribe(AgentEvents.CONTEXT_OVERFLOW.value, self._on_context_overflow)
        self._event_bus.subscribe(AgentEvents.MODEL_SWITCHED.value, self._on_model_switched)
        self._event_bus.subscribe(AgentEvents.PROVIDER_SWITCHED.value, self._on_provider_switched)
        
        # Status events
        self._event_bus.subscribe(AgentEvents.COMMAND_RESULT.value, self._on_command_result)
        self._event_bus.subscribe(AgentEvents.STATUS_CHANGED.value, self._on_status_changed)
    
    # Event Handler Methods - Professional Display
    async def _on_agent_error(self, data: Dict[str, Any]):
        """Handle agent error events with professional formatting"""
        message = data.get('message', 'Unknown error')
        await self.print_error(message)
    
    async def _on_agent_warning(self, data: Dict[str, Any]):
        """Handle agent warning events"""
        message = data.get('message', 'Unknown warning')
        await self.print_warning(message)
    
    async def _on_agent_info(self, data: Dict[str, Any]):
        """Handle agent info events"""
        message = data.get('message', 'Info message')
        await self.print_info(message)
    
    async def _on_thinking_started(self, data: Dict[str, Any]):
        """Handle thinking started events"""
        message = data.get('message', 'Thinking...')
        await self.start_thinking(message)
    
    async def _on_thinking_stopped(self, data: Dict[str, Any]):
        """Handle thinking stopped events"""
        await self.stop_thinking()
    
    async def _on_tool_start(self, data: Dict[str, Any]):
        """Handle tool execution start events"""
        tool_name = data.get('tool_name', 'Unknown tool')
        await self.print_info(f"Executing: {tool_name}")
    
    async def _on_tool_progress(self, data: Dict[str, Any]):
        """Handle tool execution progress events"""
        message = data.get('message', 'Progress update')
        progress = data.get('progress', 0)
        await self.print_info(f"Progress: {message} ({progress}%)")
    
    async def _on_tool_complete(self, data: Dict[str, Any]):
        """Handle tool execution complete events"""
        tool_name = data.get('tool_name', 'Unknown tool')
        await self.print_info(f"Completed: {tool_name}")
    
    async def _on_tool_error(self, data: Dict[str, Any]):
        """Handle tool error events"""
        tool_name = data.get('tool_name', 'Unknown tool')
        error = data.get('error', 'Unknown error')
        await self.print_error(f"Tool Error ({tool_name}): {error}")
    
    async def _on_tool_result(self, data: Dict[str, Any]):
        """Handle tool result events"""
        result = data.get('result', '')
        tool_name = data.get('tool_name', 'Unknown tool')
        await self._display_tool_result_markdown(tool_name, result)
    
    async def _on_stream_chunk(self, data: Dict[str, Any]):
        """Handle streaming text chunks"""
        chunk = data.get('chunk', '')
        await self.print_stream(chunk)
    
    async def _on_response_complete(self, data: Dict[str, Any]):
        """Handle response completion events"""
        response = data.get('response', '')
        metadata = data.get('metadata', {})
        await self.print_info("Response complete")
        if metadata:
            await self._display_metadata(metadata)
    
    async def _on_context_overflow(self, data: Dict[str, Any]):
        """Handle context overflow events"""
        current_tokens = data.get('current_tokens', 0)
        max_tokens = data.get('max_tokens', 0)
        await self.print_warning(f"Context overflow: {current_tokens}/{max_tokens} tokens")
    
    async def _on_model_switched(self, data: Dict[str, Any]):
        """Handle model switch events"""
        old_model = data.get('old_model', 'Unknown')
        new_model = data.get('new_model', 'Unknown')
        await self.print_info(f"Model switched: {old_model} → {new_model}")
    
    async def _on_provider_switched(self, data: Dict[str, Any]):
        """Handle provider switch events"""
        old_provider = data.get('old_provider', 'Unknown')
        new_provider = data.get('new_provider', 'Unknown')
        await self.print_info(f"Provider switched: {old_provider} → {new_provider}")
    
    async def _on_command_result(self, data: Dict[str, Any]):
        """Handle command result events"""
        success = data.get('success', False)
        message = data.get('message', 'Command completed')
        if success:
            await self.print_info(message)
        else:
            await self.print_error(message)
    
    async def _on_status_changed(self, data: Dict[str, Any]):
        """Handle status change events"""
        old_status = data.get('old_status', 'Unknown')
        new_status = data.get('new_status', 'Unknown')
        await self.print_info(f"Status: {old_status} → {new_status}")
    
    # Core UI Implementation Methods - Professional Display
    async def _display_tool_result_markdown(self, tool_name: str, result: str):
        """Display tool result with markdown formatting"""
        try:
            print(f"\n[TOOL] Result: {tool_name}")
            html = self._markdown.convert(result)
            # Simple markdown to terminal conversion for now
            print(result)
        except Exception as e:
            print(f"[TOOL] Result: {tool_name}")
            print(result)
    
    async def _display_metadata(self, metadata: Dict[str, Any]):
        """Display response metadata"""
        if metadata:
            print(f"\n[SYS] Metadata:")
            for key, value in metadata.items():
                print(f"  {key}: {value}")
            print()
    
    # Abstract Method Implementations - Professional Formatting
    async def print_stream(self, text: str):
        """Stream text output with think tag visibility and markdown support"""
        async with self._lock:
            if self._thinking:
                # Transition from thinking to speaking
                print("\r" + " " * 50 + "\r", end="")
                self._thinking = False
                print()  # Blank line for separation
                print("[MONK] ", end="", flush=True)
            
            # Parse and display think tags visibly (NOT hidden)
            think_pattern = r"<(thought|contemplation|thinking)>(.*?)</\1>"
            think_matches = re.findall(think_pattern, text, flags=re.IGNORECASE | re.DOTALL)
            
            # Display think sections prominently
            for tag_type, think_content in think_matches:
                if think_content.strip():
                    print(f"\n[MONK] <{tag_type.upper()}>")
                    print(think_content.strip())
                    print(f"</{tag_type.upper()}>")
            
            # Display remaining content with markdown support
            remaining_text = re.sub(think_pattern, "", text, flags=re.IGNORECASE | re.DOTALL).strip()
            if remaining_text:
                try:
                    # Simple markdown to terminal conversion
                    print(remaining_text, end="", flush=True)
                except Exception as e:
                    # Fallback to plain text
                    print(remaining_text, end="", flush=True)
    
    async def print_error(self, message: str):
        """Print error message with professional formatting"""
        print(f"\n[ERR] {message}\n")
    
    async def print_warning(self, message: str):
        """Print warning message"""
        print(f"\n[WARN] {message}\n")
    
    async def print_info(self, message: str):
        """Print info message"""
        if message.strip():
            print(f"\n[SYS] {message}\n")
        else:
            print()
    
    async def start_thinking(self, message: str = "Thinking..."):
        """Indicate that the agent is processing. Static professional indicator."""
        async with self._lock:
            self._thinking = True
            print(f"\n[MONK] {message}", end="", flush=True)
    
    async def stop_thinking(self):
        """Stop the thinking indicator."""
        async with self._lock:
            if self._thinking:
                print("\r" + " " * 50 + "\r", end="", flush=True)
                self._thinking = False
    
    async def prompt_user(self, prompt: str) -> str:
        """Prompt user for input with professional formatting"""
        async with self._lock:
            print()  # Always print newline before prompt
            
            # Professional prompt formatting
            formatted_prompt = (
                f">>> {prompt}: " if not prompt.endswith(("?", ":", ">")) else f">>> {prompt} "
            )
            
            try:
                with patch_stdout():
                    return await self.session.prompt_async(formatted_prompt)
            except (KeyboardInterrupt, EOFError):
                return ""
    
    async def display_selection_list(self, title: str, items: List[Any]) -> Any:
        """Display numbered list for CLI selection"""
        print(f"\n=== {title} ===")
        for i, item in enumerate(items, 1):
            # Extract display text
            if isinstance(item, dict):
                text = f"{item.get('name', '')} ({item.get('provider', '')})"
            elif hasattr(item, "name"):
                text = f"{item.name} ({getattr(item, 'provider', '')})"
            else:
                text = str(item)
            print(f"  {i}. {text}")
        print()
        
        while True:
            try:
                choice = await self.prompt_user("Select (number)")
                index = int(choice) - 1
                if 0 <= index < len(items):
                    return items[index]
                else:
                    await self.print_error("Invalid selection")
            except ValueError:
                await self.print_error("Please enter a number")
    
    async def confirm_action(self, message: str) -> bool:
        """Confirm action with user"""
        response = await self.prompt_user(f"{message} (y/n)")
        return response.lower().startswith('y')
    
    async def display_tool_result(self, result: ToolResult):
        """Display tool execution result with professional formatting"""
        if result.success:
            print(f"\n[TOOL] ✓ {result.tool_name or 'Tool'} completed")
            output = result.output
            
            # Truncate very long outputs professionally
            if len(output) > 1000:
                lines = output.split("\n")
                if len(lines) > 20:
                    preview = "\n".join(lines[:15])
                    print(f"{preview}\n... ({len(lines) - 15} more lines)")
                else:
                    print(output[:1000] + "\n... (truncated)")
            else:
                print(output)
        else:
            print(f"\n[TOOL] ✗ {result.tool_name or 'Tool'} failed")
            print(result.output)
    
    async def get_input(self) -> str:
        """Get user input with professional prompt"""
        return await self.prompt_user(">>>")
    
    async def run_async(self):
        """Main UI loop - professional event-driven interface"""
        print("[SYS] Protocol Monk Plain CLI - Event-Driven Interface")
        print("[SYS] All events active - professional mode engaged")
        
        try:
            while True:
                try:
                    user_input = await self.get_input()
                    if user_input.strip():
                        # Professional input handling - no double-processing
                        if user_input.startswith('/'):
                            # Slash commands handled by dispatcher
                            continue
                        
                        # Emit user input for agent processing
                        await self._event_bus.emit(AgentEvents.COMMAND_RESULT.value, {
                            'input': user_input,
                            'timestamp': datetime.now().isoformat()
                        })
                except KeyboardInterrupt:
                    # Professional interrupt handling
                    print("\n[SYS] Use Ctrl+C again to exit, or type 'quit'")
                    continue
        except KeyboardInterrupt:
            # Final exit
            print("\n[SYS] Plain CLI shutting down...")
        except Exception as e:
            print(f"\n[ERR] UI Error: {e}")


# Factory function for creating PlainUI instances
def create_plain_ui() -> PlainUI:
    """Create a new PlainUI instance"""
    return PlainUI()
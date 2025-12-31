#!/usr/bin/env python3
"""
ui/dev.py - Event-Driven Developer UI for Protocol Monk EDA

Purpose: Development-focused UI that serves as the proving ground for 
event-driven architecture. Replaces plain.py with clean event integration.

Features:
- Event-driven communication with agent
- Markdown rendering support
- Developer-focused formatting
- Async/await throughout
- No backwards compatibility constraints

TEMPORARY: This UI will be refined/removed before final release.
"""

import asyncio
import sys
import re
from typing import Any, Dict, List, Optional
from datetime import datetime

import markdown
from prompt_toolkit import PromptSession
from prompt_toolkit.patch_stdout import patch_stdout

from ui.base import UI, ToolResult
from agent.events import AgentEvents, get_event_bus


class DevUI(UI):
    """
    Event-Driven Developer UI - The proving ground for EDA architecture
    """
    
    def __init__(self):
        super().__init__()
        self.auto_confirm = False
        self._thinking = False
        self._event_bus = get_event_bus()
        self.session = PromptSession()
        self._lock: asyncio.Lock = asyncio.Lock()
        
        # Subscribe to agent events
        self._setup_event_listeners()
        
        # Markdown processor for enhanced display
        self._markdown = markdown.Markdown(extensions=['extra', 'codehilite'])
        
    def _setup_event_listeners(self):
        """Subscribe to all agent events"""
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
    
    # Event Handler Methods
    async def _on_agent_error(self, data: Dict[str, Any]):
        """Handle agent error events"""
        message = data.get('message', 'Unknown error')
        await self.print_error(f"Agent Error: {message}")
    
    async def _on_agent_warning(self, data: Dict[str, Any]):
        """Handle agent warning events"""
        message = data.get('message', 'Unknown warning')
        await self.print_info(f"⚠️  Warning: {message}")
    
    async def _on_agent_info(self, data: Dict[str, Any]):
        """Handle agent info events"""
        message = data.get('message', 'Info message')
        await self.print_info(f"ℹ️  {message}")
    
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
        await self.print_info(f"🔧 Executing: {tool_name}")
    
    async def _on_tool_progress(self, data: Dict[str, Any]):
        """Handle tool execution progress events"""
        message = data.get('message', 'Progress update')
        progress = data.get('progress', 0)
        await self.print_info(f"⏳ {message} ({progress}%)")
    
    async def _on_tool_complete(self, data: Dict[str, Any]):
        """Handle tool execution complete events"""
        tool_name = data.get('tool_name', 'Unknown tool')
        await self.print_info(f"✅ Completed: {tool_name}")
    
    async def _on_tool_error(self, data: Dict[str, Any]):
        """Handle tool error events"""
        tool_name = data.get('tool_name', 'Unknown tool')
        error = data.get('error', 'Unknown error')
        await self.print_error(f"❌ Tool Error ({tool_name}): {error}")
    
    async def _on_tool_result(self, data: Dict[str, Any]):
        """Handle tool result events"""
        result = data.get('result', '')
        tool_name = data.get('tool_name', 'Unknown tool')
        await self._display_markdown(f"**Tool Result ({tool_name}):**\n{result}")
    
    async def _on_stream_chunk(self, data: Dict[str, Any]):
        """Handle streaming text chunks"""
        chunk = data.get('chunk', '')
        await self.print_stream(chunk)
    
    async def _on_response_complete(self, data: Dict[str, Any]):
        """Handle response completion events"""
        response = data.get('response', '')
        metadata = data.get('metadata', {})
        await self.print_info("📝 Response complete")
        if metadata:
            await self._display_metadata(metadata)
    
    async def _on_context_overflow(self, data: Dict[str, Any]):
        """Handle context overflow events"""
        current_tokens = data.get('current_tokens', 0)
        max_tokens = data.get('max_tokens', 0)
        await self.print_warning(f"🚨 Context overflow: {current_tokens}/{max_tokens} tokens")
    
    async def _on_model_switched(self, data: Dict[str, Any]):
        """Handle model switch events"""
        old_model = data.get('old_model', 'Unknown')
        new_model = data.get('new_model', 'Unknown')
        await self.print_info(f"🔄 Model switched: {old_model} → {new_model}")
    
    async def _on_provider_switched(self, data: Dict[str, Any]):
        """Handle provider switch events"""
        old_provider = data.get('old_provider', 'Unknown')
        new_provider = data.get('new_provider', 'Unknown')
        await self.print_info(f"🔀 Provider switched: {old_provider} → {new_provider}")
    
    async def _on_command_result(self, data: Dict[str, Any]):
        """Handle command result events"""
        success = data.get('success', False)
        message = data.get('message', 'Command completed')
        if success:
            await self.print_info(f"✅ {message}")
        else:
            await self.print_error(f"❌ {message}")
    
    async def _on_status_changed(self, data: Dict[str, Any]):
        """Handle status change events"""
        old_status = data.get('old_status', 'Unknown')
        new_status = data.get('new_status', 'Unknown')
        await self.print_info(f"📊 Status: {old_status} → {new_status}")
    
    # Core UI Implementation Methods
    async def _display_markdown(self, text: str):
        """Display text with markdown rendering"""
        try:
            html = self._markdown.convert(text)
            # Simple markdown to terminal conversion
            # For now, just display the raw text with basic formatting
            print(f"\n{text}\n")
        except Exception as e:
            print(f"Markdown render error: {e}")
            print(text)
    
    async def _display_metadata(self, metadata: Dict[str, Any]):
        """Display response metadata"""
        if metadata:
            print(f"\n[Metadata]")
            for key, value in metadata.items():
                print(f"  {key}: {value}")
            print()
    
    # Abstract Method Implementations
    async def print_stream(self, text: str):
        """Stream text output"""
        print(text, end="", flush=True)
    
    async def print_error(self, message: str):
        """Print error message"""
        print(f"\n❌ ERROR: {message}\n")
    
    async def print_info(self, message: str):
        """Print info message"""
        print(f"\nℹ️  {message}\n")
    
    async def start_thinking(self, message: str = "Thinking..."):
        """Start thinking indicator"""
        async with self._lock:
            self._thinking = True
            print(f"\n🤔 {message}\n", end="", flush=True)
    
    async def stop_thinking(self):
        """Stop thinking indicator"""
        async with self._lock:
            if self._thinking:
                print("\r" + " " * 50 + "\r", end="", flush=True)
                self._thinking = False
    
    async def prompt_user(self, prompt: str) -> str:
        """Prompt user for input"""
        async with self._lock:
            with patch_stdout():
                try:
                    return await self.session.prompt_async(f"\n{prompt} ")
                except KeyboardInterrupt:
                    return ""
    
    async def display_selection_list(self, title: str, items: List[Any]) -> Any:
        """Display selection list"""
        print(f"\n📋 {title}")
        for i, item in enumerate(items, 1):
            print(f"  {i}. {item}")
        
        while True:
            try:
                choice = await self.prompt_user("Select (number):")
                index = int(choice) - 1
                if 0 <= index < len(items):
                    return items[index]
                else:
                    await self.print_error("Invalid selection")
            except ValueError:
                await self.print_error("Please enter a number")
    
    async def confirm_action(self, message: str) -> bool:
        """Confirm action with user"""
        response = await self.prompt_user(f"{message} (y/n):")
        return response.lower().startswith('y')
    
    async def display_tool_result(self, result: ToolResult):
        """Display tool execution result"""
    async def run_async(self):
        """Main UI loop - event driven with proper interrupt handling"""
        await self.print_info("🚀 Protocol Monk EDA - Developer UI Started")
        await self.print_info("All 55 events are active and ready for testing")
        
        try:
            while True:
                try:
                    user_input = await self.get_input()
                    if user_input.strip():
                        # CRITICAL FIX: Don't double-process slash commands
                        # Slash commands are handled by command dispatcher via events
                        if user_input.startswith('/'):
                            # Skip regular processing - let command dispatcher handle it
                            continue
                        
                        # Only emit non-slash commands for regular agent processing
                        await self._event_bus.emit(AgentEvents.COMMAND_RESULT.value, {
                            'input': user_input,
                            'timestamp': datetime.now().isoformat()
                        })
                except KeyboardInterrupt:
                    # Handle Ctrl+C gracefully
                    await self.print_info("\n👋 Use Ctrl+C again to exit, or type 'quit'")
                    continue
        except KeyboardInterrupt:
            # Second Ctrl+C or system interrupt
            await self.print_info("\n👋 Developer UI shutting down...")
        except Exception as e:
            await self.print_error(f"UI Error: {e}")
    async def get_input(self) -> str:
        """Get user input with developer-friendly prompt"""
        return await self.prompt_user("🤖 >")
    
    async def confirm_action(self, message: str) -> bool:
        """Confirm action with user"""
        response = await self.prompt_user(f"{message} (y/n):")
        return response.lower().startswith('y')
    
    async def display_tool_result(self, result: ToolResult):
        """Display tool execution result"""
        if result.success:
            await self._display_markdown(f"**Tool: {result.tool_name}**\n{result.output}")
        else:
            await self.print_error(f"Tool {result.tool_name} failed: {result.output}")


# Factory function for creating DevUI instances
def create_dev_ui() -> DevUI:
    """Create a new DevUI instance"""
    return DevUI()
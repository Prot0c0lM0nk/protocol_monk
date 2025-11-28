#!/usr/bin/env python3
"""
Plain text async UI implementation for Protocol Monk

Uses print() and input() for basic terminal interaction.
Designed to be simple and work in any terminal environment.
"""
import json
import asyncio
import sys
from typing import Dict, Any, Union, List
from ui.base import UI, ToolResult


class PlainUI(UI):
    """Async plain text UI implementation"""
    
    def __init__(self):
        self.auto_confirm = False
        self._thinking = False
    
    async def start_thinking(self, message: str = "Thinking..."):
        """Indicate that the agent is processing."""
        self._thinking = True
        print(f"{message}", end="\r", flush=True)
    
    async def stop_thinking(self):
        """Stop the thinking indicator."""
        if self._thinking:
            print(" " * 40, end="\r", flush=True)  # Clear the thinking message
            self._thinking = False
    
    async def confirm_tool_call(self, tool_call: Dict, auto_confirm: bool = False) -> Union[bool, Dict]:
        if auto_confirm or self.auto_confirm:
            await self.display_tool_call(tool_call, auto_confirm=True)
            return True
        
        await self.display_tool_call(tool_call, auto_confirm=False)
        
        # Simple y/n/m approval
        response = await self._get_input("Execute this action? [Y/n/m] (m = suggest modification) ")
        response = response.strip().lower()
        
        if response in ('y', 'yes'):
            return True
        elif response == 'm':
            # Modify option - get human suggestion
            await self.print_info("\nWhat would you like to suggest to the model?")
            await self.print_info("(Describe your suggestion in natural language)")
            suggestion = await self.prompt_user("Suggestion: ")
            
            if not suggestion.strip():
                return False
            
            # Return the suggestion as a modification request
            # The model will see this and can modify its tool call accordingly
            return {"modified": {
                "action": tool_call["action"],
                "parameters": tool_call["parameters"],  # Keep original params
                "reasoning": tool_call.get("reasoning", ""),
                "human_suggestion": suggestion  # Add human's suggestion
            }}
        else:
            return False
    
    async def _get_input(self, prompt: str) -> str:
        """Helper to get input in async context"""
        # Use asyncio.to_thread to avoid blocking the event loop
        try:
            return await asyncio.to_thread(input, prompt)
        except (KeyboardInterrupt, asyncio.CancelledError):
            # Re-raise KeyboardInterrupt to be handled by main loop
            raise KeyboardInterrupt()
    async def display_tool_call(self, tool_call: Dict, auto_confirm: bool = False):
        action = tool_call["action"]
        parameters = tool_call["parameters"]
        reasoning = tool_call.get("reasoning", "")
        
        print(f"\nProposed Action: {action}")
        
        if reasoning:
            print(f"Reasoning: {reasoning}")
        
        if parameters:
            print("\nParameters:")
            for key, value in parameters.items():
                value_str = str(value)
                if len(value_str) > 200:
                    if '\n' in value_str:
                        lines = value_str.split('\n')
                        preview = '\n'.join(lines[:5])
                        value_str = f"{preview}\n... ({len(lines) - 5} more lines)"
                    else:
                        value_str = value_str[:200] + "..."
                
                print(f"  {key}: {value_str}")
        
        if auto_confirm:
            print("(Auto-executing action)")
    
    async def display_tool_result(self, result: ToolResult, tool_name: str):
        if result.success:
            print(f"\n✓ {tool_name} completed")
            output = result.output
            if len(output) > 1000:
                lines = output.split('\n')
                if len(lines) > 20:
                    preview = '\n'.join(lines[:15])
                    print(f"{preview}\n... ({len(lines) - 15} more lines)")
                else:
                    print(output[:1000] + "\n... (truncated)")
            else:
                print(output)
        else:
            print(f"✗ {tool_name} failed")
            print(result.output)
    
    async def display_execution_start(self, count: int):
        print(f"\nExecuting {count} tool(s)...")
    
    async def display_progress(self, current: int, total: int):
        print(f"\nTool {current}/{total}")
    
    async def display_task_complete(self, summary: str = ""):
        print("✓ Task completed")
        if summary:
            print(summary)
    
    async def print_error(self, message: str):
        print(f"Error: {message}")
    
    async def print_warning(self, message: str):
        print(f"Warning: {message}")
    
    async def print_info(self, message: str):
        # Don't prefix with "Info:" for decorative or empty messages
        # Don't prefix with "Info:" for decorative or empty messages
        if message.strip() and not message.strip().startswith('☦️'):
            print(f"Info: {message}")
        elif message.strip():
            print(message)
        else:
            # Empty message - just print a newline
            print()
    
    async def set_auto_confirm(self, value: bool):
        self.auto_confirm = value
        status = "enabled" if value else "disabled"
        print(f"Auto-confirm {status}")


    async def print_stream(self, text: str):
        """Stream text without newline"""
        print(text, end="", flush=True)


    async def display_startup_banner(self, greeting: str):
        """Display startup banner/greeting"""
        print(greeting)
    
    async def display_startup_frame(self, frame: str):
        """Display startup animation frame"""
        print(frame)
    
    async def prompt_user(self, prompt: str) -> str:
        """Prompt user for input"""
        return await self._get_input(prompt)
    
    async def print_error_stderr(self, message: str):
        """Print error to stderr"""
        print(message, file=sys.stderr)


    async def display_startup_banner(self, greeting: str):
        """Display startup banner/greeting"""
        print(greeting)
    
    async def display_startup_frame(self, frame: str):
        """Display startup animation frame"""
        print(frame)
    
    async def prompt_user(self, prompt: str) -> str:
        """Prompt user for input"""
        return await self._get_input(prompt)
    
    async def print_error_stderr(self, message: str):
        """Print error to stderr"""
        print(message, file=sys.stderr)


    async def display_model_list(self, models: List[Any], current_model: str):
        print(f"\n=== Available Models (Current: {current_model}) ===")
        for m in models:
            name = getattr(m, 'name', m.get('name') if isinstance(m, dict) else str(m))
            ctx = getattr(m, 'context_window', m.get('context_window', 0) if isinstance(m, dict) else 0)
            marker = "*" if name == current_model else " "
            print(f" {marker} {name:<25} [{ctx:,}] ")
        print()

    async def display_switch_report(self, report: Any, current_model: str, target_model: str):
        # Extract data (handle object vs dict)
        safe = getattr(report, 'safe', report.get('safe', False) if isinstance(report, dict) else False)
        curr = getattr(report, 'current_tokens', 0)
        limit = getattr(report, 'target_limit', 0)
        
        if not safe:
            print(f"\n⚠️  WARNING: Context Overflow ({curr:,} > {limit:,})")
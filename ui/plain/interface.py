import asyncio
from typing import Dict, Any, List

# Import the base class and types
from ui.base import UI, ToolResult
from ui.plain.input import PlainInputHandler
from ui.plain.renderer import PlainRenderer

class PlainInterface(UI):
    """
    A lightweight, asynchronous CLI interface.
    """
    def __init__(self):
        super().__init__() # Initialize the lock from base
        self.input_handler = PlainInputHandler()
        self.renderer = PlainRenderer()

    # --- BLOCKING INTERACTION METHODS ---
    
    async def get_input(self) -> str:
        """
        Get user input for the main loop.
        """
        # Ensure any hanging stream output is closed off with a newline
        self.renderer.new_line()
        
        # We use a visual cue that it's the user's turn
        return await self.input_handler.get_input("\n>>> ")

    async def confirm_tool_execution(self, tool_call_data: Dict[str, Any]) -> bool:
        """
        Ask user to confirm a tool execution.
        """
        self.renderer.new_line()
        tool_name = tool_call_data.get("name", "Unknown Tool")
        args = tool_call_data.get("arguments", {})
        
        self.renderer.print_tool_call(tool_name, args)
        
        return await self.input_handler.confirm(f"Execute {tool_name}?")

    # --- Output Methods ---

    async def print_stream(self, text: str):
        self.renderer.stream(text)

    async def print_error(self, message: str):
        self.renderer.print_error(message)

    async def print_info(self, message: str):
        self.renderer.print_system(message)
    
    async def print_warning(self, message: str):
        self.renderer.print_warning(message)

    async def start_thinking(self):
        # In a plain UI, we might just print a status line.
        # We avoid spinning animations here to keep it "Plain".
        self.renderer.print_system("Thinking...")

    async def stop_thinking(self):
        # No-op in plain UI, or clear line if you want to get fancy.
        pass

    # --- Compat Stubs & Optional Overrides ---

    async def display_tool_result(self, result: ToolResult, tool_name: str):
        self.renderer.print_tool_result(tool_name, result.output)

    async def display_startup_banner(self, greeting: str):
        print("\n" + "="*40)
        print(f" {greeting}")
        print("="*40 + "\n")

    async def shutdown(self):
        self.renderer.print_system("Shutting down interface...")
"""
ui/textual/client.py
The Bridge between the Real Agent and the Textual App.
"""
import asyncio
from typing import Dict, Union, Any
from ui.base import UI, ToolResult
from .app import ProtocolMonkApp
from .messages import StreamText, AgentMessage, UpdateStatus

class TextualUI(UI):
    """
    The Textual implementation of the UI contract.
    """
    
    def __init__(self):
        super().__init__()
        self.app = ProtocolMonkApp()
        self.agent = None  # We will attach the agent later

    def set_agent(self, agent):
        """Attach the real agent instance."""
        self.agent = agent

    # --- 1. RUNNING THE APP ---
    async def run_async(self):
        """
        Async entry point for main.py.
        Uses Textual's run_async to avoid conflicting with the existing event loop.
        """
        # Inject the input handler
        self.app.set_input_handler(self.handle_user_input)
        
        # Start the app asynchronously
        await self.app.run_async()

    async def handle_user_input(self, user_input: str):
        """
        Called when user hits Enter in the TUI.
        We pass this input to the Real Agent.
        """
        if self.agent:
            # Run the TAOR loop for this input
            # We treat it as a task so it doesn't freeze the UI
            await self.agent.process_request(user_input)
        else:
            await self.print_error("Agent not connected!")

    # --- 2. OUTPUT METHODS (Agent -> UI) ---

    async def print_stream(self, text: str):
        """Receives a string from monk.py and posts it to Textual."""
        if self.app.is_running:
            self.app.post_message(StreamText(text))

    async def print_info(self, message: str):
        if self.app.is_running:
            self.app.post_message(AgentMessage("info", message))

    async def print_error(self, message: str):
        if self.app.is_running:
            self.app.post_message(AgentMessage("error", message))
            
    async def print_warning(self, message: str):
        if self.app.is_running:
            self.app.post_message(AgentMessage("warning", message))

    async def start_thinking(self):
        if self.app.is_running:
            self.app.post_message(UpdateStatus("thinking", True))

    async def stop_thinking(self):
        if self.app.is_running:
            self.app.post_message(UpdateStatus("thinking", False))

    # --- 3. TOOLING & INTERACTION ---

    async def display_tool_call(self, tool_call: Dict, auto_confirm: bool = False):
        if self.app.is_running:
            self.app.post_message(AgentMessage("tool_call", tool_call))

    async def display_tool_result(self, result: ToolResult, tool_name: str):
        if self.app.is_running:
            self.app.post_message(AgentMessage("tool_result", {
                "name": tool_name,
                "output": result.output,
                "success": result.success
            }))

    async def prompt_user(self, prompt: str) -> str:
        """
        Used when the Agent needs to ask a question MID-LOOP 
        (like "Confirm delete file?").
        """
        if self.app.is_running:
            # This pauses the Agent until the user types in the TUI
            return await self.app.await_user_input(prompt)
        return ""

    # --- Stubs ---
    async def close(self): pass
    async def display_startup_banner(self, greeting: str): pass
    async def confirm_tool_call(self, tool_call, auto_confirm=False): return True
    async def display_execution_start(self, count): pass
    async def display_progress(self, current, total): pass
    async def display_task_complete(self, summary=""): pass
    async def print_error_stderr(self, message): pass
    async def set_auto_confirm(self, value): pass
    async def display_startup_frame(self, frame): pass
    async def display_model_list(self, models, current): pass
    async def display_switch_report(self, report, current, target): pass
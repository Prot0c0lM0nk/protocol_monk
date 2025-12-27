"""
ui/textual/client.py
The Bridge: Connects the Agent (logic) to the Textual App (visuals).
"""
import asyncio
from typing import Dict, Union, Any, List
from ui.base import UI, ToolResult
from .app import ProtocolMonkApp
from .screens.tool_confirm import ToolConfirmModal
from .messages import StreamText, AgentMessage, UpdateStatus
from .screens.selection import SelectionModal

class TextualUI(UI):
    """
    Implementation of the UI abstract class that drives a Textual App.
    """
    
    def __init__(self):
        super().__init__()
        self.app = ProtocolMonkApp()
        self.agent = None
        self.dispatcher = None

    def set_agent(self, agent):
        """Connect the agent and initialize the command dispatcher."""
        self.agent = agent
        # Lazy import to avoid circular dependency
        from agent.command_dispatcher import CommandDispatcher
        self.dispatcher = CommandDispatcher(agent)

    async def run_async(self):
        """Start the TUI loop."""
        # Inject our input handler into the App
        self.app.set_input_handler(self.handle_user_input)
        await self.app.run_async()

    async def handle_user_input(self, user_input: str):
        """Callback: The App sends us user input here."""
        # 1. Try Slash Commands
        if self.dispatcher:
            result = await self.dispatcher.dispatch(user_input)
            if result is False: # /quit
                await self.app.action_quit()
                return
            if result is True: # Command handled
                return

        # 2. Pass to Agent
        if self.agent:
            await self.agent.process_request(user_input)

    # --- UI Contract Implementation ---

    async def start_thinking(self):
        if self.app.is_running:
            self.app.post_message(UpdateStatus("thinking", True))

    async def stop_thinking(self):
        if self.app.is_running:
            self.app.post_message(UpdateStatus("thinking", False))

    async def print_stream(self, text: str):
        if self.app.is_running:
            self.app.post_message(StreamText(text))

    async def print_error(self, message: str):
        if self.app.is_running:
            self.app.post_message(AgentMessage("error", message))

    async def print_info(self, message: str):
        if self.app.is_running:
            self.app.post_message(AgentMessage("info", message))
            
    async def print_warning(self, message: str):
        if self.app.is_running:
            self.app.post_message(AgentMessage("warning", message))

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

    async def confirm_tool_call(self, tool_call: Dict, auto_confirm: bool = False) -> Union[bool, Dict]:
        """
        CRITICAL: Intercept confirmation and show the Modal.
        """
        if auto_confirm:
            return True

        if self.app.is_running:
            # push_screen_wait pauses here until the Modal calls dismiss()
            # This allows the Agent to "block" while the User decides.
            result = await self.app.push_screen_wait(ToolConfirmModal(tool_call))
            return result
            
        return False

    async def display_selection_list(self, title: str, items: List[Any]):
        """
        Show a modal list for ANY selection (Provider, Model, etc).
        """
        # 1. robust string conversion
        options = []
        for item in items:
            # If it's a model object/dict, get the name. If it's a string, use it.
            if isinstance(item, dict):
                text = item.get("name", str(item))
            elif hasattr(item, "name"):
                text = getattr(item, "name")
            else:
                text = str(item)
            options.append(text)

        if self.app.is_running:
            # 2. Show the modal
            selected = await self.app.push_screen_wait(SelectionModal(title, options))
            
            # 3. Store result for the NEXT prompt_user call
            if selected:
                self.app.pending_selection = selected

    # Ensure prompt_user is ready to catch the result
    async def prompt_user(self, prompt: str) -> str:
        # Check if we have a "pre-selected" answer from a modal
        if hasattr(self.app, "pending_selection") and self.app.pending_selection:
            result = self.app.pending_selection
            self.app.pending_selection = None
            return result

        # Fallback to normal typing
        if self.app.is_running:
            return await self.app.await_user_input(prompt)
        return ""

    # --- Stubs for required abstract methods ---
    async def close(self): pass
    async def display_startup_banner(self, greeting: str): pass
    async def display_execution_start(self, count: int): pass
    async def display_progress(self, current: int, total: int): pass
    async def display_task_complete(self, summary: str = ""): pass
    async def print_error_stderr(self, message: str): pass
    async def set_auto_confirm(self, value: bool): pass
    async def display_startup_frame(self, frame: str): pass
    async def display_model_list(self, models, current): pass
    async def display_switch_report(self, report, current, target): pass
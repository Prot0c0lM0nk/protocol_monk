from ui.base import UI
from typing import Dict, Any, Union, List
import asyncio


class TextualUI(UI):
    """Bridge between ProtocolAgent and Textual UI."""

    def __init__(self, app):
        self.app = app

    def print_stream(self, text):
        """Stream text to UI (thread-safe)."""
        self.app.call_from_another_thread(self.app.screen.stream_to_ui, text)

    async def confirm_tool_call(
        self, tool_call: Dict, auto_confirm: bool = False
    ) -> Union[bool, Dict]:
        """Block until user approves tool call."""
        if auto_confirm:
            return True

        event = asyncio.Event()
        result_container = {}

        def callback(result):
            result_container["data"] = result
            event.set()

        # Push approval modal to UI
        self.app.call_from_another_thread(
            self.app.push_screen, "approval", tool_call, callback
        )

        # Wait for user to confirm
        await event.wait()
        return result_container["data"]

    def display_tool_result(self, result: Any, tool_name: str = None):
        """Display tool result in UI."""
        self.app.call_from_another_thread(
            self.app.screen.add_message, "tool", result.output
        )

    async def display_tool_call(self, tool_call: Dict, auto_confirm: bool = False):
        """Display a tool call to the user"""
        # Implementation needed
        pass

    async def display_execution_start(self, count: int):
        """Display execution start notification"""
        # Implementation needed
        pass

    async def display_progress(self, current: int, total: int):
        """Display execution progress"""
        # Implementation needed
        pass

    async def display_task_complete(self, summary: str = ""):
        """Display task completion notification"""
        # Implementation needed
        pass

    async def print_error(self, message: str):
        """Display error message"""
        # Implementation needed
        pass

    async def print_warning(self, message: str):
        """Display warning message"""
        # Implementation needed
        pass

    async def print_info(self, message: str):
        """Display info message"""
        # Implementation needed
        pass

    async def set_auto_confirm(self, value: bool):
        """Set auto-confirm mode"""
        # Implementation needed
        pass

    async def display_startup_banner(self, greeting: str):
        """Display startup banner/greeting"""
        # Implementation needed
        pass

    async def display_startup_frame(self, frame: str):
        """Display startup animation frame"""
        # Implementation needed
        pass

    async def prompt_user(self, prompt: str) -> str:
        """Prompt user for input"""
        # Implementation needed
        return ""

    async def print_error_stderr(self, message: str):
        """Print error to stderr"""
        # Implementation needed
        pass

    async def start_thinking(self):
        """Start the thinking/loading animation"""
        # Implementation needed
        pass

    async def display_model_list(self, models: List[Any], current_model: str):
        """Display list of available models"""
        # Implementation needed
        pass

    async def display_switch_report(
        self, report: Any, current_model: str, target_model: str
    ):
        """Display the safety report for a proposed model switch"""
        # Implementation needed
        pass

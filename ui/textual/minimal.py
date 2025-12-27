import sys
import os
import asyncio

# --- FIX: ADD PROJECT ROOT TO PATH ---
# This allows Python to find 'ui.base' even when running this script directly
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
# -------------------------------------

from textual.app import App, ComposeResult
from textual.widgets import Log, Header, Footer
from ui.base import UI


# 1. THE BRIDGE
# This looks like the 'UI' class to the Agent, but talks to Textual
class TextualBridge(UI):
    def __init__(self, app_instance):
        super().__init__()
        self.app = app_instance

    async def print_stream(self, text: str):
        # We use call_from_async to thread-safe update the UI
        self.app.log_widget.write(text)

    async def print_info(self, message: str):
        self.app.log_widget.write(f"[INFO] {message}")

    async def print_error(self, message: str):
        self.app.log_widget.write(f"[ERROR] {message}")

    async def start_thinking(self):
        self.app.log_widget.write("--- Thinking... ---")

    async def stop_thinking(self):
        self.app.log_widget.write("--- Done Thinking ---")

    async def prompt_user(self, prompt: str) -> str:
        # For this test, we just return a dummy value
        self.app.log_widget.write(f"[PROMPT] {prompt}")
        await asyncio.sleep(1)
        return "Test Input"

    # Stubs for abstract methods we aren't testing yet
    async def close(self):
        pass

    async def display_startup_banner(self, greeting: str):
        pass

    async def confirm_tool_call(self, tool_call, auto_confirm=False):
        return True

    async def display_tool_call(self, tool_call, auto_confirm=False):
        pass

    async def display_tool_result(self, result, tool_name):
        pass

    async def display_execution_start(self, count):
        pass

    async def display_progress(self, current, total):
        pass

    async def display_task_complete(self, summary=""):
        pass

    async def print_warning(self, message):
        pass

    async def print_error_stderr(self, message):
        pass

    async def set_auto_confirm(self, value):
        pass

    async def display_startup_frame(self, frame):
        pass

    async def display_model_list(self, models, current):
        pass

    async def display_switch_report(self, report, current, target):
        pass


# 2. THE APP
class MinimalApp(App):
    """The simplest possible Textual app to test the connection."""

    def compose(self) -> ComposeResult:
        yield Header()
        # A simple scrolling log to see if we are getting signals
        self.log_widget = Log()
        yield self.log_widget
        yield Footer()

    async def on_mount(self):
        self.log_widget.write("UI Mounted. Starting Agent...")

        # CREATE THE BRIDGE
        self.ui_bridge = TextualBridge(self)

        # START THE AGENT (Run it as a worker so it doesn't freeze the UI)
        self.run_worker(self.mock_agent_loop(self.ui_bridge))

    # 3. THE MOCK AGENT
    # This simulates exactly what monk.py does
    async def mock_agent_loop(self, ui: UI):
        await asyncio.sleep(1)
        await ui.print_info("Agent Connected!")

        await asyncio.sleep(0.5)
        await ui.start_thinking()

        # Simulate streaming tokens
        words = ["Hello ", "this ", "is ", "Protocol ", "Monk ", "streaming..."]
        for word in words:
            await ui.print_stream(word)
            await asyncio.sleep(0.2)

        await ui.stop_thinking()
        await ui.print_info("Stream complete.")


if __name__ == "__main__":
    app = MinimalApp()
    app.run()

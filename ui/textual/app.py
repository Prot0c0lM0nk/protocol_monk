"""
ui/textual/app.py
"""
import asyncio
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer
from textual.binding import Binding

# Import screens/messages
from .screens.chat_screen import ChatScreen
from .messages import StreamText, AgentMessage, UpdateStatus

# 1. IMPORT THE PROVIDER
from .commands import MonkCommandProvider 

class ProtocolMonkApp(App):
    """
    The Protocol Monk TUI.
    """
    
    CSS_PATH = "styles/orthodox.tcss"
    TITLE = "Protocol Monk ✠"
    
    # 2. REGISTER THE PROVIDER
    # This enables Ctrl+P to find our commands
    COMMANDS = {MonkCommandProvider}  
    
    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit"),
        Binding("ctrl+l", "clear_screen", "Clear"),
        # Textual adds Ctrl+P automatically [cite: 468]
    ]

    def __init__(self):
        super().__init__()
        self.input_future: asyncio.Future = None
        self.input_handler = None

    def set_input_handler(self, handler):
        self.input_handler = handler

    # 3. ADD THE HELPER METHOD
    def trigger_slash_command(self, command: str):
        """
        Called by Command Palette to execute a slash command.
        """
        if self.input_handler:
            # We treat this exactly like the user typed it in the chat box
            self.run_worker(self.input_handler(command))

    # ... (Keep the rest of your existing methods: compose, on_mount, etc.) ...
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield ChatScreen(id="chat_screen")
        yield Footer()

    def on_mount(self) -> None:
        self.notify("Protocol Monk Initialized", title="System")

    async def await_user_input(self, prompt: str) -> str:
        screen = self.query_one(ChatScreen)
        screen.focus_input()
        self.input_future = asyncio.Future()
        return await self.input_future

    def resolve_input(self, value: str):
        if self.input_future and not self.input_future.done():
            self.input_future.set_result(value)
            self.input_future = None
            return

        if self.input_handler:
            self.run_worker(self.input_handler(value))

    def on_stream_text(self, message: StreamText):
        self.query_one(ChatScreen).write_to_log(message.text)

    def on_agent_message(self, message: AgentMessage):
        """Route general agent events (info/error/tools)"""
        screen = self.query_one(ChatScreen)
        display = screen.query_one("ChatDisplay")  # Access display directly

        if message.type == "error":
            # Errors are best shown as tool outputs (Red)
            display.add_tool_output("SYSTEM ERROR", message.data, False)
            
        elif message.type == "info":
            # Info can go to log or notification
            self.notify(message.data)

        elif message.type == "tool_call":
            # Just notify that a tool is starting
            self.notify(f"Calling: {message.data.get('tool', 'unknown')}")

        elif message.type == "tool_result":
            # USE THE NEW WIDGET FOR RESULTS
            data = message.data
            display.add_tool_output(
                tool_name=data.get("name", "Unknown Tool"),
                output=data.get("output", ""),
                success=data.get("success", True)
            )

    def on_update_status(self, message: UpdateStatus):
        screen = self.query_one(ChatScreen)
        if message.key == "thinking":
            if message.value:
                screen.show_loading_indicator()
            else:
                screen.finalize_response()
"""
ui/textual/app.py
The Main Application Container.
Wires the Agent Bridge to the Visual Widgets.
"""
import asyncio
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer
from textual.binding import Binding

# Import the screen we just created
from .screens.chat_screen import ChatScreen
from .messages import StreamText, AgentMessage, UpdateStatus

class ProtocolMonkApp(App):
    """
    The Protocol Monk TUI.
    """
    
    # Corrected to point to .tcss
    CSS_PATH = "styles/orthodox.tcss"
    TITLE = "Protocol Monk ✠"
    
    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit"),
        Binding("ctrl+l", "clear_screen", "Clear"),
    ]

    def __init__(self):
        super().__init__()
        self.input_future = None
        self.input_handler = None

    def compose(self) -> ComposeResult:
        """Build the UI structure."""
        yield Header(show_clock=True)
        yield ChatScreen(id="chat_screen")
        yield Footer()

    def on_mount(self) -> None:
        self.notify("Protocol Monk Initialized", title="System")

    # --- INPUT HANDLING (The Pause/Resume Logic) ---
    def set_input_handler(self, handler):
        self.input_handler = handler

    async def await_user_input(self, prompt: str) -> str:
        """
        Called by the Bridge (Agent).
        Waits for the user to type in the ChatScreen.
        """
        # Focus the input widget
        screen = self.query_one(ChatScreen)
        screen.focus_input()
        
        # Create a future that the ChatScreen will resolve
        self.input_future = asyncio.Future()
        
        # This await blocks the Agent until resolve_input is called
        return await self.input_future

    async def resolve_input(self, value: str):
        """Called by ChatScreen when user hits Enter."""
        
        # CASE 1: The Agent is paused waiting for input (Mid-Loop Prompt)
        if self.input_future and not self.input_future.done():
            self.input_future.set_result(value)
            self.input_future = None
            return

        # CASE 2: The Agent is idle, this is a new request
        if self.input_handler:
            # Run the handler as a worker so we don't block the UI
            self.run_worker(self.input_handler(value))

    # --- MESSAGE HANDLERS (From Bridge) ---

    def on_stream_text(self, message: StreamText):
        """Route streaming text to the chat screen."""
        self.query_one(ChatScreen).write_to_log(message.text)

    def on_agent_message(self, message: AgentMessage):
        """Route general agent events (info/error/tools)"""
        # For now, we just dump these to the log. 
        # Later we will route tool_calls to specific widgets.
        screen = self.query_one(ChatScreen)
        
        if message.type == "error":
            screen.write_to_log(f"[bold red]ERROR: {message.data}[/]")
        elif message.type == "info":
            screen.write_to_log(f"[dim]{message.data}[/]")
        elif message.type == "tool_call":
            screen.write_to_log(f"[bold cyan]Tool Call: {message.data.get('tool', 'unknown')}[/]")
        elif message.type == "tool_result":
            screen.write_to_log(f"[cyan]Result: {message.data.get('output', '')}[/]")

    def on_update_status(self, message: UpdateStatus):
        """Route status updates (thinking/loading)"""
        screen = self.query_one(ChatScreen)
        
        if message.key == "thinking":
            if message.value:
                # Started thinking
                screen.show_loading_indicator()
            else:
                # Stopped thinking -> Finish the stream
                screen.finalize_response()
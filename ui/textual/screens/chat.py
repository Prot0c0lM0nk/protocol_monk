from textual import on
from textual.containers import Container, VerticalScroll
from textual.screen import Screen
from textual.widgets import Label

from ui.textual.widgets.inputs import InputPanel
from ui.textual.widgets.messages import ChatMessage


class ChatScreen(Screen):
    """Main chat screen."""

    def __init__(self):
        super().__init__()
        self.mount(
            Container(
                Label("Status: Waiting for input...", id="status"),
                VerticalScroll(id="messages"),
                InputPanel(id="input"),
                id="main",
            )
        )

    def on_mount(self):
        """Initialize components after mounting."""
        self.messages = self.query_one("#messages")
        self.status = self.query_one("#status")
        self.add_message("assistant", "Hello! I'm ready to assist you.")

    def stream_to_ui(self, text):
        """Stream text to UI (appends to last message)."""
        messages = self.query(".message")
        if messages:
            last_msg = messages[-1]
            if last_msg.has_class("assistant"):
                last_msg.append_text(text)
                return
        self.add_message("assistant", text)

    def add_message(self, role, content):
        """Mount a new message."""
        self.messages.mount(ChatMessage(role, content))

    @on(InputPanel.Submit)
    def on_input_panel_submit(self, event):
        """Handle user input submission."""
        text = event.text
        self.add_message("user", text)
        self.run_worker(self.app.agent.process_request(text), thread=True)

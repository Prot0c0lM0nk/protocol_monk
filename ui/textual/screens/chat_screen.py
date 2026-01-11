"""
ui/textual/screens/chat_screen.py
Main chat screen for the agent interface
"""

from textual.app import ComposeResult
from textual.screen import Screen
from textual.containers import Vertical, Horizontal
from textual.widgets import Header, Button

from ..widgets.chat_display import ChatDisplay
from ..widgets.chat_input import ChatInput
from ..widgets.status_bar import StatusBar


class ChatScreen(Screen):
    """
    Main chat screen
    Displays conversation with agent and handles user input
    """

    BINDINGS = [
        ("ctrl+c", "app.request_quit", "Quit"),
        ("ctrl+s", "app.switch_mode('settings')", "Settings"),
        ("ctrl+h", "app.switch_mode('help')", "Help"),
    ]

    def compose(self) -> ComposeResult:
        """Compose the chat screen"""
        yield Header()
        with Vertical():
            yield ChatDisplay(id="chat-display")
            with Horizontal(id="input-area"):
                yield ChatInput(
                    placeholder="Type your message...",
                    id="user-input"
                )
                yield Button("Send", variant="primary", id="send-button")
        yield StatusBar(id="status-bar")

    def on_mount(self) -> None:
        """Called when screen is mounted"""
        # Focus input widget
        input_widget = self.query_one("#user-input", ChatInput)
        input_widget.focus()
        
    def on_chat_input_user_submitted(self, event: ChatInput.UserSubmitted) -> None:
        """
        Handle user input submission
        Event posted by ChatInput when user presses Enter
        """
        user_message = event.value
        if user_message.strip():
            # Add user message to chat display
            chat_display = self.query_one("#chat-display", ChatDisplay)
            chat_display.add_message("user", user_message)

            # Process with agent (runs in worker)
            self.app.process_agent_request(user_message)

            # Clear input
            event.input_widget.value = ""

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """
        Handle send button press
        """
        if event.button.id == "send-button":
            input_widget = self.query_one("#user-input", ChatInput)
            user_message = input_widget.value
            if user_message.strip():
                # Add user message to chat display
                chat_display = self.query_one("#chat-display", ChatDisplay)
                chat_display.add_message("user", user_message)

                # Process with agent (runs in worker)
                self.app.process_agent_request(user_message)

                # Clear input
                input_widget.value = ""
                input_widget.focus()
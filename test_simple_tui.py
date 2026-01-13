#!/usr/bin/env python3
"""
Simple Textual TUI Test - Minimal Version
Tests basic Textual functionality without agent integration
"""

from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Static, TextArea, Button
from textual.containers import Vertical, Horizontal
from textual import events


class SimpleChatApp(App):
    """Minimal chat app to test Textual basics"""
    
    CSS = """
    Screen {
        background: #1a1a1a;
    }
    
    Header {
        background: #2a2a2a;
        color: #00ff00;
    }
    
    Footer {
        background: #2a2a2a;
        color: #00ff00;
    }
    
    TextArea {
        background: #2a2a2a;
        color: #ffffff;
        border: solid #00ff00;
    }
    
    Button {
        background: #00ff00;
        color: #000000;
    }
    
    #chat-area {
        height: 80%;
        background: #1a1a1a;
        border: solid #00ff00;
        padding: 1;
    }
    """

    def compose(self) -> ComposeResult:
        yield Header()
        
        with Vertical():
            yield Static("Protocol Monk Test", id="chat-area")
            
            with Horizontal():
                yield TextArea(placeholder="Type a message...", id="msg-input")
                yield Button("Send", id="send-btn")
        
        yield Footer()

    def on_mount(self) -> None:
        self.title = "Protocol Monk Test"
        self.sub_title = "Minimal TUI Test"

    def on_button_pressed(self, event) -> None:
        if event.button.id == "send-btn":
            self.send_message()

    def on_key(self, event) -> None:
        if event.key == "enter":
            self.send_message()
    def on_key(self, event: events.Key) -> None:
        if event.key == "enter":
            self.send_message()

    def send_message(self) -> None:
        """Handle message sending"""
        text_area = self.query_one("#msg-input", TextArea)
        message = text_area.text.strip()
        
        if message:
            chat_area = self.query_one("#chat-area", Static)
            chat_area.update(f"You said: {message}")
            text_area.text = ""


if __name__ == "__main__":
    app = SimpleChatApp()
    app.run()
#!/usr/bin/env python3
"""
Protocol Monk - Basic Chat Interface
A simple Textual UI that connects to the MockEventAgent
"""

import sys
import os
from pathlib import Path

# Add parent directory to path to import agent module
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from textual.app import App, ComposeResult
from textual.containers import Vertical, Horizontal
from textual.widgets import (
    Static, Input, Footer, Header, Button,
    RichLog, Label
)
from textual.reactive import reactive
from textual import events
from agent.events import get_event_bus, AgentEvents
from agent.mock_event_agent import MockEventAgent
import asyncio


class StatusBar(Static):
    """Status bar showing current agent state."""

    status = reactive("idle")
    model = reactive("mock-model")
    provider = reactive("mock-provider")

    def watch_status(self, old_status: str, new_status: str) -> None:
        """Update status display."""
        self.update(f"Status: {new_status} | Model: {self.model} ({self.provider})")

    def update_model(self, model: str, provider: str) -> None:
        """Update model info."""
        self.model = model
        self.provider = provider


class ChatContainer(Static):
    """Container for chat messages."""

    def on_mount(self) -> None:
        """Initialize chat container."""
        self.messages = []

    def add_message(self, role: str, content: str, style: str = "") -> None:
        """Add a message to the chat."""
        # Create message widget
        message = MessageBubble(role, content, style)
        self.mount(message)
        message.scroll_visible()


class MessageBubble(Static):
    """A single message bubble."""

    def __init__(self, role: str, content: str, style: str = ""):
        super().__init__()
        self.role = role
        self.content = content
        self.style = style

    def on_mount(self) -> None:
        """Render message on mount."""
        if self.role == "user":
            prefix = "👤 You:"
            self.add_class("user-message")
        elif self.role == "assistant":
            prefix = "🤖 Protocol Monk:"
            self.add_class("assistant-message")
        elif self.role == "system":
            prefix = "ℹ️ System:"
            self.add_class("system-message")
        elif self.role == "tool":
            prefix = "🔧 Tool:"
            self.add_class("tool-message")
        elif self.role == "error":
            prefix = "❌ Error:"
            self.add_class("error-message")
        else:
            prefix = f"{self.role}:"

        self.update(f"{prefix}\n{self.content}")


class ProtocolMonkChat(App):
    """Main chat application."""

    CSS = """
    Screen {
        layout: vertical;
    }

    StatusBar {
        background: #3b4252;
        color: #eceff4;
        padding: 0 1;
        height: 3;
        dock: top;
    }

    ChatContainer {
        height: 1fr;
        overflow-y: auto;
        padding: 1;
    }

    MessageBubble {
        margin: 1 0;
        padding: 1;
        border: solid gray;
    }

    .user-message {
        background: #5e81ac;
        color: white;
    }

    .assistant-message {
        background: #4c566a;
        color: #eceff4;
    }

    .system-message {
        background: #88c0d0;
        color: #2e3440;
    }

    .tool-message {
        background: #a3be8c;
        color: #2e3440;
    }

    .error-message {
        background: #bf616a;
        color: #eceff4;
    }

    InputArea {
        height: 3;
        dock: bottom;
        padding: 0 1;
    }

    Input {
        dock: left;
    }

    Button {
        margin-left: 1;
    }
    """

    BINDINGS = [
        ("ctrl+c", "quit", "Quit"),
        ("ctrl+p", "command_palette", "Commands"),
    ]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.event_bus = get_event_bus()
        self.agent = MockEventAgent(self.event_bus)
        self.current_response = ""
        self.thinking = False

    def compose(self) -> ComposeResult:
        """Compose the UI."""
        yield Header()
        yield StatusBar()
        yield ChatContainer(id="chat")
        yield Horizontal(
            Input(placeholder="Type a message...", id="message_input"),
            Button("Send", variant="primary", id="send_button"),
            id="input_area"
        )
        yield Footer()

    def on_mount(self) -> None:
        """Initialize the app."""
        # Subscribe to all agent events
        self._subscribe_to_events()

        # Start the mock agent
        asyncio.create_task(self._start_agent())

    def _subscribe_to_events(self) -> None:
        """Subscribe to all agent events."""
        # Info messages
        self.event_bus.subscribe(
            AgentEvents.INFO.value,
            self._on_info_event
        )

        # Error messages
        self.event_bus.subscribe(
            AgentEvents.ERROR.value,
            self._on_error_event
        )

        # Warning messages
        self.event_bus.subscribe(
            AgentEvents.WARNING.value,
            self._on_warning_event
        )

        # Thinking events
        self.event_bus.subscribe(
            AgentEvents.THINKING_STARTED.value,
            self._on_thinking_started
        )

        self.event_bus.subscribe(
            AgentEvents.THINKING_STOPPED.value,
            self._on_thinking_stopped
        )

        # Streaming response
        self.event_bus.subscribe(
            AgentEvents.STREAM_CHUNK.value,
            self._on_stream_chunk
        )

        # Response complete
        self.event_bus.subscribe(
            AgentEvents.RESPONSE_COMPLETE.value,
            self._on_response_complete
        )

        # Status changes
        self.event_bus.subscribe(
            AgentEvents.STATUS_CHANGED.value,
            self._on_status_changed
        )

        # Model/provider switching
        self.event_bus.subscribe(
            AgentEvents.MODEL_SWITCHED.value,
            self._on_model_switched
        )

        self.event_bus.subscribe(
            AgentEvents.PROVIDER_SWITCHED.value,
            self._on_provider_switched
        )

        # Tool events
        self.event_bus.subscribe(
            AgentEvents.TOOL_EXECUTION_START.value,
            self._on_tool_start
        )

        self.event_bus.subscribe(
            AgentEvents.TOOL_RESULT.value,
            self._on_tool_result
        )

        self.event_bus.subscribe(
            AgentEvents.TOOL_ERROR.value,
            self._on_tool_error
        )

        # Command results
        self.event_bus.subscribe(
            AgentEvents.COMMAND_RESULT.value,
            self._on_command_result
        )

    async def _start_agent(self) -> None:
        """Start the mock agent."""
        await asyncio.sleep(1)  # Wait for UI to mount
        await self.agent.emit_all_events()

    # Event handlers

    def _on_info_event(self, data: dict) -> None:
        """Handle info event."""
        message = data.get("message", "")
        context = data.get("context", "")

        # Skip user input messages (we already display them)
        if context == "user_input":
            return

        # Display system messages
        if context in ["startup", "completion", "command_simulation"]:
            chat = self.query_one("#chat", ChatContainer)
            chat.add_message("system", message)

    def _on_error_event(self, data: dict) -> None:
        """Handle error event."""
        message = data.get("message", "")
        chat = self.query_one("#chat", ChatContainer)
        chat.add_message("error", message)

    def _on_warning_event(self, data: dict) -> None:
        """Handle warning event."""
        message = data.get("message", "")
        chat = self.query_one("#chat", ChatContainer)
        chat.add_message("system", f"⚠️ {message}")

    def _on_thinking_started(self, data: dict) -> None:
        """Handle thinking started."""
        self.thinking = True
        self.current_response = ""
        status_bar = self.query_one(StatusBar)
        status_bar.status = "thinking"

    def _on_thinking_stopped(self, data: dict) -> None:
        """Handle thinking stopped."""
        self.thinking = False
        status_bar = self.query_one(StatusBar)
        status_bar.status = "idle"

    def _on_stream_chunk(self, data: dict) -> None:
        """Handle stream chunk."""
        chunk = data.get("chunk", "")
        thinking = data.get("thinking", "")

        if thinking:
            # Display thinking content
            chat = self.query_one("#chat", ChatContainer)
            chat.add_message("system", f"🤔 {thinking}")
        elif chunk:
            # Append to current response
            self.current_response += chunk
            # Update last message if it's from assistant
            chat = self.query_one("#chat", ChatContainer)
            if chat.messages and chat.messages[-1].role == "assistant":
                chat.messages[-1].update(f"🤖 Protocol Monk:\n{self.current_response}")
            else:
                chat.add_message("assistant", self.current_response)

    def _on_response_complete(self, data: dict) -> None:
        """Handle response complete."""
        content = data.get("content", "")
        tokens = data.get("tokens", 0)
        chat = self.query_one("#chat", ChatContainer)
        chat.add_message("system", f"✓ Response complete ({tokens} tokens)")

    def _on_status_changed(self, data: dict) -> None:
        """Handle status changed."""
        status = data.get("status", "idle")
        message = data.get("message", "")
        status_bar = self.query_one(StatusBar)
        status_bar.status = status

    def _on_model_switched(self, data: dict) -> None:
        """Handle model switched."""
        old_model = data.get("old_model", "")
        new_model = data.get("new_model", "")
        status_bar = self.query_one(StatusBar)
        status_bar.update_model(new_model, status_bar.provider)
        chat = self.query_one("#chat", ChatContainer)
        chat.add_message("system", f"🔄 Model switched: {old_model} → {new_model}")

    def _on_provider_switched(self, data: dict) -> None:
        """Handle provider switched."""
        old_provider = data.get("old_provider", "")
        new_provider = data.get("new_provider", "")
        status_bar = self.query_one(StatusBar)
        status_bar.update_model(status_bar.model, new_provider)
        chat = self.query_one("#chat", ChatContainer)
        chat.add_message("system", f"🔄 Provider switched: {old_provider} → {new_provider}")

    def _on_tool_start(self, data: dict) -> None:
        """Handle tool execution start."""
        tool_name = data.get("tool_name", "")
        parameters = data.get("parameters", {})
        chat = self.query_one("#chat", ChatContainer)
        chat.add_message("tool", f"Executing: {tool_name}\nParameters: {parameters}")

    def _on_tool_result(self, data: dict) -> None:
        """Handle tool result."""
        tool_name = data.get("tool_name", "")
        output = data.get("output", "")
        success = data.get("success", False)
        chat = self.query_one("#chat", ChatContainer)
        status = "✓" if success else "✗"
        chat.add_message("tool", f"{status} {tool_name} result:\n{output}")

    def _on_tool_error(self, data: dict) -> None:
        """Handle tool error."""
        tool_name = data.get("tool_name", "")
        error = data.get("error", "")
        chat = self.query_one("#chat", ChatContainer)
        chat.add_message("error", f"Tool error ({tool_name}): {error}")

    def _on_command_result(self, data: dict) -> None:
        """Handle command result."""
        command = data.get("command", "")
        success = data.get("success", False)
        message = data.get("message", "")
        chat = self.query_one("#chat", ChatContainer)
        status = "✓" if success else "✗"
        chat.add_message("system", f"{status} Command: {command}\n{message}")

    # UI handlers

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press."""
        if event.button.id == "send_button":
            self._send_message()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle input submission."""
        if event.input.id == "message_input":
            self._send_message()

    def _send_message(self) -> None:
        """Send user message."""
        input_widget = self.query_one("#message_input", Input)
        message = input_widget.value.strip()

        if message:
            # Display user message
            chat = self.query_one("#chat", ChatContainer)
            chat.add_message("user", message)

            # Clear input
            input_widget.value = ""


if __name__ == "__main__":
    app = ProtocolMonkChat()
    app.run()
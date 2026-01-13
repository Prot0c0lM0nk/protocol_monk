"""
ui/textual/app.py
The Protocol Monk Textual Application
"""

import asyncio
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Header, Footer

from .screens.main_chat import MainChatScreen
from .interface import TextualUI
from .messages import (
    AgentStreamChunk,
    AgentThinkingStatus,
    AgentToolResult,
    AgentSystemMessage,
)


class ProtocolMonkApp(App):
    """Protocol Monk - The Oracle of the Holy Light"""

    CSS_PATH = [
        "styles/main.tcss",
        "styles/components.tcss",
        "styles/chat.tcss"
    ]

    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit", show=False),
        Binding("ctrl+p", "command_palette", "Commands"),
        Binding("f1", "show_help", "Help"),
    ]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.textual_ui = None  # Will hold the TextualUI bridge instance
        self._input_future = None

    def compose(self) -> ComposeResult:
        """Create the app layout."""
        yield Header()
        yield MainChatScreen()
        yield Footer()

    def on_mount(self) -> None:
        """Initialize the app after mounting."""
        # Set up message handlers but don't push extra screens
        self.notify("Protocol Monk TUI Ready", severity="information")
        self.push_screen(MainChatScreen())

    def set_agent(self, agent):
        """
        Connect the agent to the UI bridge.
        This is called from main.py after agent creation.
        """
        # Create the UI bridge that connects events to this app
        self.textual_ui = TextualUI(self)
        
        # Store the agent reference for potential direct access
        self.agent = agent
        
        # If the agent has a UI reference, update it to use our bridge
        if hasattr(agent, 'ui') and agent.ui:
            agent.ui = self.textual_ui

    async def get_user_input_wait(self) -> str:
        """
        Wait for user input from the chat screen.
        This is called by the TextualUI bridge when agent needs input.
        """
        # Get the current chat screen
        screen = self.screen
        if hasattr(screen, 'await_user_input'):
            return await screen.await_user_input()
        return ""

    async def push_screen_wait(self, screen):
        """
        Push a modal screen and wait for its result.
        This is called by the TextualUI bridge for tool confirmations.
        """
        return await super().push_screen_wait(screen)

    def call_from_child_submit(self, text: str) -> None:
        """
        Called by InputBar when user submits a message.
        Routes the message to the agent through the UI bridge.
        """
        # If we have a UI bridge, use it to process the input
        if self.textual_ui:
            # Create a task to handle the agent processing
            asyncio.create_task(self._process_user_input(text))
        else:
            # Fallback to mock behavior if no bridge
            asyncio.create_task(self._handle_mock_response(text))

    async def _process_user_input(self, text: str):
        """Process user input through the agent."""
        screen = None  # Initialize screen variable
        
        try:
            # Get screen safely - it might not be available during app initialization
            try:
                screen = self.screen
            except Exception:
                # If no screen is available, just process the text without UI updates
                if hasattr(self, 'agent') and self.agent:
                    # Start agent on first use if not already running
                    if not hasattr(self, 'agent_task') or self.agent_task is None:
                        self.agent_task = asyncio.create_task(self.agent.run())
                    
                    # Process the user request
                    await self.agent.process_request(text)
                return

            # Add user message to chat
            if hasattr(screen, 'add_user_message'):
                await screen.add_user_message(text)

            # Show thinking status
            if hasattr(screen, 'show_thinking'):
                screen.show_thinking(True)

            # Process through agent if available
            if hasattr(self, 'agent') and self.agent:
                # Start agent on first use if not already running
                if not hasattr(self, 'agent_task') or self.agent_task is None:
                    self.agent_task = asyncio.create_task(self.agent.run())
                
                # Process the user request
                await self.agent.process_request(text)
            else:
                # Fallback response
                await self._handle_mock_response(text)

        except Exception as e:
            self.notify(f"Error processing input: {e}", severity="error")
        finally:
            # Hide thinking status
            if screen and hasattr(screen, 'show_thinking'):
                screen.show_thinking(False)
    async def _handle_mock_response(self, text: str):
        """Handle mock response when no agent is connected."""
        screen = self.screen
        if hasattr(screen, 'add_ai_message'):
            await screen.add_ai_message(f"**Mock Response:** I received your message: *{text}*")

    # --- Message Handlers for Agent Events ---

    def on_agent_stream_chunk(self, message: AgentStreamChunk) -> None:
        """Handle streaming text from agent."""
        screen = self.screen
        if hasattr(screen, 'add_stream_chunk'):
            screen.add_stream_chunk(message.chunk)

    def on_agent_thinking_status(self, message: AgentThinkingStatus) -> None:
        """Handle thinking status updates."""
        screen = self.screen
        if hasattr(screen, 'show_thinking'):
            screen.show_thinking(message.is_thinking)

    def on_agent_tool_result(self, message: AgentToolResult) -> None:
        """Handle tool execution results."""
        screen = self.screen
        if hasattr(screen, 'add_tool_result'):
            screen.add_tool_result(message.tool_name, message.result)

    def on_agent_system_message(self, message: AgentSystemMessage) -> None:
        """Handle system messages (info, error, warnings)."""
        if message.type == "error":
            self.notify(message.message, severity="error")
        elif message.type == "info":
            self.notify(message.message, severity="information")
        elif message.type == "warning":
            self.notify(message.message, severity="warning")
        elif message.type == "response_complete":
            screen = self.screen
            if hasattr(screen, 'finalize_response'):
                screen.finalize_response()


if __name__ == "__main__":
    app = ProtocolMonkApp()
    app.run()
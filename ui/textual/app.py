"""
The core Textual application for Protocol Monk.

This module implements the main TUI with worker isolation for the ProtocolAgent.
"""

from textual.app import App
from textual.worker import Worker, WorkerState
from textual import on
from typing import Optional

from agent.monk import ProtocolAgent
from ui.textual.interface import (
    TextualUI,
    StreamMsg,
    RequestInputMsg,
    RequestApprovalMsg,
)
from ui.textual.screens.chat import ChatScreen
from ui.textual.screens.approval import ApprovalScreen


class MonkCodeTUI(App):
    """The main Textual application for Protocol Monk."""

    CSS_PATH = "styles.tcss"  # Path relative to working directory

    def __init__(self, agent: Optional[ProtocolAgent] = None, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.agent = agent or ProtocolAgent()
        self.bridge: Optional[TextualUI] = None

    def on_mount(self) -> None:
        """Initialize the UI bridge and start configuration."""
        self.bridge = TextualUI(self)
        self.agent.ui = self.bridge
        self._start_configuration()

    async def _start_configuration(self) -> None:
        """Start the configuration flow before the agent."""
        from ui.textual.screens.config import ConfigScreen
        
        # Get available providers and models from agent
        providers = list(self.agent.available_providers.keys())
        models = list(self.agent.available_models.keys())
        
        config = await self.push_screen_wait(
            ConfigScreen({
                "provider": providers,
                "model": models
            })
        )
        
        if config:
            # Apply configuration to agent
            self.agent.config.working_directory = config.get("directory", "")
            self.agent.config.provider = config.get("provider", providers[0])
            self.agent.config.model = config.get("model", models[0])
            
            # Start the agent worker after configuration
            self.run_agent_worker()
            
            # Push the chat screen
            await self.push_screen(ChatScreen())

    def run_agent_worker(self) -> None:
        """Start the Agent in a background worker."""
        self.run_worker(self._agent_loop, exclusive=True, thread=False)

    async def _agent_loop(self) -> None:
        """The main Agent processing loop."""
        await self.agent.process_request("Start")

    @on(RequestInputMsg)
    async def on_request_input(self, message: RequestInputMsg) -> None:
        """Handle request for user input."""
        chat_screen = ChatScreen(message.prompt)
        await self.push_screen(chat_screen)
        chat_screen.focus_input()

    @on(ChatScreen.InputSubmitted)
    async def on_input_submitted(self, message: ChatScreen.InputSubmitted) -> None:
        """Handle user input submission."""
        if self.bridge:
            self.bridge.input_response = message.value
            self.bridge.input_event.set()

    @on(RequestApprovalMsg)
    async def on_request_approval(self, message: RequestApprovalMsg) -> None:
        """Handle request for tool call approval."""
        if self.bridge:
            result = await self.push_screen_wait(ApprovalScreen(message.tool_call))
            self.bridge.approval_response = result
            self.bridge.approval_event.set()

    @on(StreamMsg)
    def on_stream_message(self, message: StreamMsg) -> None:
        """Handle streaming text from the Agent."""
        if self.screen and hasattr(self.screen, "update_stream"):
            self.screen.update_stream(message.text)

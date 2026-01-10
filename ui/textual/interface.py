import asyncio
from typing import Any, Dict, Optional

from agent.events import AgentEvents, get_event_bus
from ui.textual.messages import (
    StreamChunkMsg,
    ToolResultMsg,
    AgentLogMsg,
    ToolConfirmationRequestMsg,
    StatusUpdateMsg,
    ThinkingStatusMsg,
)
from ui.textual.screens import ToolConfirmationScreen


class TextualUI:
    """
    Bridge between the Protocol Monk Agent (Background Task) and Textual App (Main Thread).
    """

    def __init__(self, app):
        """
        Args:
            app: The running ProtocolMonkApp instance.
        """
        self.app = app
        self.event_bus = get_event_bus()

        # Queue for passing user input from UI -> Agent
        self.input_queue = asyncio.Queue()

        # Subscribe to all relevant agent events
        self._setup_event_listeners()

    def _setup_event_listeners(self):
        """Map AgentEvents to Textual Messages."""
        self.event_bus.subscribe(AgentEvents.STREAM_CHUNK.value, self._on_stream_chunk)
        self.event_bus.subscribe(AgentEvents.TOOL_RESULT.value, self._on_tool_result)
        self.event_bus.subscribe(AgentEvents.ERROR.value, self._on_error)
        self.event_bus.subscribe(AgentEvents.WARNING.value, self._on_warning)
        self.event_bus.subscribe(AgentEvents.INFO.value, self._on_info)
        self.event_bus.subscribe(
            AgentEvents.THINKING_STARTED.value, self._on_thinking_start
        )
        self.event_bus.subscribe(
            AgentEvents.THINKING_STOPPED.value, self._on_thinking_stop
        )

        # Note: We do not subscribe to confirm_tool here because
        # ToolExecutor calls our confirm_tool_execution() method directly.

    # --- BLOCKING METHODS CALLED BY AGENT ---

    async def get_input(self) -> str:
        """
        Pauses the Agent until the User submits text in the TUI.
        """
        # Wait for the App to put something in the queue
        return await self.input_queue.get()

    async def confirm_tool_execution(self, tool_data: Dict[str, Any]) -> bool:
        """
        Pauses the Agent, triggers a Modal in the TUI, and waits for Yes/No.
        """
        # We instantiate the screen with the data provided by the agent
        screen = ToolConfirmationScreen(tool_data)

        # push_screen_wait is a coroutine on the App that pushes the screen
        # and waits for it to be dismissed with a result.
        return await self.app.push_screen_wait(screen)

    # --- EVENT HANDLERS (Background -> UI) ---

    async def _on_stream_chunk(self, data: Dict[str, Any]):
        chunk = data.get("chunk") or data.get("thinking")
        if chunk:
            self.app.post_message(StreamChunkMsg(chunk))

    async def _on_tool_result(self, data: Dict[str, Any]):
        result = data.get("result")
        tool_name = data.get("tool_name", "Unknown")
        # Extract output string safely
        output = result.output if hasattr(result, "output") else str(result)
        self.app.post_message(ToolResultMsg(tool_name, output))

    async def _on_error(self, data: Dict[str, Any]):
        self.app.post_message(
            AgentLogMsg("error", data.get("message", "Unknown Error"))
        )

    async def _on_warning(self, data: Dict[str, Any]):
        self.app.post_message(
            AgentLogMsg("warning", data.get("message", "Unknown Warning"))
        )

    async def _on_info(self, data: Dict[str, Any]):
        self.app.post_message(AgentLogMsg("info", data.get("message", "")))

    async def _on_thinking_start(self, data: Dict[str, Any]):
        self.app.post_message(ThinkingStatusMsg(True))

    async def _on_thinking_stop(self, data: Dict[str, Any]):
        self.app.post_message(ThinkingStatusMsg(False))

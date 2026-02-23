"""Protocol Monk Textual MVP app (no slash command features)."""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any, Iterable

from textual.app import App, SystemCommand
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Input

from protocol_monk.agent.structs import UserRequest
from protocol_monk.protocol.events import EventTypes
from protocol_monk.ui.textual.messages import (
    AgentResponseComplete,
    AgentStatusUpdate,
    AgentStreamChunk,
    AgentSystemMessage,
    AgentToolResult,
)
from protocol_monk.ui.textual.screens.main_chat import MainChatScreen
from protocol_monk.ui.textual.screens.modals.tool_confirm import ToolConfirmModal


class ProtocolMonkTextualApp(App):
    CSS_PATH = [
        "styles/main.tcss",
        "styles/components.tcss",
        "styles/chat.tcss",
    ]
    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit", show=False),
        Binding("ctrl+c", "quit", "Quit", show=False),
        Binding("ctrl+p", "command_palette", "Commands"),
    ]

    def __init__(
        self,
        bus: Any,
        bridge: Any = None,
        mock_agent: Any = None,
        settings: Any = None,
    ):
        super().__init__()
        self.bus = bus
        self.bridge = bridge
        self.mock_agent = mock_agent
        self.settings = settings
        self._agent_status = "idle"

    def compose(self):
        yield from ()

    async def on_mount(self) -> None:
        self.push_screen(MainChatScreen())

        # Seed status bar with runtime provider/model when available.
        screen = self._chat_screen()
        if screen is not None:
            provider = getattr(self.settings, "llm_provider", None)
            model = getattr(self.settings, "active_model_name", None)
            auto_confirm = bool(getattr(self.settings, "auto_confirm", False))
            working_dir = getattr(self.settings, "workspace_root", None)
            screen.update_status_bar(
                "idle",
                "Ready",
                provider=provider,
                model=model,
                auto_confirm=auto_confirm,
                working_dir=str(working_dir) if working_dir else None,
            )

        # Start event subscribers before user interaction to avoid dropping early events.
        if self.bridge is not None:
            await self.bridge.start()
        if self.mock_agent is not None:
            await self.mock_agent.start()

    def action_quit(self) -> None:
        self.exit()

    def get_system_commands(self, screen: Screen) -> Iterable[SystemCommand]:
        yield from super().get_system_commands(screen)
        yield SystemCommand(
            "Refresh Status Bar",
            "Refresh context and token metrics",
            self.action_refresh_status_bar,
        )

    def action_refresh_status_bar(self) -> None:
        if self.bus is None:
            self.notify(
                "Event bus unavailable; cannot refresh status.", severity="warning"
            )
            return
        asyncio.create_task(self._emit_system_command({"command": "refresh_status"}))
        self.notify("Requested status refresh", severity="information")

    def _chat_screen(self) -> MainChatScreen | None:
        current = self.screen
        if isinstance(current, MainChatScreen):
            return current
        try:
            return self.query_one(MainChatScreen)
        except Exception:
            return None

    async def push_screen_wait(self, screen: Screen) -> Any:
        """Reference-style linear screen waiter used for tool confirmation modals."""
        wait_future: asyncio.Future[Any] = asyncio.get_running_loop().create_future()

        def _callback(result: Any) -> None:
            if not wait_future.done():
                wait_future.set_result(result)

        self.push_screen(screen, callback=_callback)
        return await wait_future

    async def request_tool_confirmation(self, tool_name: str, parameters: dict) -> str:
        modal = ToolConfirmModal(tool_name, parameters)

        try:
            decision = await self.push_screen_wait(modal)
        except Exception:
            self.notify(
                "Tool approval dialog failed; rejecting by default.", severity="error"
            )
            return "rejected"

        if decision in {"approved", "approved_auto", "rejected"}:
            return decision
        return "rejected"

    def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if not text:
            return
        if self._agent_status != "idle":
            self.notify(
                "Agent is busy; wait for idle before sending another message.",
                severity="warning",
            )
            return

        screen = self._chat_screen()
        if screen is not None:
            asyncio.create_task(screen.add_user_message(text))

        payload = UserRequest(
            text=text,
            source="textual",
            request_id=str(uuid.uuid4()),
            timestamp=time.time(),
        )
        asyncio.create_task(self._emit_user_input(payload))

    async def _emit_user_input(self, payload: UserRequest) -> None:
        try:
            await self.bus.emit(EventTypes.USER_INPUT_SUBMITTED, payload)
        except Exception:
            self.notify("Failed to dispatch user input to agent.", severity="error")

    async def _emit_system_command(self, payload: dict) -> None:
        try:
            await self.bus.emit(EventTypes.SYSTEM_COMMAND_ISSUED, payload)
        except Exception:
            self.notify("Failed to dispatch system command.", severity="error")

    def on_agent_stream_chunk(self, message: AgentStreamChunk) -> None:
        screen = self._chat_screen()
        if screen is None:
            return
        screen.add_stream_chunk(
            message.chunk,
            is_thinking=message.channel == "thinking",
            pass_id=message.pass_id,
            sequence=message.sequence,
        )

    def on_agent_status_update(self, message: AgentStatusUpdate) -> None:
        screen = self._chat_screen()
        if screen is None:
            return
        self._agent_status = message.status
        screen.update_status_bar(
            message.status,
            message.detail,
            provider=message.provider,
            model=message.model,
            auto_confirm=message.auto_confirm,
            working_dir=message.working_dir,
            message_count=message.message_count,
            total_tokens=message.total_tokens,
            context_limit=message.context_limit,
            loaded_files_count=message.loaded_files_count,
        )
        screen.show_thinking(message.status == "thinking", detail=message.detail)

    def on_agent_tool_result(self, message: AgentToolResult) -> None:
        screen = self._chat_screen()
        if screen is None:
            return
        screen.add_tool_result(message.payload)

    def on_agent_response_complete(self, message: AgentResponseComplete) -> None:
        screen = self._chat_screen()
        if screen is None:
            return
        screen.finalize_response(pass_id=message.pass_id)

    def on_agent_system_message(self, message: AgentSystemMessage) -> None:
        screen = self._chat_screen()
        if screen is None:
            return

        if message.level in {"warning", "error"}:
            self.notify(message.message, severity=message.level)

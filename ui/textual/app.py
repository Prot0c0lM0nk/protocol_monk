"""Protocol Monk Textual MVP app (no slash command features)."""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any

from textual.app import App
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Input

from protocol_monk.agent.structs import UserRequest
from protocol_monk.protocol.events import EventTypes
from protocol_monk.ui.textual.messages import (
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

        if self.mock_agent is not None:
            asyncio.create_task(self.mock_agent.start())
        if self.bridge is not None:
            asyncio.create_task(self.bridge.start())

    def action_quit(self) -> None:
        self.exit()

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
            decision = await asyncio.wait_for(self.push_screen_wait(modal), timeout=120.0)
        except asyncio.TimeoutError:
            # Prevent indefinite deadlocks in case of terminal/input issues.
            self.notify("Tool approval timed out; rejecting by default.", severity="warning")
            try:
                if self.screen is modal:
                    self.pop_screen()
            except Exception:
                pass
            return "rejected"
        except Exception:
            self.notify("Tool approval dialog failed; rejecting by default.", severity="error")
            return "rejected"

        if decision in {"approved", "approved_auto", "rejected"}:
            return decision
        return "rejected"

    def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if not text:
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

    def on_agent_stream_chunk(self, message: AgentStreamChunk) -> None:
        screen = self._chat_screen()
        if screen is None:
            return
        screen.add_stream_chunk(
            message.chunk,
            is_thinking=message.channel == "thinking",
        )

    def on_agent_status_update(self, message: AgentStatusUpdate) -> None:
        screen = self._chat_screen()
        if screen is None:
            return
        screen.update_status_bar(
            message.status,
            message.detail,
            provider=message.provider,
            model=message.model,
            auto_confirm=message.auto_confirm,
            working_dir=message.working_dir,
        )
        screen.show_thinking(message.status == "thinking", detail=message.detail)

    def on_agent_tool_result(self, message: AgentToolResult) -> None:
        screen = self._chat_screen()
        if screen is None:
            return
        screen.add_tool_result(message.payload)

    def on_agent_system_message(self, message: AgentSystemMessage) -> None:
        screen = self._chat_screen()
        if screen is None:
            return
        if message.level == "response_complete":
            screen.finalize_response()
            return

        if message.level in {"warning", "error"}:
            self.notify(message.message, severity=message.level)

"""Integration checks for Textual chat flow ordering and status behavior."""

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from textual.app import App, ComposeResult
from textual.widgets import Label

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ui.textual.widgets.chat_area import (
    ChatArea,
    AIMessage,
    ToolResultWidget,
    ThinkingIndicator,
    ReasoningStripWidget,
)
from ui.textual.widgets.status_bar import StatusBar
from ui.textual.models.phase_state import THINKING, RUNNING_TOOLS, READY


class ChatFlowApp(App):
    def compose(self) -> ComposeResult:
        yield ChatArea(id="chat")


class StatusBarApp(App):
    def compose(self) -> ComposeResult:
        yield StatusBar(id="status")


@pytest.mark.asyncio
async def test_reasoning_strip_precedes_assistant_message_and_has_no_emoji():
    app = ChatFlowApp()

    async with app.run_test() as pilot:
        chat = app.query_one(ChatArea)
        chat.add_stream_chunk("inner thought", is_thinking=True)
        chat.add_stream_chunk("assistant response", is_thinking=False)
        chat.finalize_response()
        await pilot.pause()

        children = list(chat.children)
        strip_indexes = [
            idx for idx, child in enumerate(children) if isinstance(child, ReasoningStripWidget)
        ]
        ai_indexes = [idx for idx, child in enumerate(children) if isinstance(child, AIMessage)]

        assert len(strip_indexes) == 1
        assert len(ai_indexes) == 1
        assert strip_indexes[0] < ai_indexes[0]

        strip = chat.query_one(ReasoningStripWidget)
        rendered = str(strip.render())
        assert "Reasoning captured" in rendered
        assert "🧠" not in rendered


@pytest.mark.asyncio
async def test_tool_result_stays_between_assistant_messages():
    app = ChatFlowApp()

    async with app.run_test() as pilot:
        chat = app.query_one(ChatArea)

        chat.add_stream_chunk("First assistant segment.", is_thinking=False)
        chat.finalize_response()
        await pilot.pause()

        chat.add_tool_result(
            "execute_command",
            SimpleNamespace(success=True, output="ok", data={"exit_code": 0}),
        )
        await pilot.pause()

        chat.add_stream_chunk("Second assistant segment.", is_thinking=False)
        chat.finalize_response()
        await pilot.pause()

        children = list(chat.children)
        ai_indexes = [idx for idx, child in enumerate(children) if isinstance(child, AIMessage)]
        tool_indexes = [
            idx for idx, child in enumerate(children) if isinstance(child, ToolResultWidget)
        ]

        assert len(ai_indexes) == 2
        assert len(tool_indexes) == 1
        assert ai_indexes[0] < tool_indexes[0] < ai_indexes[1]


@pytest.mark.asyncio
async def test_activity_indicator_phase_and_clear():
    app = ChatFlowApp()

    async with app.run_test() as pilot:
        chat = app.query_one(ChatArea)
        chat.show_thinking(True, phase="running_tools", detail="Tool 1/2: execute_command")
        await pilot.pause()

        indicator = chat.query_one(ThinkingIndicator)
        assert "Tool 1/2: execute_command" in str(indicator.render())

        chat.show_thinking(False, phase="running_tools")
        await pilot.pause()
        assert len(chat.query(ThinkingIndicator)) == 0


@pytest.mark.asyncio
async def test_status_bar_partial_updates_keep_metrics():
    app = StatusBarApp()

    async with app.run_test() as pilot:
        status_bar = app.query_one(StatusBar)
        status_bar.update_metrics(
            {
                "current_model": "model-a",
                "provider": "ollama",
                "conversation_length": 8,
                "estimated_tokens": 1200,
                "token_limit": 32000,
                "phase": READY,
                "working_dir": "/Users/nicholaspitzarella/Desktop/protocol_core_EDA_P1",
            }
        )
        await pilot.pause()

        status_bar.update_metrics({"phase": RUNNING_TOOLS, "phase_detail": "1/2 complete"})
        await pilot.pause()

        assert status_bar._last_metrics["current_model"] == "model-a"
        assert status_bar._last_metrics["provider"] == "ollama"
        assert status_bar._last_metrics["estimated_tokens"] == 1200
        assert status_bar._last_metrics["token_limit"] == 32000

        status_label = status_bar.query_one("#status-label", Label)
        assert "Running Tools" in str(status_label.render())
        status_detail = status_bar.query_one("#status-detail-label", Label)
        assert "1/2 complete" in str(status_detail.render())


@pytest.mark.asyncio
async def test_status_bar_spinner_active_then_static():
    app = StatusBarApp()

    async with app.run_test() as pilot:
        status_bar = app.query_one(StatusBar)
        status_bar.update_metrics({"phase": THINKING})
        await pilot.pause(0.25)
        first = str(status_bar.query_one("#status-label", Label).render())
        await pilot.pause(0.25)
        second = str(status_bar.query_one("#status-label", Label).render())

        assert first != second

        status_bar.update_metrics({"phase": READY})
        await pilot.pause(0.25)
        ready_label = str(status_bar.query_one("#status-label", Label).render())
        assert ready_label.startswith("● ")

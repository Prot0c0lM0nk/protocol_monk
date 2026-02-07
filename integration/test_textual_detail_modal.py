"""Focused tests for Textual compact detail flow."""

import sys
from types import SimpleNamespace
from pathlib import Path

import pytest
from textual.app import App, ComposeResult

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ui.textual.screens.modals.detail_viewer import DetailViewerModal
from ui.textual.widgets.chat_area import ChatArea


class DetailTestApp(App):
    def compose(self) -> ComposeResult:
        yield ChatArea(id="chat")


@pytest.mark.asyncio
async def test_thinking_is_hidden_and_viewable():
    app = DetailTestApp()

    async with app.run_test() as pilot:
        chat = app.query_one(ChatArea)

        chat.add_stream_chunk("first thought ", is_thinking=True)
        chat.add_stream_chunk("second thought", is_thinking=True)
        chat.add_stream_chunk("final answer", is_thinking=False)
        chat.finalize_response()
        await pilot.pause()

        detail_id = chat.last_detail_id()
        assert detail_id is not None

        detail = chat.get_detail(detail_id)
        assert detail is not None
        assert detail.kind == "thinking"
        assert "first thought second thought" in detail.full_text

        chat.open_detail(detail_id)
        await pilot.pause()
        assert isinstance(app.screen, DetailViewerModal)

        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, DetailViewerModal)


@pytest.mark.asyncio
async def test_tool_result_creates_persistent_detail_record():
    app = DetailTestApp()

    async with app.run_test() as pilot:
        chat = app.query_one(ChatArea)
        result = SimpleNamespace(
            success=True,
            output="command output line 1\ncommand output line 2",
            data={"exit_code": 0},
        )

        chat.add_tool_result("execute_command", result)
        await pilot.pause()

        detail_id = chat.last_detail_id()
        assert detail_id is not None
        detail = chat.get_detail(detail_id)
        assert detail is not None
        assert detail.kind == "tool_result"
        assert detail.tool_name == "execute_command"
        assert "command output line 1" in detail.full_text

"""Main chat screen for the Textual MVP."""

from textual.screen import Screen
from textual.widgets import Footer

from protocol_monk.ui.textual.widgets.chat_area import ChatArea
from protocol_monk.ui.textual.widgets.input_bar import InputBar
from protocol_monk.ui.textual.widgets.status_bar import StatusBar


class MainChatScreen(Screen):
    def compose(self):
        yield StatusBar(id="status-bar")
        yield ChatArea(id="chat-area")
        yield InputBar(id="input-bar")
        yield Footer()

    async def add_user_message(self, content: str) -> None:
        await self.query_one("#chat-area", ChatArea).add_user_message(content)

    def add_stream_chunk(
        self,
        chunk: str,
        is_thinking: bool = False,
        pass_id: str | None = None,
        sequence: int | None = None,
    ) -> None:
        self.query_one("#chat-area", ChatArea).add_stream_chunk(
            chunk,
            is_thinking=is_thinking,
            pass_id=pass_id,
            sequence=sequence,
        )

    def add_tool_result(self, payload: dict) -> None:
        self.query_one("#chat-area", ChatArea).add_tool_result(payload)

    def show_thinking(self, is_thinking: bool, detail: str = "") -> None:
        self.query_one("#chat-area", ChatArea).show_thinking(is_thinking, detail=detail)

    def finalize_response(self, pass_id: str = "") -> None:
        self.query_one("#chat-area", ChatArea).finalize_response(pass_id=pass_id)

    def update_status_bar(
        self,
        status: str,
        detail: str = "",
        provider: str | None = None,
        model: str | None = None,
        auto_confirm: bool | None = None,
        working_dir: str | None = None,
        message_count: int | None = None,
        total_tokens: int | None = None,
        context_limit: int | None = None,
        loaded_files_count: int | None = None,
    ) -> None:
        self.query_one("#status-bar", StatusBar).update_status(
            status,
            detail,
            provider=provider,
            model=model,
            auto_confirm=auto_confirm,
            working_dir=working_dir,
            message_count=message_count,
            total_tokens=total_tokens,
            context_limit=context_limit,
            loaded_files_count=loaded_files_count,
        )

    async def clear_chat(self) -> None:
        await self.query_one("#chat-area", ChatArea).clear_chat()

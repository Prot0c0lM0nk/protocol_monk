"""
The Bridge between ProtocolAgent and Textual UI.

This module implements the UI interface using Textual's thread-safe messaging system.
"""

import asyncio
from typing import Optional, Union, Dict, Any, List

from ui.base import UI
from textual.message import Message


class StreamMsg(Message):
    """Message for streaming text to the UI."""

    def __init__(self, text: str) -> None:
        super().__init__()
        self.text = text


class RequestInputMsg(Message):
    """Message requesting user input."""

    def __init__(self, prompt: str) -> None:
        super().__init__()
        self.prompt = prompt


class RequestApprovalMsg(Message):
    """Message requesting tool call approval."""

    def __init__(self, tool_call: Dict[str, Any]) -> None:
        super().__init__()
        self.tool_call = tool_call


class TextualUI(UI):
    """Textual implementation of the UI interface."""

    def __init__(self, app: Any) -> None:
        self.app = app
        self.input_event = asyncio.Event()
        self.input_response: Optional[str] = None
        self.approval_event = asyncio.Event()
        self.approval_response: Union[bool, Dict[str, Any], None] = None

    async def prompt_user(self, prompt: str) -> str:
        """Prompt the user for input and return the response."""
        self.input_event.clear()
        self.app.post_message(RequestInputMsg(prompt))
        await self.input_event.wait()
        return str(self.input_response)

    async def confirm_tool_call(
        self, tool_call: Dict[str, Any]
    ) -> Union[bool, Dict[str, Any]]:
        """Request approval for a tool call and return the response."""
        self.approval_event.clear()
        self.app.post_message(RequestApprovalMsg(tool_call))
        await self.approval_event.wait()
        return self.approval_response

    def print_stream(self, text: str) -> None:
        """Stream text to the UI."""
        self.app.post_message(StreamMsg(text))
    # === Sacred Abstract Method Implementations ===
    async def close(self) -> None:
        """Close the UI."""
        pass

    async def display_execution_start(self) -> None:
        """Display execution start message."""
        self.print_stream("✨ Execution started...")

    async def display_model_list(self, models: List[str]) -> None:
        """Display available models."""
        self.print_stream(f"Available models: {', '.join(models)}")

    async def display_progress(self, message: str) -> None:
        """Display progress message."""
        self.print_stream(f"⏳ {message}")

    async def display_startup_banner(self) -> None:
        """Display startup banner."""
        self.print_stream("🙏 Protocol Monk - Matrix of Ascension")

    async def display_startup_frame(self) -> None:
        """Display startup frame."""
        pass

    async def display_switch_report(self, report: str) -> None:
        """Display model switch report."""
        self.print_stream(f"🔄 {report}")

    async def display_task_complete(self, message: str) -> None:
        """Display task completion message."""
        self.print_stream(f"✅ {message}")

    async def display_tool_call(self, tool_call: Dict[str, Any]) -> None:
        """Display tool call information."""
        self.print_stream(f"🛠️ Tool call: {tool_call.get('tool_name')}")

    async def display_tool_result(self, result: str) -> None:
        """Display tool result."""
        self.print_stream(f"📋 Tool result: {result}")

    async def print_error(self, error: str) -> None:
        """Print error message."""
        self.print_stream(f"❌ Error: {error}")

    async def print_error_stderr(self, error: str) -> None:
        """Print error to stderr."""
        self.print_stream(f"❌ [STDERR] {error}")

    async def print_info(self, info: str) -> None:
        """Print info message."""
        self.print_stream(f"ℹ️ {info}")

    async def print_warning(self, warning: str) -> None:
        """Print warning message."""
        self.print_stream(f"⚠️ {warning}")

    async def set_auto_confirm(self, auto_confirm: bool) -> None:
        """Set auto-confirm mode."""
        pass

    async def start_thinking(self) -> None:
        """Start thinking animation."""
        self.print_stream("🤔 Thinking...")

    async def stop_thinking(self) -> None:
        """Stop thinking animation."""
        self.print_stream("💡 Thought complete")

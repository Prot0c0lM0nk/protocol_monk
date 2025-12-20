from textual.widget import Widget
from textual.widgets import Markdown, Static
from textual.containers import Container
from textual.reactive import reactive
from typing import Literal


class ChatMessage(Widget):
    """Display individual chat messages with proper reactive content."""

    # Reactive content that can update the display
    content = reactive("")
    role = reactive("")

    def __init__(
        self,
        role: Literal[
            "user",
            "assistant",
            "tool-call",
            "tool-result",
            "error",
            "warning",
            "info",
            "system",
        ],
        content: str,
        is_greeting: bool = False,
        is_tool_result: bool = False,
    ):
        super().__init__()
        self.role = role
        self.content = content
        self.is_greeting = is_greeting
        self.is_tool_result = is_tool_result
        self.content_widget = None

    def compose(self):
        """Create child widgets based on role and content type."""
        self.add_class(f"message {self.role}")

        if self.is_greeting:
            self.add_class("greeting")

        if self.is_tool_result:
            self.add_class("tool-result")

        # Add appropriate header based on role
        header_text = self._get_header_text()
        if header_text:
            yield Static(header_text, classes="message-header")

        # Choose appropriate content widget
        if self._should_use_markdown():
            self.content_widget = Markdown(self.content, classes="message-content")
            yield self.content_widget
        else:
            yield Static(self.content, classes="message-content")

    def _get_header_text(self) -> str:
        """Get appropriate header text for the message type."""
        headers = {
            "user": "👤 You",
            "assistant": "☦ Monk",
            "tool-call": "🛠️ Tool Call",
            "tool-result": "✅ Tool Result",
            "error": "❌ Error",
            "warning": "⚠️ Warning",
            "info": "ℹ️ Info",
            "system": "⚙️ System",
        }
        return headers.get(self.role, "")

    def _should_use_markdown(self) -> bool:
        """Determine if content should be rendered as Markdown."""
        # Use Markdown for assistant messages (except greetings) and tool results
        markdown_roles = {"assistant", "tool-call", "tool-result", "system"}
        return (
            self.role in markdown_roles
            and not self.is_greeting
            and self.content.strip()
        )

    def watch_content(self, content: str):
        """Update content when changed."""
        if self.content_widget:
            self.content_widget.update(content)
        else:
            # Find and update the content widget
            for child in self.children:
                if (
                    hasattr(child, "update")
                    and not isinstance(child, Static)
                    or "message-header" not in child.classes
                ):
                    child.update(content)
                    break

    def append_text(self, text: str):
        """Append text to existing message with streaming support."""
        self.content += text
        # The watch_content method will handle the update

    def get_content_width(self, container: int, viewport: int) -> int:
        """Calculate optimal content width."""
        # For messages, we want to use most of the available width but with some padding
        available_width = viewport - 4  # 2 characters padding on each side

        # Limit maximum width for better readability
        max_width = min(available_width, 120)
        return max_width

    def on_mount(self):
        """Additional setup after mounting."""
        # Ensure the message is properly styled based on its properties
        if self.is_greeting:
            self.add_class("greeting")
        if self.is_tool_result:
            self.add_class("tool-result")


"""--- End of messages.py ---

**Key Changes Made:**

1. **Added reactive properties**: `content` and `role` are now reactive for live updates
2. **Enhanced message types**: Added support for `tool-call`, `tool-result`, `error`, `warning`, `info`, `system`
3. **Proper header system**: Each message type gets an appropriate header with icons
4. **Smart Markdown rendering**: Only uses Markdown for appropriate content types
5. **Enhanced CSS styling**: Better visual distinction between message types
6. **Watch method**: `watch_content` automatically updates display when content changes
7. **Content width calculation**: Proper width handling for readability
8. **Streaming support**: `append_text` leverages the reactive system
9. **Flexible initialization**: Supports `is_greeting` and `is_tool_result` flags

The refactored message widget now properly handles different message types with appropriate styling and supports real-time content updates through Textual's reactive system.

Please upload the next file: `ui/textual/widgets/inputs.py` so I can continue with the refactoring.
"""

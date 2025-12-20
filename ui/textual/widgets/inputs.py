from textual.events import Key
from textual.message import Message
from textual.widget import Widget
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, TextArea, Static
from textual.reactive import reactive
from textual.validation import Validator, Length


class InputPanel(Widget):
    """Handle user input with proper event handling and validation."""

    class Submit(Message):
        """Event sent when user submits input."""

        def __init__(self, text: str):
            super().__init__()
            self.text = text

    class Clear(Message):
        """Event sent when input is cleared."""

        def __init__(self):
            super().__init__()

    # Reactive properties
    character_count = reactive(0)
    has_content = reactive(False)

    def __init__(self, id: str = "input-panel"):
        super().__init__(id=id)
        self.text_area = None
        self.send_button = None
        self.clear_button = None
        self.character_count_label = None

    def compose(self):
        """Create proper layout with text area and buttons."""
        with Horizontal(id="input-container"):
            with Vertical(id="text-area-container"):
                self.text_area = TextArea(
                    id="input-text",
                    placeholder="Type your message... (Shift+Enter for new line)",
                    show_line_numbers=False,
                    language="markdown",
                )
                yield self.text_area
                yield Static("", id="character-count")

            with Vertical(id="button-container"):
                self.send_button = Button("Send ✓", variant="primary", id="send")
                self.clear_button = Button("Clear ✗", variant="secondary", id="clear")
                yield self.send_button
                yield self.clear_button

    def on_mount(self):
        """Initialize after mounting."""
        self.text_area = self.query_one("#input-text", TextArea)
        self.send_button = self.query_one("#send", Button)
        self.clear_button = self.query_one("#clear", Button)
        self.character_count_label = self.query_one("#character-count", Static)

        # Focus the text area by default
        self.text_area.focus()

    def on_text_area_changed(self, event: TextArea.Changed):
        """Handle text changes and update reactive properties."""
        text = event.text_area.text
        self.character_count = len(text)
        self.has_content = bool(text.strip())

        # Update character count display
        if self.character_count_label:
            count_text = f"{self.character_count}/4000"
            self.character_count_label.update(count_text)

            # Show warning/error based on length
            if self.character_count > 4000:
                self.character_count_label.styles.color = "$error"
                self.text_area.add_class("validation-error")
            elif self.character_count > 3500:
                self.character_count_label.styles.color = "$warning"
                self.text_area.add_class("validation-warning")
            else:
                self.character_count_label.styles.color = "$text-muted"
                self.text_area.remove_class("validation-error")
                self.text_area.remove_class("validation-warning")

        # Update button states
        self.send_button.disabled = not self.has_content or self.character_count > 4000

    @property
    def text(self) -> str:
        """Get the current text content."""
        return self.text_area.text if self.text_area else ""

    def clear_input(self):
        """Clear the text input."""
        if self.text_area:
            self.text_area.clear()
            self.post_message(self.Clear())

    def set_placeholder(self, text: str):
        """Set the placeholder text."""
        if self.text_area:
            self.text_area.placeholder = text

    def on_button_pressed(self, event: Button.Pressed):
        """Handle button press events."""
        if event.button.id == "send":
            self._submit_text()
        elif event.button.id == "clear":
            self.clear_input()

    def _submit_text(self):
        """Submit the current text."""
        if self.text_area and self.has_content and self.character_count <= 4000:
            text = self.text_area.text.strip()
            if text:
                self.post_message(self.Submit(text))
                self.text_area.clear()
                # Keep focus on text area for continuous input
                self.text_area.focus()

    def on_key(self, event: Key):
        """Handle key press events."""
        if event.key == "enter" and not event.shift:
            # Enter without Shift submits
            self._submit_text()
            event.prevent_default()
        elif event.key == "escape":
            # Escape clears the input
            self.clear_input()
            event.prevent_default()
        elif event.key == "ctrl+l":
            # Ctrl+L focuses the input
            self.text_area.focus()
            event.prevent_default()

    def watch_has_content(self, has_content: bool):
        """Update button state when content availability changes."""
        if self.send_button:
            self.send_button.disabled = not has_content or self.character_count > 4000

    def watch_character_count(self, count: int):
        """Update styling based on character count."""
        if count > 4000:
            self.text_area.add_class("validation-error")
            if self.character_count_label:
                self.character_count_label.styles.color = "$error"
        elif count > 3500:
            self.text_area.add_class("validation-warning")
            if self.character_count_label:
                self.character_count_label.styles.color = "$warning"
        else:
            self.text_area.remove_class("validation-error")
            self.text_area.remove_class("validation-warning")
            if self.character_count_label:
                self.character_count_label.styles.color = "$text-muted"


"""--- End of inputs.py ---

**Key Changes Made:**

1. **Removed invalid TextArea.Validated reference**: Textual doesn't have a `Validated` event class for TextArea
2. **Implemented manual validation**: Used character count monitoring instead of formal validation events
3. **Simplified validation logic**: Removed the `Length` validator since we're handling it manually
4. **Enhanced character count handling**: Added color changes for warning/error states
5. **Better button disabling**: Button is disabled when content is too long

The error occurred because Textual's TextArea doesn't have a `Validated` event class. The validation in Textual is typically handled through reactive properties and manual checks rather than specific validation events.

This should fix the import error you're experiencing. Try running the TUI again with this corrected version.
"""

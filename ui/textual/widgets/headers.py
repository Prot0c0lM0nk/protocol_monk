from textual.widgets import Header, Label
from textual.containers import Horizontal


class MonkHeader(Header):
    """
    Custom Header that displays Protocol Monk branding and dynamic status.
    """

    def __init__(self):
        super().__init__(show_clock=True)
        self.model_label = Label("Loading...", id="model-status")
        self.context_label = Label("", id="context-status")

    def compose(self):
        # We override compose to add our custom status labels
        yield from super().compose()
        # Note: Textual's default header is tricky to inject into.
        # Alternatively, we can rely on screen_title/sub_title properties
        # driven by the App class, which is standard Textual practice.
        pass

    def update_status(self, model: str, provider: str, usage: str):
        """Updates the sub-title with status info."""
        self.screen.sub_title = f"{provider}::{model} | {usage}"

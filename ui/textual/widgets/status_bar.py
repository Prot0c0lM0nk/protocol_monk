"""
ui/textual/widgets/status_bar.py
Live-updating status bar.
"""

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Label, Static
from textual.reactive import reactive


class StatusBar(Horizontal):
    """
    Top status bar showing live agent metrics.
    """

    # Reactive attributes for auto-updates
    status = reactive("Idle")
    model_name = reactive("Unknown")
    provider = reactive("Unknown")
    tokens = reactive("0")
    limit = reactive("0")
    messages = reactive("0")
    working_dir = reactive("")

    def compose(self) -> ComposeResult:
        yield Label("☦ Protocol Monk", id="app-title")
        yield Static(" | ", classes="separator")

        # Model & Provider
        yield Label(f"{self.provider}", id="provider-label")
        yield Static(":", classes="separator")
        yield Label(f"{self.model_name}", id="model-label")

        yield Static("", classes="spacer")  # Pushes rest to the right

        # Messages
        yield Label("Msgs:", classes="metric-label")
        yield Label(f"{self.messages}", id="messages-label")

        yield Static(" | ", classes="separator")

        # Token Usage
        yield Label("Tokens:", classes="metric-label")
        yield Label(f"{self.tokens}/{self.limit}", id="token-label")

        yield Static(" | ", classes="separator")
        yield Label(f"● {self.status}", id="status-label")

        yield Static(" | ", classes="separator")
        yield Label("Dir:", classes="metric-label")
        yield Label(f"{self.working_dir}", id="working-dir-label")

    def watch_status(self, new_status: str) -> None:
        """Update status indicator color."""
        try:
            label = self.query_one("#status-label", Label)
            label.update(f"● {new_status}")

            if "thinking" in new_status.lower():
                label.set_classes("status-thinking")
            elif "error" in new_status.lower():
                label.set_classes("status-error")
            else:
                label.set_classes("status-idle")
        except Exception:
            pass

    def update_metrics(self, stats: dict) -> None:
        """Called by App to update display values."""
        self.model_name = stats.get("current_model", "Unknown")
        self.provider = stats.get("provider", "Unknown")
        self.tokens = f"{stats.get('estimated_tokens', 0):,}"
        self.limit = f"{stats.get('token_limit', 0):,}"
        self.messages = str(stats.get("conversation_length", 0))
        self.working_dir = stats.get("working_dir", "")

    def watch_model_name(self, value: str) -> None:
        try:
            self.query_one("#model-label", Label).update(value)
        except Exception:
            pass

    def watch_provider(self, value: str) -> None:
        try:
            self.query_one("#provider-label", Label).update(value)
        except Exception:
            pass

    def watch_tokens(self, value: str) -> None:
        try:
            self.query_one("#token-label", Label).update(f"{value}/{self.limit}")
        except Exception:
            pass

    def watch_limit(self, value: str) -> None:
        try:
            self.query_one("#token-label", Label).update(f"{self.tokens}/{value}")
        except Exception:
            pass

    def watch_messages(self, value: str) -> None:
        try:
            self.query_one("#messages-label", Label).update(value)
        except Exception:
            pass

    def watch_working_dir(self, value: str) -> None:
        try:
            self.query_one("#working-dir-label", Label).update(value)
        except Exception:
            pass

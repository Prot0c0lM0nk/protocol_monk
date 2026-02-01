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

    def compose(self) -> ComposeResult:
        yield Label("☦ Protocol Monk", id="app-title")
        yield Static(" | ", classes="separator")

        # Model & Provider
        yield Label(f"{self.provider}", id="provider-label")
        yield Static(":", classes="separator")
        yield Label(f"{self.model_name}", id="model-label")

        yield Static("", classes="spacer")  # Pushes rest to the right

        # Token Usage
        yield Label("Tokens:", classes="metric-label")
        yield Label(f"{self.tokens}/{self.limit}", id="token-label")

        yield Static(" | ", classes="separator")
        yield Label(f"● {self.status}", id="status-label")

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

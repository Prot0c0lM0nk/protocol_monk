"""
ui/textual/widgets/status_bar.py
Live-updating status bar with spinner support.
"""

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Label, Static
from textual.reactive import reactive

from .spinners import Spinner


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
    
    # Spinner for thinking state
    _thinking_spinner: Spinner = None

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

        # Thinking spinner (hidden by default)
        self._thinking_spinner.add_class("hidden")
        yield self._thinking_spinner

    def on_mount(self) -> None:
        """Force an initial render so all labels are visible immediately."""
        self._render_all()

    def _render_all(self) -> None:
        try:
            self.query_one("#provider-label", Label).update(str(self.provider))
            self.query_one("#model-label", Label).update(str(self.model_name))
            self.query_one("#messages-label", Label).update(str(self.messages))
            self.query_one("#token-label", Label).update(f"{self.tokens}/{self.limit}")
            self.query_one("#status-label", Label).update(f"● {self.status}")
            self.query_one("#working-dir-label", Label).update(str(self.working_dir))
        except Exception:
            pass

    def watch_status(self, new_status: str) -> None:
        """Update status indicator color and spinner."""
        try:
            label = self.query_one("#status-label", Label)
            label.update(f"● {new_status}")

            if "thinking" in new_status.lower():
                label.set_classes("status-thinking")
                self._thinking_spinner.remove_class("hidden")
                self._thinking_spinner.start()
            elif "error" in new_status.lower():
                label.set_classes("status-error")
                self._thinking_spinner.add_class("hidden")
                self._thinking_spinner.stop()
            else:
                label.set_classes("status-idle")
                self._thinking_spinner.add_class("hidden")
                self._thinking_spinner.stop()
        except Exception:
            pass

    def update_metrics(self, stats: dict) -> None:
        """Called by App to update display values."""
        self.model_name = str(stats.get("current_model", "Unknown"))
        self.provider = str(stats.get("provider", "Unknown"))
        self.tokens = f"{stats.get('estimated_tokens', 0):,}"
        self.limit = f"{stats.get('token_limit', 0):,}"
        self.messages = str(stats.get('conversation_length', 0))
        self.working_dir = str(stats.get("working_dir", ""))
        self.status = str(stats.get("status", "Ready"))
        self._render_all()

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

    def watch_working_dir(self, value: str) -> None:
        try:
            self.query_one("#working-dir-label", Label).update(value)
        except Exception:
            pass

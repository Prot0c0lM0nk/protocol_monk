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

        # Status (always visible)
        yield Label(f"● {self.status}", id="status-label")

        yield Static(" | ", classes="separator")
        yield Label("Dir:", classes="metric-label")
        yield Label(f"{self.working_dir}", id="working-dir-label")

    def on_mount(self) -> None:
        """Force an initial render so all labels are visible immediately."""
        self.call_after_refresh(self._render_all)

    def _render_all(self) -> None:
        """Update all labels with current reactive values."""
        try:
            self.query_one("#provider-label", Label).update(str(self.provider))
            self.query_one("#model-label", Label).update(str(self.model_name))
            self.query_one("#messages-label", Label).update(str(self.messages))
            self.query_one("#token-label", Label).update(f"{self.tokens}/{self.limit}")
            self.query_one("#status-label", Label).update(f"● {self.status}")
            self.query_one("#working-dir-label", Label).update(str(self.working_dir))
        except Exception:
            # Widgets may not be ready yet (e.g., during initial compose)
            # This is expected and safe to ignore
            pass

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
        # Bypass watchers to avoid race conditions - update labels directly
        try:
            self.query_one("#model-label", Label).update(
                str(stats.get("current_model", "Unknown"))
            )
            self.query_one("#provider-label", Label).update(
                str(stats.get("provider", "Unknown"))
            )
            self.query_one("#messages-label", Label).update(
                str(stats.get("conversation_length", 0))
            )

            tokens = f"{stats.get('estimated_tokens', 0):,}"
            limit = f"{stats.get('token_limit', 0):,}"
            self.query_one("#token-label", Label).update(f"{tokens}/{limit}")

            status = str(stats.get("status", "Ready"))
            status_label = self.query_one("#status-label", Label)
            status_label.update(f"● {status}")

            # Update status color
            if "thinking" in status.lower():
                status_label.set_classes("status-thinking")
            elif "error" in status.lower():
                status_label.set_classes("status-error")
            else:
                status_label.set_classes("status-idle")

            # Truncate working directory if too long
            working_dir = str(stats.get("working_dir", ""))
            if len(working_dir) > 30:
                # Show first part and last part: /Users/.../protocol_core_EDA_P1
                parts = working_dir.split("/")
                if len(parts) > 3:
                    working_dir = f"{parts[0]}/{parts[1]}/.../{parts[-1]}"
                else:
                    working_dir = working_dir[:27] + "..."

            self.query_one("#working-dir-label", Label).update(working_dir)

            # Force refresh of the status bar
            self.refresh()
        except Exception:
            # Widgets may not be ready yet - skip update
            pass

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

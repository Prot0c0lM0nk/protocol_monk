"""
ui/textual/widgets/status_bar.py
Live-updating status bar.
"""

from typing import Optional

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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._provider_label: Optional[Label] = None
        self._model_label: Optional[Label] = None
        self._messages_label: Optional[Label] = None
        self._token_label: Optional[Label] = None
        self._status_label: Optional[Label] = None
        self._working_dir_label: Optional[Label] = None

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

    def _cache_labels(self) -> None:
        """Cache frequent label lookups to avoid repeated query_one calls."""
        if self._provider_label is None:
            self._provider_label = self.query_one("#provider-label", Label)
        if self._model_label is None:
            self._model_label = self.query_one("#model-label", Label)
        if self._messages_label is None:
            self._messages_label = self.query_one("#messages-label", Label)
        if self._token_label is None:
            self._token_label = self.query_one("#token-label", Label)
        if self._status_label is None:
            self._status_label = self.query_one("#status-label", Label)
        if self._working_dir_label is None:
            self._working_dir_label = self.query_one("#working-dir-label", Label)

    def _labels_ready(self) -> bool:
        return all(
            [
                self._provider_label,
                self._model_label,
                self._messages_label,
                self._token_label,
                self._status_label,
                self._working_dir_label,
            ]
        )

    def _render_all(self) -> None:
        """Update all labels with current reactive values."""
        try:
            self._cache_labels()
            if not self._labels_ready():
                return
            self._provider_label.update(str(self.provider))
            self._model_label.update(str(self.model_name))
            self._messages_label.update(str(self.messages))
            self._token_label.update(f"{self.tokens}/{self.limit}")
            self._status_label.update(f"● {self.status}")
            self._working_dir_label.update(str(self.working_dir))
        except Exception:
            # Widgets may not be ready yet (e.g., during initial compose)
            # This is expected and safe to ignore
            pass

    def _set_status_style(self, label: Label, status: str) -> None:
        if "thinking" in status.lower():
            label.set_classes("status-thinking")
        elif "error" in status.lower():
            label.set_classes("status-error")
        else:
            label.set_classes("status-idle")

    def watch_status(self, new_status: str) -> None:
        """Update status indicator color."""
        try:
            self._cache_labels()
            label = self._status_label
            if label is None:
                return
            label.update(f"● {new_status}")
            self._set_status_style(label, new_status)
        except Exception:
            pass

    def update_metrics(self, stats: dict) -> None:
        """Called by App to update display values."""
        # Bypass watchers to avoid race conditions - update labels directly
        try:
            self._cache_labels()
            if not self._labels_ready():
                return

            self._model_label.update(str(stats.get("current_model", "Unknown")))
            self._provider_label.update(str(stats.get("provider", "Unknown")))
            self._messages_label.update(str(stats.get("conversation_length", 0)))

            tokens = f"{stats.get('estimated_tokens', 0):,}"
            limit = f"{stats.get('token_limit', 0):,}"
            self._token_label.update(f"{tokens}/{limit}")

            status = str(stats.get("status", "Ready"))
            status_label = self._status_label
            if status_label is None:
                return
            status_label.update(f"● {status}")
            self._set_status_style(status_label, status)

            # Truncate working directory if too long
            working_dir = str(stats.get("working_dir", ""))
            if len(working_dir) > 30:
                # Show first part and last part: /Users/.../protocol_core_EDA_P1
                parts = working_dir.split("/")
                if len(parts) > 3:
                    working_dir = f"{parts[0]}/{parts[1]}/.../{parts[-1]}"
                else:
                    working_dir = working_dir[:27] + "..."

            self._working_dir_label.update(working_dir)
        except Exception:
            # Widgets may not be ready yet - skip update
            pass

    def watch_model_name(self, value: str) -> None:
        try:
            self._cache_labels()
            if self._model_label is not None:
                self._model_label.update(value)
        except Exception:
            pass

    def watch_provider(self, value: str) -> None:
        try:
            self._cache_labels()
            if self._provider_label is not None:
                self._provider_label.update(value)
        except Exception:
            pass

    def watch_tokens(self, value: str) -> None:
        try:
            self._cache_labels()
            if self._token_label is not None:
                self._token_label.update(f"{value}/{self.limit}")
        except Exception:
            pass

    def watch_limit(self, value: str) -> None:
        try:
            self._cache_labels()
            if self._token_label is not None:
                self._token_label.update(f"{self.tokens}/{value}")
        except Exception:
            pass

    def watch_messages(self, value: str) -> None:
        try:
            self._cache_labels()
            if self._messages_label is not None:
                self._messages_label.update(value)
        except Exception:
            pass

    def watch_working_dir(self, value: str) -> None:
        try:
            self._cache_labels()
            if self._working_dir_label is not None:
                self._working_dir_label.update(value)
        except Exception:
            pass

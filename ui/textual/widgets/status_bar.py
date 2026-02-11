"""
ui/textual/widgets/status_bar.py
Live-updating status bar.
"""

from typing import Optional

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Label, Static
from textual.reactive import reactive

from ..models.phase_state import (
    ALLOWED_PHASES,
    PHASE_ACTIVE_FLAGS,
    PHASE_LABELS,
    PHASE_STYLE_CLASS,
    READY,
    THINKING,
    PLANNING,
    RUNNING_TOOLS,
    AWAITING_APPROVAL,
    WAITING_INPUT,
    ERROR,
    normalize_phase,
)


class StatusBar(Horizontal):
    """
    Top status bar showing live agent metrics.
    """

    # Reactive attributes for auto-updates
    status = reactive(READY)
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
        self._status_detail_label: Optional[Label] = None
        self._working_dir_label: Optional[Label] = None
        self._last_metrics = {
            "current_model": "Unknown",
            "provider": "Unknown",
            "conversation_length": 0,
            "estimated_tokens": 0,
            "token_limit": 0,
            "working_dir": "",
            "phase": READY,
            "phase_detail": "",
        }
        self._phase = READY
        self._phase_detail = ""
        self._status_frames = ("◴", "◷", "◶", "◵")
        self._status_frame_index = 0
        self._status_timer = None

    def compose(self) -> ComposeResult:
        yield Label("☦ Protocol Monk", id="app-title")
        yield Static(" | ", classes="separator")

        # Left: model and provider
        yield Label(f"{self.provider}", id="provider-label")
        yield Static(":", classes="separator")
        yield Label(f"{self.model_name}", id="model-label")

        # Middle: metrics
        yield Static(" | ", classes="separator")
        yield Label("Msgs:", classes="metric-label")
        yield Label(f"{self.messages}", id="messages-label")

        yield Static(" | ", classes="separator")
        yield Label("Tokens:", classes="metric-label")
        yield Label(f"{self.tokens}/{self.limit}", id="token-label")

        yield Static(" | ", classes="separator")
        yield Label("Dir:", classes="metric-label")
        yield Label(f"{self.working_dir}", id="working-dir-label")

        # Right: phase lane
        yield Static(" | ", classes="separator")
        yield Label("Phase:", classes="metric-label")
        yield Label("● Ready", id="status-label", classes="status-ready")
        yield Label("", id="status-detail-label")

    def on_mount(self) -> None:
        """Force an initial render so all labels are visible immediately."""
        self._status_timer = self.set_interval(0.18, self._tick_phase_spinner)
        self.call_after_refresh(self._render_all)

    def on_unmount(self) -> None:
        if self._status_timer is not None:
            self._status_timer.stop()

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
        if self._status_detail_label is None:
            self._status_detail_label = self.query_one("#status-detail-label", Label)
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
                self._status_detail_label,
                self._working_dir_label,
            ]
        )

    def _render_all(self) -> None:
        """Update all labels with current reactive values."""
        try:
            self._cache_labels()
            if not self._labels_ready():
                return
            self.update_metrics(self._last_metrics)
        except Exception:
            pass

    def watch_status(self, new_status: str) -> None:
        """Backward-compatible status watcher."""
        try:
            self._phase = self._coerce_phase(new_status)
            self._phase_detail = ""
            self._cache_labels()
            if self._status_label is not None:
                self._render_phase_labels()
        except Exception:
            pass

    def update_metrics(self, stats: dict) -> None:
        """Called by App to update display values."""
        if not isinstance(stats, dict):
            return

        for key, value in stats.items():
            if value is not None:
                self._last_metrics[key] = value

        if "phase" in stats or "status" in stats:
            phase_value = stats.get("phase", stats.get("status", READY))
            self._phase = self._coerce_phase(phase_value)
        if "phase_detail" in stats:
            self._phase_detail = str(stats.get("phase_detail") or "")
        elif "status_detail" in stats:
            self._phase_detail = str(stats.get("status_detail") or "")
        elif "phase" in stats and "phase_detail" not in stats:
            # If phase changed without detail, clear stale detail text.
            self._phase_detail = ""

        try:
            self._cache_labels()
            if not self._labels_ready():
                return

            merged = self._last_metrics
            self._model_label.update(str(merged.get("current_model", "Unknown")))
            self._provider_label.update(str(merged.get("provider", "Unknown")))
            self._messages_label.update(str(merged.get("conversation_length", 0)))

            tokens = self._format_int(merged.get("estimated_tokens", 0))
            limit = self._format_int(merged.get("token_limit", 0))
            self._token_label.update(f"{tokens}/{limit}")

            self._working_dir_label.update(
                self._truncate_working_dir(str(merged.get("working_dir", "")))
            )
            self._render_phase_labels()
        except Exception:
            pass

    def _render_phase_labels(self) -> None:
        status_label = self._status_label
        status_detail_label = self._status_detail_label
        if status_label is None or status_detail_label is None:
            return

        prefix = self._phase_prefix(self._phase)
        phase_text = PHASE_LABELS.get(self._phase, PHASE_LABELS[READY])
        status_label.update(f"{prefix} {phase_text}")
        status_label.set_classes(PHASE_STYLE_CLASS.get(self._phase, "status-ready"))

        detail = self._truncate_phase_detail(self._phase_detail)
        status_detail_label.update(f"({detail})" if detail else "")
        status_detail_label.set_classes("status-detail")

    def _tick_phase_spinner(self) -> None:
        try:
            if not PHASE_ACTIVE_FLAGS.get(self._phase, False):
                return
            self._status_frame_index += 1
            self._cache_labels()
            if self._status_label is None:
                return
            self._render_phase_labels()
        except Exception:
            pass

    def _phase_prefix(self, phase: str) -> str:
        if not PHASE_ACTIVE_FLAGS.get(phase, False):
            return "●"
        return self._status_frames[self._status_frame_index % len(self._status_frames)]

    @staticmethod
    def _format_int(value: object) -> str:
        try:
            return f"{int(value):,}"
        except (TypeError, ValueError):
            return str(value)

    @staticmethod
    def _truncate_working_dir(working_dir: str) -> str:
        if len(working_dir) <= 30:
            return working_dir
        parts = working_dir.split("/")
        if len(parts) > 3:
            return f"{parts[0]}/{parts[1]}/.../{parts[-1]}"
        return working_dir[:27] + "..."

    @staticmethod
    def _truncate_phase_detail(detail: str) -> str:
        text = str(detail or "").strip()
        if len(text) <= 32:
            return text
        return text[:31] + "…"

    @staticmethod
    def _coerce_phase(value: object) -> str:
        text = str(value or "").strip()
        normalized = normalize_phase(text)
        if normalized in ALLOWED_PHASES and text in ALLOWED_PHASES:
            return normalized

        lowered = text.lower()
        if "thinking" in lowered:
            return THINKING
        if "plan" in lowered or "reflect" in lowered or "process" in lowered:
            return PLANNING
        if "running" in lowered or "tool" in lowered:
            return RUNNING_TOOLS
        if "approval" in lowered:
            return AWAITING_APPROVAL
        if "waiting" in lowered or "input" in lowered:
            return WAITING_INPUT
        if "error" in lowered or "fail" in lowered:
            return ERROR
        if "ready" in lowered:
            return READY
        return READY

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

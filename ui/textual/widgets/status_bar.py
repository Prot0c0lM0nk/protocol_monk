"""Status bar with reference-compatible structure and selectors."""

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Label, Static


class StatusBar(Horizontal):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._status_frames = ("◴", "◷", "◶", "◵")
        self._frame_index = 0
        self._phase = "idle"
        self._detail = ""
        self._provider = "unknown"
        self._model = "unknown"
        self._auto_confirm = False
        self._working_dir = ""
        self._message_count = 0
        self._total_tokens = 0
        self._context_limit = 0
        self._loaded_files_count = 0
        self._timer = None

    def compose(self) -> ComposeResult:
        yield Label("☦ Protocol Monk", id="app-title")
        yield Static(" | ", classes="separator")
        yield Label(self._provider, id="provider-label")
        yield Static(":", classes="separator")
        yield Label(self._model, id="model-label")

        yield Static(" | ", classes="separator")
        yield Label("Msgs:", classes="metric-label")
        yield Label("0", id="messages-label")

        yield Static(" | ", classes="separator")
        yield Label("Tokens:", classes="metric-label")
        yield Label("0/0", id="token-label")

        yield Static(" | ", classes="separator")
        yield Label("Files:", classes="metric-label")
        yield Label("0", id="files-label")

        yield Static(" | ", classes="separator")
        yield Label("Dir:", classes="metric-label")
        yield Label(self._working_dir or "-", id="working-dir-label")

        yield Static(" | ", classes="separator")
        yield Label("Phase:", classes="metric-label")
        yield Label("● Ready", id="status-label", classes="status-ready")
        yield Label("", id="status-detail-label", classes="status-detail")

    def on_mount(self) -> None:
        self._timer = self.set_interval(0.18, self._tick)

    def on_unmount(self) -> None:
        if self._timer is not None:
            self._timer.stop()

    def update_status(
        self,
        status: str,
        detail: str = "",
        provider: str | None = None,
        model: str | None = None,
        auto_confirm: bool | None = None,
        working_dir: str | None = None,
        message_count: int | None = None,
        total_tokens: int | None = None,
        context_limit: int | None = None,
        loaded_files_count: int | None = None,
    ) -> None:
        self._phase = str(status or "idle").strip().lower()
        self._detail = str(detail or "")
        if provider is not None:
            self._provider = str(provider)
        if model is not None:
            self._model = str(model)
        if auto_confirm is not None:
            self._auto_confirm = bool(auto_confirm)
        if working_dir is not None:
            self._working_dir = self._truncate_working_dir(str(working_dir))
        self.update_metrics(
            message_count=message_count,
            total_tokens=total_tokens,
            context_limit=context_limit,
            loaded_files_count=loaded_files_count,
        )
        self._render_labels()
        self._render_status()

    def update_metrics(
        self,
        message_count: int | None = None,
        total_tokens: int | None = None,
        context_limit: int | None = None,
        loaded_files_count: int | None = None,
    ) -> None:
        if message_count is not None:
            self._message_count = max(0, int(message_count))
        if total_tokens is not None:
            self._total_tokens = max(0, int(total_tokens))
        if context_limit is not None:
            self._context_limit = max(0, int(context_limit))
        if loaded_files_count is not None:
            self._loaded_files_count = max(0, int(loaded_files_count))
        self._render_labels()

    def _tick(self) -> None:
        if self._phase in {"thinking", "executing", "paused"}:
            self._frame_index += 1
            self._render_status()

    def _render_status(self) -> None:
        status_label = self.query_one("#status-label", Label)
        detail_label = self.query_one("#status-detail-label", Label)

        prefix = self._phase_prefix()
        text, style_class = self._phase_label_and_class()
        status_label.update(f"{prefix} {text}")
        status_label.set_classes(style_class)

        detail = self._detail.strip()
        if self._auto_confirm:
            detail = f"{detail} | auto-approve:on" if detail else "auto-approve:on"
        detail_label.update(f"({detail})" if detail else "")

    def _render_labels(self) -> None:
        self.query_one("#provider-label", Label).update(self._provider)
        self.query_one("#model-label", Label).update(self._model)
        self.query_one("#working-dir-label", Label).update(self._working_dir or "-")
        self.query_one("#messages-label", Label).update(str(self._message_count))
        token_value = f"{self._total_tokens}/{self._context_limit or 0}"
        self.query_one("#token-label", Label).update(token_value)
        self.query_one("#files-label", Label).update(str(self._loaded_files_count))

    @staticmethod
    def _truncate_working_dir(working_dir: str) -> str:
        if len(working_dir) <= 30:
            return working_dir
        parts = working_dir.split("/")
        if len(parts) > 3:
            return f"{parts[0]}/{parts[1]}/.../{parts[-1]}"
        return working_dir[:27] + "..."

    def _phase_prefix(self) -> str:
        if self._phase in {"thinking", "executing", "paused"}:
            return self._status_frames[self._frame_index % len(self._status_frames)]
        return "●"

    def _phase_label_and_class(self) -> tuple[str, str]:
        if self._phase == "thinking":
            return "Thinking", "status-thinking"
        if self._phase == "executing":
            return "Running Tools", "status-tools"
        if self._phase == "paused":
            return "Awaiting Approval", "status-waiting"
        if self._phase == "error":
            return "Error", "status-error"
        return "Ready", "status-ready"

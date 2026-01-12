from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Label, Static
from textual.reactive import reactive

class StatusBar(Horizontal):
    """
    Top status bar showing the current model and agent state.
    """
    
    # Reactive attributes will auto-update the UI when changed
    status = reactive("Idle")
    model = reactive("Mock Model")

    def compose(self) -> ComposeResult:
        yield Label("🤖 Protocol Monk", id="app-title")
        yield Static(" | ", classes="separator")
        yield Label(f"{self.model}", id="model-label")
        yield Static("", classes="spacer") # Pushes status to the right
        yield Label(f"● {self.status}", id="status-label")

    def watch_status(self, new_status: str) -> None:
        """Called automatically when self.status changes."""
        try:
            label = self.query_one("#status-label", Label)
            label.update(f"● {new_status}")
            
            # Simple color coding based on status string
            if "thinking" in new_status.lower():
                label.set_classes("status-thinking")
            elif "error" in new_status.lower():
                label.set_classes("status-error")
            else:
                label.set_classes("status-idle")
        except:
            pass
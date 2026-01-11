"""
ui/textual/widgets/status_bar.py
Status bar widget for showing agent status
"""

from textual.widgets import Static
from typing import Optional


class StatusBar(Static):
    """
    Status bar widget
    Shows current agent status and connection info
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.status = "Ready"
        self.model = "Unknown"
        self.provider = "Unknown"

    def set_status(self, status: str) -> None:
        """
        Set the status text

        Args:
            status: Status message
        """
        self.status = status
        self._update_display()

    def set_model(self, model: str) -> None:
        """
        Set the current model

        Args:
            model: Model name
        """
        self.model = model
        self._update_display()

    def set_provider(self, provider: str) -> None:
        """
        Set the current provider

        Args:
            provider: Provider name
        """
        self.provider = provider
        self._update_display()

    def _update_display(self) -> None:
        """Update the status bar display"""
        display = f"Status: {self.status} | Model: {self.model} | Provider: {self.provider}"
        self.update(display)
"""Textual UI package for Protocol Monk."""

from protocol_monk.ui.textual.mock_agent import MockAgentService

__all__ = ["MockAgentService", "ProtocolMonkTextualApp", "TextualEventBridge"]


def create_textual_app(*args, **kwargs):
    """Lazy import helper so non-Textual test runs can import this package."""
    from protocol_monk.ui.textual.app import ProtocolMonkTextualApp

    return ProtocolMonkTextualApp(*args, **kwargs)


def create_textual_bridge(*args, **kwargs):
    """Lazy import helper so non-Textual test runs can import this package."""
    from protocol_monk.ui.textual.bridge import TextualEventBridge

    return TextualEventBridge(*args, **kwargs)

"""
Textual TUI Implementation for Protocol Monk
==========================================

This package provides a modern, event-driven Terminal User Interface using Textual.
It serves as a frontend for the EDA agent with real-time streaming, interactive
tool approvals, and mouse support.
"""

from .app import ProtocolMonkApp
from .interface import TextualUI

__all__ = ["ProtocolMonkApp", "TextualUI"]

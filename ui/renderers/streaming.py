#!/usr/bin/env python3
"""
Streaming Renderer Module - Orthodox Matrix Theme
Contains pure rendering functions for streaming UI components.
"""
from rich.markdown import Markdown
from rich.text import Text

from ..styles import create_monk_panel


def generate_stream_panel(content_str: str):
    """Generates the panel frame for streaming content."""

    # Generate Content
    if content_str.strip():
        if any(c in content_str for c in ["*", "_", "#", "`"]):
            content = Markdown(content_str)
        else:
            content = Text(content_str)
    else:
        content = Text("", style="dim")  # Empty text if just starting

    # Use the Shared Factory
    main_panel = create_monk_panel(content)

    return main_panel

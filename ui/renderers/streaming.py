#!/usr/bin/env python3
"""
Streaming Renderer Module - Orthodox Matrix Theme

Contains pure rendering functions for streaming UI components.
"""

from rich.text import Text
from rich.markdown import Markdown
from rich.console import Group
from rich.align import Align
from rich.spinner import Spinner
from ..styles import create_monk_panel


def generate_stream_panel(content_str: str, is_tool: bool, tool_len: int):
    """Generates the panel frame using the shared style factory."""
    # 1. Generate Content
    if content_str.strip():
        if any(c in content_str for c in ["*", "_", "#", "`"]):
            content = Markdown(content_str)
        else:
            content = Text(content_str)
    else:
        content = Text("...", style="dim")

    # 2. Use the Shared Factory (Clean & Consistent)
    main_panel = create_monk_panel(content)

    # 3. If Tool Detected, add the Status Footer
    if is_tool:
        status_text = Text.assemble(
            ("  Constructing Neural Action... ", "dim"),
            (f"({tool_len} bytes)", "dim cyan"),
        )
        spinner = Spinner(
            "dots", text=status_text, style="#ffaa44"
        )  # Orthodox gold color

        return Group(main_panel, Align.center(spinner))

    return main_panel

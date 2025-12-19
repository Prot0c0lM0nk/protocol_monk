#!/usr/bin/env python3
"""
Streaming Renderer Module - Orthodox Matrix Theme
Contains pure rendering functions for streaming UI components.
"""

from rich.align import Align
from rich.console import Group
from rich.markdown import Markdown
from rich.spinner import Spinner
from rich.text import Text
from rich.progress_bar import ProgressBar  # Used for visual effect

from ..styles import create_monk_panel


def generate_stream_panel(content_str: str, is_tool: bool, tool_len: int, buffer_limit_exceeded: bool = False):
    """Generates the panel frame. Hides raw JSON tool calls. Shows buffer limit warnings."""

    # 1. Generate Content
    # If we are in tool mode, we might want to hide the partial JSON from the main text area
    # depending on how the processor splits it. The processor returns 'visible_text'
    # which excludes the JSON.

    if content_str.strip():
        if any(c in content_str for c in ["*", "_", "#", "`"]):
            content = Markdown(content_str)
        else:
            content = Text(content_str)
    else:
        content = Text("", style="dim")  # Empty text if just starting

    # 2. Use the Shared Factory
    main_panel = create_monk_panel(content)
    
    # 2.5. Add Buffer Limit Warning if exceeded
    if buffer_limit_exceeded:
        warning_text = Text(
            "  ⚠️  Content truncated due to buffer limits",
            style="bold #ff6b6b"  # Red warning color
        )
        main_panel = Group(main_panel, warning_text)

    # If Tool Detected, Add simple status indicator
    if is_tool:
        # Simple status text with spinner (no complex Group)
        status_text = Text.assemble(
            ("  Constructing Neural Action... ", "bold #ffaa44"),
            (f"({tool_len} bytes)", "dim cyan"),
        )
        
        # Use simple text instead of complex Group with spinner
        return Group(main_panel, status_text)

    return main_panel
    return main_panel

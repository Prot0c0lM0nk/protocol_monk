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


def generate_stream_panel(content_str: str, is_tool: bool, tool_len: int):
    """Generates the panel frame. Hides raw JSON tool calls."""

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

    # 3. If Tool Detected, Add the Neural Construction Bar
    if is_tool:
        # Create a visual indicator that the agent is "coding" or "constructing"
        # We simulate a progress bar based on length to give it life

        # Calculate a fake "percent" based on bytes to make the bar move
        # Modulo 100 ensures it loops if it gets huge
        percent = min((tool_len % 1000) / 10.0, 100.0)

        status_text = Text.assemble(
            ("  Constructing Neural Action... ", "bold #ffaa44"),
            (f"({tool_len} bytes)", "dim cyan"),
        )

        # We construct a Group containing the text + a spinner
        status_group = Group(
            Align.center(status_text),
            Align.center(Spinner("dots12", style="bold #ffaa44")),
        )

        # We append this status group to the main panel output
        return Group(main_panel, status_group)

    return main_panel

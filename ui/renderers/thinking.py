#!/usr/bin/env python3
"""
Thinking Renderer - Orthodox Matrix Theme
"""
import asyncio
from rich.status import Status
from ui.styles import console


async def render_agent_thinking():
    """
    The 'Reasoning' Phase.
    Async-safe cinematic pause.
    """
    console.print()
    with console.status(
        "[success]Contemplating the Logos...[/]",
        spinner="dots",
        spinner_style="#ffaa44",
    ):  # Orthodox gold color
        # Non-blocking sleep
        await asyncio.sleep(2.5)

"""Configurable typewriter animation effect for Protocol Monk.

Implements a Matrix-style typing animation with configurable timing
for dramatic text reveal during the setup wizard.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING

from rich.console import Console

if TYPE_CHECKING:
    from rich.text import Text

from .styles import console as default_console


@dataclass
class TypewriterConfig:
    """Timing configuration for typewriter animation.

    All times are in seconds.
    """

    # Character delays
    char_delay: float = 0.02  # Base delay between characters

    # Pause durations for punctuation
    pause_on_period: float = 0.15  # Pause after . ! ?
    pause_on_comma: float = 0.08  # Pause after , ; :
    pause_on_newline: float = 0.10  # Pause after line breaks
    pause_before_prompt: float = 0.30  # Pause before showing options

    # Random variation (0.0 = none, 1.0 = full char_delay)
    variation: float = 0.3  # Add human-like variation


# Presets for easy tuning
TYPEWRITER_PRESETS = {
    "fast": TypewriterConfig(
        char_delay=0.01,
        pause_on_period=0.08,
        pause_on_comma=0.04,
        pause_on_newline=0.05,
        pause_before_prompt=0.15,
        variation=0.2,
    ),
    "normal": TypewriterConfig(
        char_delay=0.02,
        pause_on_period=0.15,
        pause_on_comma=0.08,
        pause_on_newline=0.10,
        pause_before_prompt=0.30,
        variation=0.3,
    ),
    "dramatic": TypewriterConfig(
        char_delay=0.035,
        pause_on_period=0.25,
        pause_on_comma=0.12,
        pause_on_newline=0.15,
        pause_before_prompt=0.50,
        variation=0.4,
    ),
}

# Matrix-style character set for visual effect
MATRIX_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789@#$%&*<>[]{}|/\\~"


async def typewriter_print(
    text: str,
    *,
    console: Console | None = None,
    config: TypewriterConfig | None = None,
    style: str = "monk.text",
    clear_after: bool = False,
) -> None:
    """Print text with typewriter animation effect.

    Args:
        text: The text to animate
        console: Rich console to use (defaults to styled console)
        config: Timing configuration (defaults to "normal" preset)
        style: Rich style to apply to the text
        clear_after: If True, clear the line after animation completes

    """
    target_console = console or default_console
    cfg = config or TYPEWRITER_PRESETS["normal"]

    import random

    for i, char in enumerate(text):
        # Apply style and print character
        target_console.print(char, style=style, end="")

        # Calculate delay with optional variation
        base_delay = cfg.char_delay
        if cfg.variation > 0:
            variation = random.uniform(0, cfg.variation * base_delay)
            base_delay += random.choice([-variation, variation])
            base_delay = max(0.005, base_delay)  # Minimum 5ms

        # Add punctuation pauses
        if char in ".!?":
            await asyncio.sleep(base_delay + cfg.pause_on_period)
        elif char in ",;:":
            await asyncio.sleep(base_delay + cfg.pause_on_comma)
        elif char == "\n":
            await asyncio.sleep(base_delay + cfg.pause_on_newline)
        else:
            await asyncio.sleep(base_delay)

    if clear_after:
        # Move cursor back and clear line
        target_console.print("\r" + " " * len(text) + "\r", end="")


async def typewriter_text(
    text: str | Text,
    *,
    config: TypewriterConfig | None = None,
) -> None:
    """Animate text with typewriter effect, supporting Rich Text objects.

    This is a convenience wrapper that handles both plain strings and
    Rich Text objects.

    Args:
        text: Plain string or Rich Text object to animate
        config: Timing configuration

    """
    from rich.text import Text as RichText

    if isinstance(text, RichText):
        # Extract plain text for animation, then print styled
        await typewriter_print(text.plain, config=config)
    else:
        await typewriter_print(text, config=config)
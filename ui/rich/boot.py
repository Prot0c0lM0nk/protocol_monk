"""Boot animation for Protocol Monk.

Implements an animated boot sequence with ASCII art reveal and
real phase progress indicators.
"""

from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable

from rich import box
from rich.align import Align
from rich.console import Console, RenderableType
from rich.live import Live
from rich.panel import Panel
from rich.text import Text

from .styles import console as default_console


class BootPhase(Enum):
    """Boot phases for progress tracking."""

    CONFIGURATION = "Loading Configuration"
    WIRING = "Wiring Components"
    SERVICES = "Starting Services"
    UI = "Starting Rich UI"


# ASCII Art Assets
ART_HEBREW = r"""
 _
| |____ _______ ________ __  __   _______ ________  ______ __________   __________ ______ ____
|____  |.  __  |.  ___  |  \/  | |____  .|.  ___  ||____  |.  ___  \ \ / /.  ___  |____  |  _ \
    / / | |  | || |   | | |\/| |      | | | |   | |     | || |   | |  V / | |   | |    | | |_) |
   / /  | | _| || |___| | |  | |      | | | |___| |_____| || |___| | |\ \ | |___| |    | |  __/
  /_/   |_||___||_______|_|  |_|      | | |_______/________/_______|_| \_\|_______|    |_|_|
                                      |_|
"""

ART_GREEK = r"""
 _______                            __       __   __
(   _   )                           \ \     |  \ /  |
 | | | | ___   ___ ___ _____   _____ \ \    |   v   | ___  _  ___  __
 | | | |/ _ \ / _ (   ) _ \ \ / / _ \ > \   | |\_/| |/ _ \| |/ / |/ /
 | | | | |_) | (_) ) ( (_) ) v ( (_) ) ^ \  | |   | ( (_) ) / /|   <
 |_| |_|  __/ \___/ \_)___/ > < \___/_/ \_\ |_|   |_|\___/|__/ |_|\_\
       | |                 / ^ \
       |_|                /_/ \_\
"""

ART_RUSSIAN = r"""
##### ####   ###  #####  ###  #   #  ###  #####     #   #  ###  #   # #   #
#   # #   # #   #   #   #   # #   # #   #  #  #     ## ## #   # #   # #  #
#   # ####  #   #   #   #   #  #### #   #  #  #     # # # #   # ##### ###
#   # #     #   #   #   #   #     # #   #  #  #     #   # #   # #   # #  #
#   # #      ###    #    ###      #  ###  #   #     #   #  ###  #   # #   #
"""

ART_FINAL = r"""
▗▄▄▖  ▄▄▄ ▄▄▄     ■   ▄▄▄  ▗▞▀▘ ▄▄▄  █     ▗▖  ▗▖ ▄▄▄  ▄▄▄▄  █  ▄
▐▌ ▐▌█   █   █ ▗▄▟▙▄▖█   █ ▝▚▄▖█   █ █     ▐▛▚▞▜▌█   █ █   █ █▄▀
▐▛▀▘ █   ▀▄▄▄▀   ▐▌  ▀▄▄▄▀     ▀▄▄▄▀ █     ▐▌  ▐▌▀▄▄▄▀ █   █ █ ▀▄
▐▌               ▐▌                  █     ▐▌  ▐▌            █  █
                 ▐▌
"""

# Glitch characters for corruption effects
GLITCH_CHARS = "▓▒░█▄▀■□▪▫▲▼◄►◆◇○●◎◐◑★☆☂☀☁☽☾♠♣♥♦♪♫€¥£¢∞§¶†‡"

# Fixed panel width for consistent sizing
_PADDINGS = (5, 20)  # (vertical, horizontal)
_GLOBAL_MAX_CONTENT_WIDTH = max(
    len(line)
    for art in (ART_HEBREW, ART_GREEK, ART_RUSSIAN, ART_FINAL)
    for line in art.strip("\n").split("\n")
)
_GLOBAL_PANEL_WIDTH = _GLOBAL_MAX_CONTENT_WIDTH + (_PADDINGS[1] * 2) + 2

# Pre-computed art data
_ART_LINES: dict = {}
_ART_MAX_LENGTH: dict = {}


def _get_art_lines(art: str) -> list:
    """Cache art lines to avoid repeated splitting."""
    if art not in _ART_LINES:
        _ART_LINES[art] = art.strip("\n").split("\n")
        _ART_MAX_LENGTH[art] = max(len(line) for line in _ART_LINES[art])
    return _ART_LINES[art]


def _get_max_length(art: str) -> int:
    """Get cached max line length."""
    if art not in _ART_MAX_LENGTH:
        _get_art_lines(art)
    return _ART_MAX_LENGTH[art]


def corrupt_text(text: str, intensity: float = 0.3) -> str:
    """Apply glitch corruption to text based on intensity (0.0-1.0)."""
    if intensity <= 0:
        return text
    return "".join(
        random.choice(GLITCH_CHARS) if char.strip() and random.random() < intensity else char
        for char in text
    )


def progressive_reveal(art: str, progress: float) -> str:
    """Reveal characters progressively based on progress (0.0-1.0)."""
    lines = _get_art_lines(art)
    total_chars = sum(len(line) for line in lines)
    chars_to_show = int(total_chars * progress)

    result = []
    chars_shown = 0
    for line in lines:
        line_len = len(line)
        if chars_shown >= chars_to_show:
            result.append(" " * line_len)
        elif chars_shown + line_len <= chars_to_show:
            result.append(line)
            chars_shown += line_len
        else:
            reveal_count = chars_to_show - chars_shown
            result.append(line[:reveal_count] + " " * (line_len - reveal_count))
            chars_shown = chars_to_show
    return "\n".join(result)


@dataclass
class BootState:
    """State for the boot animation."""

    phase: BootPhase = BootPhase.CONFIGURATION
    progress: float = 0.0
    message: str = ""
    current_art: str = ART_HEBREW
    current_style: str = "red"


class BootAnimation:
    """Manages the boot animation with phase progress."""

    PHASE_SEQUENCE = [
        (ART_HEBREW, "red", "DECODING ANCIENT PROTOCOLS..."),
        (ART_GREEK, "yellow", "TRANSMITTING BYZANTINE WISDOM..."),
        (ART_RUSSIAN, "cyan", "ESTABLISHING MONASTIC LINK..."),
        (ART_FINAL, "monk.border", "ORTHODOX PROTOCOL v1.0 INITIALIZED"),
    ]

    def __init__(self, console: Console | None = None) -> None:
        self._console = console or default_console
        self._state = BootState()
        self._live: Live | None = None
        self._phase_index = 0
        self._running = False

    def _get_panel(
        self,
        art: str,
        style: str = "monk.border",
        status_text: str = "",
        signal_strength: float = 1.0,
        corruption: float = 0.0,
    ) -> Panel:
        """Create a panel with the ASCII art."""
        lines = _get_art_lines(art)
        max_length = _get_max_length(art)

        display_art = "\n".join(lines)

        if corruption > 0:
            display_art = corrupt_text(display_art, corruption)

        # Normalize line lengths
        left_pad = max((_GLOBAL_MAX_CONTENT_WIDTH - max_length) // 2, 0)
        right_pad = max(_GLOBAL_MAX_CONTENT_WIDTH - max_length - left_pad, 0)
        normalized_lines = [
            (" " * left_pad) + line.ljust(max_length) + (" " * right_pad)
            for line in display_art.split("\n")
        ]
        normalized_art = "\n".join(normalized_lines)

        # Build signal indicator
        filled = int(signal_strength * 10)
        bars = "█" * filled + "░" * (10 - filled)
        percentage = int(signal_strength * 100)

        color = "green" if signal_strength > 0.7 else "yellow" if signal_strength > 0.4 else "red"

        signal_text = Text()
        if status_text:
            signal_text.append(status_text, style="dim")
            signal_text.append("  ")
        signal_text.append("SIGNAL: ", style="bold")
        signal_text.append(bars, style=color)
        signal_text.append(f" {percentage}%", style=color)

        content = Text()
        content.append(normalized_art, style=style)
        content.append("\n\n")
        content.append(signal_text)

        return Panel(
            Align.center(content),
            box=box.DOUBLE,
            border_style=style,
            expand=False,
            padding=_PADDINGS,
            width=_GLOBAL_PANEL_WIDTH,
        )

    def update_phase(self, phase: BootPhase, message: str = "") -> None:
        """Update the current boot phase.

        Args:
            phase: The current boot phase
            message: Optional status message

        """
        self._state.phase = phase
        self._state.message = message

        # Map phase to sequence index
        phase_to_index = {
            BootPhase.CONFIGURATION: 0,
            BootPhase.WIRING: 1,
            BootPhase.SERVICES: 2,
            BootPhase.UI: 3,
        }
        self._phase_index = phase_to_index.get(phase, 0)

        # Update art and style based on phase
        if self._phase_index < len(self.PHASE_SEQUENCE):
            art, style, _ = self.PHASE_SEQUENCE[self._phase_index]
            self._state.current_art = art
            self._state.current_style = style

        # Update progress
        progress_values = {
            BootPhase.CONFIGURATION: 0.25,
            BootPhase.WIRING: 0.50,
            BootPhase.SERVICES: 0.75,
            BootPhase.UI: 1.0,
        }
        self._state.progress = progress_values.get(phase, 0.0)

        # Update live display if running
        if self._live and self._running:
            self._live.update(self._get_panel(
                self._state.current_art,
                self._state.current_style,
                status_text=message or self._state.phase.value,
                signal_strength=self._state.progress,
            ))

    async def run_animation(self, duration_per_art: float = 1.5) -> None:
        """Run the animated boot sequence.

        This runs independently and can be updated via update_phase().

        Args:
            duration_per_art: Base duration for each ASCII art piece

        """
        self._running = True

        with Live(console=self._console, refresh_per_second=20, transient=True) as live:
            self._live = live

            for idx, (art, style, message) in enumerate(self.PHASE_SEQUENCE):
                # Check if we should skip to current phase
                if idx < self._phase_index:
                    continue

                start_signal = idx / len(self.PHASE_SEQUENCE)
                end_signal = (idx + 1) / len(self.PHASE_SEQUENCE)
                is_final = idx == len(self.PHASE_SEQUENCE) - 1

                # Acquisition frames
                for frame in range(6):
                    corruption = 0.5 - (frame / 6) * 0.3
                    signal = start_signal + (end_signal - start_signal) * (frame / 12)
                    live.update(self._get_panel(
                        art, style,
                        status_text=message,
                        signal_strength=signal,
                        corruption=corruption,
                    ))
                    await asyncio.sleep(0.06)

                # Reveal frames
                for step in range(16):
                    progress = step / 15
                    revealed = progressive_reveal(art, progress)
                    corruption = 0.3 * (1 - progress)
                    signal = start_signal + (end_signal - start_signal) * ((step + 6) / 20)
                    live.update(self._get_panel(
                        revealed, style,
                        status_text=message,
                        signal_strength=signal,
                        corruption=corruption,
                    ))
                    await asyncio.sleep(0.04)

                # Lock frames (not for final)
                if not is_final:
                    for _ in range(3):
                        live.update(self._get_panel(
                            art, style,
                            status_text=f"{message} — LOCKED",
                            signal_strength=end_signal,
                        ))
                        await asyncio.sleep(0.08)

            # Final static display
            final_panel = self._get_panel(
                ART_FINAL,
                "monk.border",
                status_text="ORTHODOX PROTOCOL v1.0 — SYSTEM READY",
                signal_strength=1.0,
            )
            live.update(final_panel)
            await asyncio.sleep(0.3)

        self._running = False
        self._live = None

        # Print final banner to remain on screen
        self._console.print(final_panel)
        self._console.print()

    def run_sync(self, duration_per_art: float = 1.5) -> None:
        """Synchronous wrapper for run_animation."""
        asyncio.run(self.run_animation(duration_per_art))


def run_boot_sequence(console: Console | None = None) -> None:
    """Run the boot sequence synchronously (blocking).

    This is the simple API for running the full boot animation.

    Args:
        console: Rich console to use

    """
    boot = BootAnimation(console)
    boot.run_sync()


async def run_boot_sequence_async(console: Console | None = None) -> BootAnimation:
    """Run the boot sequence asynchronously.

    Returns the BootAnimation instance so phase updates can be applied.

    Args:
        console: Rich console to use

    Returns:
        BootAnimation instance for phase updates

    """
    boot = BootAnimation(console)
    await boot.run_animation()
    return boot


async def run_boot_with_phases(
    console: Console | None = None,
    phase_callback: Callable[[BootAnimation], None] | None = None,
) -> BootAnimation:
    """Run boot animation with phase callback support.

    This runs the boot animation and calls the callback at appropriate
    points to allow external phase updates.

    Args:
        console: Rich console to use
        phase_callback: Optional callback for phase updates

    Returns:
        BootAnimation instance

    """
    boot = BootAnimation(console)

    # Run animation in background while phases progress
    animation_task = asyncio.create_task(boot.run_animation(duration_per_art=0.5))

    # Give animation time to start
    await asyncio.sleep(0.1)

    # Call phase callback if provided
    if phase_callback:
        phase_callback(boot)

    # Wait for animation to complete
    await animation_task

    return boot
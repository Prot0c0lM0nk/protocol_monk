"""
ui/textual/screens/startup.py
Cinematic startup screen for Protocol Monk TUI.
"""

from __future__ import annotations

import asyncio
import random
import time
from typing import Iterable

from rich.align import Align
from rich.text import Text
from textual.binding import Binding
from textual.containers import Container, Vertical
from textual.screen import Screen
from textual.widgets import Static

# Startup art is defined locally so Textual startup has no dependency on Rich boot code.
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


class CinematicStartupScreen(Screen[bool]):
    """Non-blocking cinematic intro before entering the main chat screen."""

    BINDINGS = [
        Binding("enter", "skip", "Skip Intro", show=False),
        Binding("escape", "skip", "Skip Intro", show=False),
    ]

    _RAIN_CHARS = "░▒▓█▌▐╱╲╳"
    _RARE_GLYPHS = "☦†✠"

    _PHASES = [
        (ART_HEBREW, "DECODING ANCIENT PROTOCOLS...", "red"),
        (ART_GREEK, "TRANSMITTING BYZANTINE WISDOM...", "yellow"),
        (ART_RUSSIAN, "ESTABLISHING MONASTIC LINK...", "cyan"),
        (ART_FINAL, "ORTHODOX PROTOCOL v1.0 INITIALIZED", "green"),
    ]

    def __init__(self, min_runtime: float = 4.5) -> None:
        super().__init__()
        self._min_runtime = min_runtime
        self._started_at = 0.0
        self._rain_lines: list[str] = []
        self._rain_timer = None
        self._sequence_task: asyncio.Task | None = None
        self._completed = False

    def compose(self):
        with Container(id="startup-root"):
            yield Static("", id="startup-atmosphere")
            with Vertical(id="startup-panel"):
                yield Static("PROTOCOL MONK", id="startup-title")
                yield Static("Textual Interface Initialization", id="startup-subtitle")
                yield Static("", id="startup-art")
                yield Static("", id="startup-status")
                yield Static("", id="startup-progress")
                yield Static("Press Enter to skip", id="startup-hint")

    def on_mount(self) -> None:
        self._started_at = time.perf_counter()
        self._seed_rain()
        self._rain_timer = self.set_interval(0.09, self._tick_rain)
        self._sequence_task = asyncio.create_task(self._run_sequence())

    async def _run_sequence(self) -> None:
        try:
            phase_count = len(self._PHASES)
            for idx, (art, status_text, color) in enumerate(self._PHASES):
                await self._animate_phase(
                    art=art,
                    status_text=status_text,
                    color=color,
                    phase_idx=idx,
                    total_phases=phase_count,
                )
                await asyncio.sleep(0.14)

            await self._respect_min_runtime()
        except asyncio.CancelledError:
            pass
        finally:
            self._finish()

    async def _animate_phase(
        self,
        art: str,
        status_text: str,
        color: str,
        phase_idx: int,
        total_phases: int,
    ) -> None:
        self.query_one("#startup-status", Static).update(status_text)
        lines = art.strip("\n").splitlines()
        frame_count = 16 if phase_idx == total_phases - 1 else 20

        for frame in range(frame_count + 1):
            progress = frame / frame_count
            ratio = (phase_idx + progress) / total_phases
            shown_art = self._progressive_reveal(lines, progress)
            art_text = Text(shown_art, style=f"bold {color}")
            self.query_one("#startup-art", Static).update(Align.center(art_text))
            self.query_one("#startup-subtitle", Static).update(
                f"Phase {phase_idx + 1}/{total_phases}"
            )
            self.query_one("#startup-progress", Static).update(
                self._render_progress_bar(ratio)
            )
            await asyncio.sleep(0.05 if phase_idx < total_phases - 1 else 0.06)

    def _progressive_reveal(self, lines: Iterable[str], progress: float) -> str:
        materialized_lines = list(lines)
        total_chars = sum(len(line) for line in materialized_lines)
        visible_chars = int(total_chars * progress)
        built: list[str] = []
        shown = 0

        for line in materialized_lines:
            line_len = len(line)
            if shown >= visible_chars:
                built.append(" " * line_len)
            elif shown + line_len <= visible_chars:
                built.append(self._add_flicker(line, phase="full"))
                shown += line_len
            else:
                visible_in_line = visible_chars - shown
                visible = self._add_flicker(line[:visible_in_line], phase="edge")
                hidden = " " * (line_len - visible_in_line)
                built.append(visible + hidden)
                shown = visible_chars

        return "\n".join(built)

    def _add_flicker(self, text: str, phase: str) -> str:
        if not text.strip():
            return text
        chance = 0.025 if phase == "full" else 0.08
        out = []
        for char in text:
            if char != " " and random.random() < chance:
                out.append(random.choice(self._RAIN_CHARS))
            else:
                out.append(char)
        return "".join(out)

    def _render_progress_bar(self, ratio: float, width: int = 34) -> Text:
        ratio = max(0.0, min(1.0, ratio))
        filled = int(width * ratio)
        empty = width - filled
        pct = int(ratio * 100)

        bar = Text()
        bar.append("[" , style="bold #7da9f8")
        bar.append("█" * filled, style="bold #7da9f8")
        bar.append("░" * empty, style="#305080")
        bar.append("]", style="bold #7da9f8")
        bar.append(f" {pct:>3}% ", style="bold #9ec6ff")
        return bar

    def _seed_rain(self) -> None:
        width = max(self.size.width - 8, 40)
        self._rain_lines = [self._make_rain_line(width) for _ in range(6)]
        self.query_one("#startup-atmosphere", Static).update("\n".join(self._rain_lines))

    def _tick_rain(self) -> None:
        if not self.is_mounted:
            return
        width = max(self.size.width - 8, 40)
        self._rain_lines.pop(0)
        self._rain_lines.append(self._make_rain_line(width))
        self.query_one("#startup-atmosphere", Static).update("\n".join(self._rain_lines))

    def _make_rain_line(self, width: int) -> str:
        line = []
        for _ in range(width):
            roll = random.random()
            if roll < 0.32:
                line.append(random.choice(self._RAIN_CHARS))
            elif roll < 0.34:
                line.append(random.choice(self._RARE_GLYPHS))
            else:
                line.append(" ")
        return "".join(line)

    async def _respect_min_runtime(self) -> None:
        elapsed = time.perf_counter() - self._started_at
        remaining = self._min_runtime - elapsed
        if remaining > 0:
            await asyncio.sleep(remaining)

    def action_skip(self) -> None:
        if self._sequence_task and not self._sequence_task.done():
            self._sequence_task.cancel()

    def _finish(self) -> None:
        if self._completed:
            return
        self._completed = True
        if self._rain_timer is not None:
            self._rain_timer.stop()
        try:
            self.dismiss(True)
        except Exception:
            pass

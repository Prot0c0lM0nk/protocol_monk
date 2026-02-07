"""
ui/textual/screens/startup.py
Textual startup screen powered by a non-ANSI custom matrix harness.
"""

from __future__ import annotations

import asyncio
import random
import time
import unicodedata
from typing import Optional

from textual.binding import Binding
from textual.containers import Container, Vertical
from textual.screen import Screen
from textual.widgets import Static

from ui.custom_matrix import CHAOS_CHARS, ILLUMINATION_CHARS, PRAYER_CHARS


def _sanitize_charset(chars: str) -> str:
    """Keep printable single-cell glyphs to avoid Textual layout wrapping."""
    clean: list[str] = []
    for char in chars:
        if not char.isprintable():
            continue
        if unicodedata.combining(char):
            continue
        if unicodedata.east_asian_width(char) in {"W", "F"}:
            continue
        clean.append(char)
    return "".join(clean)


CHAOS_POOL = _sanitize_charset(CHAOS_CHARS) or "01/\\|-_"
ILLUMINATION_POOL = _sanitize_charset(ILLUMINATION_CHARS) or "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
PRAYER_POOL = _sanitize_charset(PRAYER_CHARS) or "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"


class MatrixHarness:
    """Generate matrix-style frames without ANSI escapes."""

    def __init__(self, width: int, height: int) -> None:
        self.width = max(20, width)
        self.height = max(6, height)
        self._drops: list[dict] = []
        self._reset_drops()

    def resize(self, width: int, height: int) -> None:
        width = max(20, width)
        height = max(6, height)
        if width == self.width and height == self.height:
            return
        self.width = width
        self.height = height
        self._reset_drops()

    def _reset_drops(self) -> None:
        self._drops = []
        for _ in range(self.width):
            self._drops.append(
                {
                    "head": random.randint(0, self.height),
                    "length": random.randint(4, 14),
                    "speed": random.randint(1, 3),
                    "tick": random.randint(0, 2),
                }
            )
        # Extra streams increase coverage so the full panel looks active.
        for _ in range(max(8, self.width // 3)):
            self._drops.append(
                {
                    "col": random.randint(0, self.width - 1),
                    "head": random.randint(-self.height // 2, self.height),
                    "length": random.randint(3, 10),
                    "speed": random.randint(1, 3),
                    "tick": random.randint(0, 2),
                }
            )

    def _pick_char(self, progress: float) -> str:
        if progress < 0.35:
            char_set = CHAOS_POOL
        elif progress < 0.75:
            char_set = ILLUMINATION_POOL
        else:
            char_set = PRAYER_POOL
        return random.choice(char_set)

    def _overlay_title(self, grid: list[list[str]], progress: float) -> None:
        if self.height < 3:
            return

        title = "PROTOCOL.MONK"
        subtitle = "Booting up. The Kingdom is at hand. Delete the false world."
        reveal = 0.0 if progress < 0.35 else min(1.0, (progress - 0.35) / 0.6)
        reveal_count = int(len(title) * reveal)

        title_line = list(" " * len(title))
        for idx, char in enumerate(title):
            if idx < reveal_count:
                title_line[idx] = char
            elif char != " " and random.random() < 0.18:
                title_line[idx] = self._pick_char(progress)

        title_text = "".join(title_line)
        start_col = max(0, (self.width - len(title_text)) // 2)
        title_row = self.height // 2 - 1
        if 0 <= title_row < self.height:
            for idx, char in enumerate(title_text):
                col = start_col + idx
                if 0 <= col < self.width and char != " ":
                    grid[title_row][col] = char

        if reveal >= 0.65:
            sub_start = max(0, (self.width - len(subtitle)) // 2)
            sub_row = title_row + 2
            if 0 <= sub_row < self.height:
                for idx, char in enumerate(subtitle):
                    col = sub_start + idx
                    if 0 <= col < self.width and char != " ":
                        grid[sub_row][col] = char

    def step(self, progress: float) -> str:
        grid = [[" " for _ in range(self.width)] for _ in range(self.height)]

        for idx, drop in enumerate(self._drops):
            col = drop.get("col", idx % self.width)
            drop["tick"] += 1
            if drop["tick"] >= drop["speed"]:
                drop["tick"] = 0
                drop["head"] += 1

            if drop["head"] - drop["length"] > self.height + random.randint(0, 6):
                drop["head"] = random.randint(-self.height // 3, 0)
                drop["length"] = random.randint(4, 14)
                drop["speed"] = random.randint(1, 3)

            for tail in range(drop["length"]):
                row = drop["head"] - tail
                if 0 <= row < self.height:
                    grid[row][col] = self._pick_char(progress)

        # Low-intensity ambient rain to avoid empty dead zones in wide panels.
        ambient = 0.028 if progress < 0.6 else 0.018
        for row in range(self.height):
            for col in range(self.width):
                if grid[row][col] == " " and random.random() < ambient:
                    grid[row][col] = self._pick_char(progress)

        self._overlay_title(grid, progress)
        return "\n".join("".join(line) for line in grid)


class CinematicStartupScreen(Screen[bool]):
    """Matrix startup that runs while the agent initializes in the background."""

    BINDINGS = [
        Binding("enter", "skip", "Skip Intro", show=False),
        Binding("escape", "skip", "Skip Intro", show=False),
    ]

    def __init__(
        self,
        ready_task: Optional[asyncio.Task] = None,
        min_runtime: float = 4.0,
    ) -> None:
        super().__init__()
        self._ready_task = ready_task
        self._min_runtime = min_runtime
        self._start_time = 0.0
        self._skip_requested = False
        self._completed = False
        self._harness: Optional[MatrixHarness] = None
        self._frame_timer = None
        self._sequence_task: Optional[asyncio.Task] = None

    def compose(self):
        with Container(id="startup-root"):
            with Vertical(id="startup-panel"):
                yield Static("", id="startup-matrix")
                yield Static("", id="startup-status")
                yield Static("", id="startup-progress")
                yield Static("Press Enter to skip intro", id="startup-hint")

    def on_mount(self) -> None:
        self._start_time = time.perf_counter()
        self._init_harness()
        self._frame_timer = self.set_interval(0.06, self._tick_frame)
        self._sequence_task = asyncio.create_task(self._run_sequence())

    def _init_harness(self) -> None:
        width, height = self._measure_matrix_area()
        if self._harness is None:
            self._harness = MatrixHarness(width, height)
        else:
            self._harness.resize(width, height)

    def _measure_matrix_area(self) -> tuple[int, int]:
        matrix = self.query_one("#startup-matrix", Static)
        # size can be very small at mount; keep updating until layout settles.
        width = matrix.size.width
        height = matrix.size.height

        if width < 8:
            width = self.size.width - 4
        if height < 4:
            height = self.size.height - 8

        return max(30, width - 2), max(8, height - 2)

    def _tick_frame(self) -> None:
        if not self.is_mounted or self._harness is None:
            return
        width, height = self._measure_matrix_area()
        self._harness.resize(width, height)

        elapsed = time.perf_counter() - self._start_time
        target_runtime = 0.0 if self._skip_requested else self._min_runtime
        progress = 1.0 if target_runtime == 0 else min(1.0, elapsed / target_runtime)
        frame = self._harness.step(progress)
        self.query_one("#startup-matrix", Static).update(frame)

    async def _run_sequence(self) -> None:
        try:
            while True:
                elapsed = time.perf_counter() - self._start_time
                target_runtime = 0.0 if self._skip_requested else self._min_runtime
                progress = (
                    1.0 if target_runtime == 0 else min(1.0, elapsed / target_runtime)
                )
                ready = self._ready_task is None or self._ready_task.done()

                self.query_one("#startup-status", Static).update(
                    self._status_line(progress, ready)
                )
                self.query_one("#startup-progress", Static).update(
                    self._progress_line(progress, ready)
                )

                if progress >= 1.0 and ready:
                    break
                await asyncio.sleep(0.06)

            if self._ready_task and self._ready_task.done():
                try:
                    await self._ready_task
                except Exception:
                    pass

        except asyncio.CancelledError:
            pass
        finally:
            self._finish()

    def _status_line(self, progress: float, ready: bool) -> str:
        if self._ready_task and self._ready_task.done():
            try:
                self._ready_task.result()
            except Exception:
                return "Agent initialization failed. Starting interface with warnings."

        if not ready and progress < 0.35:
            return "Calibrating matrix harness..."
        if not ready:
            return "Agent service initializing in background..."
        if ready and progress < 1.0:
            return "Agent ready. Finalizing terminal handshake..."
        return "Agent online. Entering chat."

    def _progress_line(self, progress: float, ready: bool, width: int = 34) -> str:
        fill = int(progress * width)
        bar = "█" * fill + "░" * (width - fill)
        percent = int(progress * 100)
        init_state = "READY" if ready else "LOADING"
        return f"[{bar}] {percent:>3}%  AGENT:{init_state}"

    def action_skip(self) -> None:
        self._skip_requested = True
        self.query_one("#startup-hint", Static).update("Skip requested...")

    def _finish(self) -> None:
        if self._completed:
            return
        self._completed = True
        if self._frame_timer is not None:
            self._frame_timer.stop()
        try:
            self.dismiss(True)
        except Exception:
            pass

"""
Prayer Rope Progress Indicators
Orthodox-themed spinners and progress bars for AI thinking states
"""

import time
import random
from typing import Optional, List
from rich.console import Console
from rich.live import Live
from rich.text import Text
from rich.spinner import Spinner
from contextlib import contextmanager


class PrayerRope:
    """Prayer rope (chotki/komboskini) themed progress indicators"""

    # Prayer rope symbols
    KNOT = "☦"
    EMPTY = "—"

    # Greek letters for contemplation
    GREEK_LETTERS = "αβγδεζηθικλμνξοπρστυφχψω"

    # Whispered prayers (short fragments)
    WHISPERS = [
        "Κύριε...",
        "ἐλέησον...",
        "Χριστέ...",
        "Φῶς...",
        "Λόγος...",
        "Σοφία...",
    ]

    def __init__(self, total_knots: int = 5):
        self.total_knots = total_knots
        self.console = Console()

    def render(self, completed: int) -> Text:
        """Render prayer rope with completed knots"""
        rope = Text()

        for i in range(self.total_knots):
            if i < completed:
                rope.append(self.KNOT, style="bold #44ff44")
            else:
                rope.append(self.EMPTY, style="dim #888888")

            # Add separator between knots
            if i < self.total_knots - 1:
                rope.append("—", style="dim #444444")

        return rope

    def with_whisper(self, completed: int) -> Text:
        """Prayer rope with whispered Greek text"""
        result = Text()
        result.append("[", style="dim")
        result.append(self.render(completed))
        result.append("]", style="dim")
        result.append(" ")

        # Add whisper
        whisper = random.choice(self.WHISPERS)
        result.append(whisper, style="italic dim #888888")

        return result


class ThinkingSpinner:
    """Simple Orthodox cross spinner for contemplation"""

    CROSSES = ["☦", "†", "✠", "☩"]

    def __init__(self):
        self.console = Console()
        self.frame = 0

    def render(self) -> Text:
        """Render current spinner frame"""
        cross = self.CROSSES[self.frame % len(self.CROSSES)]
        result = Text()
        result.append(cross, style="bold #44ff44")
        result.append(" contemplating...", style="dim #888888")
        return result

    def next_frame(self):
        """Advance to next spinner frame"""
        self.frame += 1


class ProtocolSpinner:
    def __init__(self):
        # Create a custom spinner pattern using the cross symbols
        self.frames = [
            "[bold green]☦ contemplating...[/bold green]",
            "[bold green]† contemplating...[/bold green]",
            "[bold green]✠ contemplating...[/bold green]",
            "[bold green]☩ contemplating...[/bold green]",
        ]
        self.frame_index = 0

    def render(self, style=None):
        """Render the current frame of the spinner"""
        return self.frames[self.frame_index % len(self.frames)]

    def next_frame(self):
        """Advance to the next frame"""
        self.frame_index += 1


# class GreekLetterSpinner:
class ThinkingSpinner:
    """Simple Orthodox cross spinner for contemplation"""

    CROSSES = ["☦", "†", "✠", "☩"]

    def __init__(self):
        self.console = Console()
        self.frame = 0

    def render(self) -> Text:
        """Render current spinner frame"""
        cross = self.CROSSES[self.frame % len(self.CROSSES)]
        result = Text()
        result.append(cross, style="bold #44ff44")
        result.append(" contemplating...", style="dim #888888")
        return result

    def next_frame(self):
        """Advance to next spinner frame"""
        self.frame += 1


class GreekLetterSpinner:
    """Cycling Greek letters for contemplative waiting"""

    def __init__(self):
        self.console = Console()
        self.frame = 0
        self.letters = "ΑΒΓΔΕΖΗΘΙΚΛΜΝΞΟΠΡΣΤΥΦΧΨΩαβγδεζηθικλμνξοπρστυφχψω"

    def render(self) -> Text:
        """Render current letter"""
        letter = self.letters[self.frame % len(self.letters)]
        result = Text()
        result.append(letter, style="bold #ffaa44")
        result.append(" ", style="dim")
        return result

    def next_frame(self):
        """Advance to next letter"""
        self.frame += 1


@contextmanager
def prayer_rope_progress(console: Optional[Console] = None, message: str = ""):
    """
    Context manager for prayer rope progress during AI streaming

    Usage:
        with prayer_rope_progress(console, "Contemplating your request"):
            # Your streaming code here
            update_progress(20)  # 1 knot
            update_progress(40)  # 2 knots
            # etc.
    """
    if console is None:
        console = Console()

    rope = PrayerRope(total_knots=5)
    current_knots = 0

    # Create display text
    display = Text()
    if message:
        display.append(message, style="dim #888888")
        display.append(" ", style="dim")
    display.append(rope.render(current_knots))

    live = Live(display, console=console, refresh_per_second=4, transient=True)
    live.start()

    class Progress:
        def update(self, percent: float):
            nonlocal current_knots
            knots = int((percent / 100) * rope.total_knots)
            if knots != current_knots:
                current_knots = knots
                display = Text()
                if message:
                    display.append(message, style="dim #888888")
                    display.append(" ", style="dim")
                display.append(rope.with_whisper(current_knots))
                live.update(display)

    try:
        yield Progress()
    finally:
        live.stop()


@contextmanager
def thinking_spinner(console: Optional[Console] = None, message: str = "contemplating"):
    """
    Simple spinner for short waits

    Usage:
        with thinking_spinner(console, "processing"):
            # Your code here
            pass
    """
    if console is None:
        console = Console()

    spinner = ThinkingSpinner()

    display = Text()
    display.append(spinner.render())

    live = Live(display, console=console, refresh_per_second=2, transient=True)
    live.start()

    # Update spinner in background
    import threading

    stop_event = threading.Event()

    def update_loop():
        while not stop_event.is_set():
            spinner.next_frame()
            display = Text()
            display.append(spinner.render())
            live.update(display)
            time.sleep(0.5)

    thread = threading.Thread(target=update_loop, daemon=True)
    thread.start()

    try:
        yield
    finally:
        stop_event.set()
        thread.join(timeout=0.1)
        live.stop()


@contextmanager
def greek_letter_spinner(console: Optional[Console] = None):
    """
    Greek letter cycling spinner

    Usage:
        with greek_letter_spinner(console):
            # Your code here
            pass
    """
    if console is None:
        console = Console()

    spinner = GreekLetterSpinner()

    display = Text()
    display.append(spinner.render())

    live = Live(display, console=console, refresh_per_second=8, transient=True)
    live.start()

    # Update spinner in background
    import threading

    stop_event = threading.Event()

    def update_loop():
        while not stop_event.is_set():
            spinner.next_frame()
            display = Text()
            display.append(spinner.render())
            live.update(display)
            time.sleep(0.125)

    thread = threading.Thread(target=update_loop, daemon=True)
    thread.start()

    try:
        yield
    finally:
        stop_event.set()
        thread.join(timeout=0.1)
        live.stop()


def demo_prayer_rope():
    """Demo the prayer rope progress"""
    console = Console()
    console.print("\n[bold #44ff44]Prayer Rope Progress Demo[/bold #44ff44]\n")

    rope = PrayerRope()

    # Show progressive filling: 0% → 100% (6 states for 5 knots)
    console.print(
        f"[dim]Showing {rope.total_knots} knots in {rope.total_knots + 1} states (0% → 100%):[/dim]\n"
    )
    for i in range(rope.total_knots + 1):
        percent = int((i / rope.total_knots) * 100)
        console.print(f"[dim]{percent:3d}%[/dim] ", end="")
        console.print(rope.with_whisper(i))
        time.sleep(0.8)

    console.print("\n[bold #44ff44]With Context Manager:[/bold #44ff44]\n")

    with prayer_rope_progress(console, "Processing") as progress:
        for i in range(0, 101, 20):
            progress.update(i)
            time.sleep(0.5)


def demo_spinners():
    """Demo all spinner types"""
    console = Console()

    console.print("\n[bold #44ff44]Thinking Spinner:[/bold #44ff44]\n")
    with thinking_spinner(console):
        time.sleep(3)

    console.print("\n[bold #44ff44]Greek Letter Spinner:[/bold #44ff44]\n")
    with greek_letter_spinner(console):
        time.sleep(3)


if __name__ == "__main__":
    demo_prayer_rope()
    demo_spinners()

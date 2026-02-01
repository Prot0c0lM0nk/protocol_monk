# ui/animations.py

import datetime

import random
import sys
import time
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.text import Text
from typing import Optional

from .custom_matrix import run_animation, run_enhanced_matrix_intro

# --- NEW STARTUP SEQUENCE ---


def play_startup_sequence(duration: float = 10) -> None:
    """Plays the custom Matrix rain animation for a set duration."""
    print("Initializing custom startup sequence...")
    run_animation(duration=duration)
    print("Sequence complete.")


# --- CINEMATIC "DESCENT OF THE LOGOS" SEQUENCE ---


def display_logos_intro() -> None:
    """Phase 0: Void - 'In the beginning was the Logos' - Rich version"""
    console = Console()
    console.clear()
    console.show_cursor(False)

    verses = [
        "In the beginning was the Logos...",
        "and the Logos was with God...",
        "and the Logos is God.",
    ]

    try:
        center_row = max(3, console.size.height // 2 - 2)
        width = console.size.width
    except (AttributeError, OSError):
        center_row = 5
        width = 80

    for i, verse in enumerate(verses):
        # Center the verse
        padding = " " * max(0, (width - len(verse)) // 2)
        full_line = padding + verse

        # Print with typewriter effect
        for j, char in enumerate(full_line):
            if j < len(padding):
                console.print(char, end="")
            else:
                console.print(f"[#44ff44]{char}[/]", end="", highlight=False)
            time.sleep(0.03)
        console.print()  # Newline
        time.sleep(0.5)

    time.sleep(1.0)
    console.clear()
    console.show_cursor(True)


def monk_challenge() -> None:
    """Phase 3: The Monk's Challenge - Rich + safe input"""
    console = Console()
    console.clear()
    console.show_cursor(False)

    try:
        challenge_text = "> AWAKEN, OR REMAIN IN CHAINS."
        timeout_text = "(Press any key within 30s)"
        symbols = ["☦", "†"]

        try:
            center_y = console.size.height // 2
            center_x = console.size.width // 2
        except (AttributeError, OSError):
            center_y = 12
            center_x = 40

        start_time = time.time()

        # Blinking cursor phase - plain text only
        with Live(console=console, refresh_per_second=4, transient=True) as live:
            while True:
                elapsed = time.time() - start_time
                if elapsed > 30:  # 30 second timeout
                    break
                cursor_sym = symbols[int(elapsed // 0.7) % 2]

                lines = []
                for i in range(console.size.height if hasattr(console, "size") else 24):
                    if i == center_y:
                        pad = " " * max(
                            0, (console.size.width - len(challenge_text)) // 2
                        )
                        lines.append(pad + challenge_text)  # ← PLAIN TEXT
                    elif i == center_y + 1:
                        # Show timeout notification
                        timeout_pad = " " * max(
                            0, (console.size.width - len(timeout_text)) // 2
                        )
                        lines.append(timeout_pad + timeout_text)
                    elif i == center_y + 2:
                        cursor_line = " " * (center_x - 1) + f" {cursor_sym} "
                        lines.append(cursor_line)
                    else:
                        lines.append("")

                live.update(Text("\n".join(lines)), refresh=True)

                # Check for input
                import sys

                if sys.platform == "win32":
                    import msvcrt

                    if msvcrt.kbhit():
                        msvcrt.getch()
                        break
                else:
                    import select

                    if select.select([sys.stdin], [], [], 0.1)[0]:
                        sys.stdin.readline()
                        break

                time.sleep(0.05)

        # AFTER Live loop - now print with RICH STYLING
        console.clear()
        console.print("\n" * (center_y - 1), end="")  # Position vertically
        pad = " " * max(0, (console.size.width - len(challenge_text)) // 2)
        console.print(pad, end="")
        console.print(f"[#44ff44]{challenge_text}[/]", highlight=False, end="")
        console.print("\n" * 2, end="")  # Space for cursor

        # Detonation flash - FULL SCREEN
        console.clear()
        try:
            height = min(console.size.height, 40)
            width = console.size.width
            flash_line = "[#ffffff]" + "█" * width + "[/]"
            for _ in range(height):
                console.print(flash_line, highlight=False)
            time.sleep(0.03)
        except (AttributeError, OSError):
            console.print("█" * 40)

        console.clear()
    finally:
        console.show_cursor(True)


def play_cinematic_intro_sequence() -> None:
    console = Console()
    try:
        display_logos_intro()
        smooth_transition(0.8)

        # Phase 1: Chaos Rain
        console.show_cursor(False)
        run_animation(duration=4, speed=150, glitches=200, frequency=150)
        smooth_transition(0.5)

        # Phase 2: Sanctified Rain (morph via run_enhanced_matrix_intro)
        run_enhanced_matrix_intro()  # Assume this now uses PRAYER_CHARS
        smooth_transition(0.8)

        # Phase 3: Monk's Challenge
        monk_challenge()
        smooth_transition(0.6)

        # Phase 4: Baptized Protocol
        display_protocol_message()
        smooth_transition(0.8)

        # Phase 5: Monk's Manifesto
        display_welcome_panel()

    except KeyboardInterrupt:
        console.clear()
        console.print("\n[#ffaa44]Cinematic sequence interrupted.[/]")
    except Exception as e:
        console.clear()
        console.print(f"\n[#ff4444]Error: {e}[/]")
        console.print("[#ffaa44]Continuing...[/]")
        time.sleep(1)
    finally:
        console.show_cursor(True)


def smooth_transition(duration: float = 1.0) -> None:
    """Create a smooth transition effect between screens."""
    from rich.live import Live
    from rich.text import Text

    console = Console()

    # Create fade-out effect
    transition_text = Text("", style="dim")

    with Live(transition_text, console=console, refresh_per_second=20) as live:
        # Brief pause
        time.sleep(duration * 0.3)

        # Add some visual elements during transition
        transition_chars = [".", "..", "...", "....", "....."]
        for chars in transition_chars:
            transition_text.plain = chars
            live.update(transition_text)
            time.sleep(duration * 0.1)

        # Clear and brief pause
        transition_text.plain = ""
        live.update(transition_text)
        time.sleep(duration * 0.2)

    console.clear()


def play_complete_intro_sequence() -> None:
    """
    Play the complete 4-screen intro sequence with smooth transitions.
    """
    try:
        # Screen 1: Enhanced Matrix Rain with PROTOCOL MONK
        run_enhanced_matrix_intro()
        smooth_transition(0.8)

        # Screen 2: Press Enter prompt
        wait_for_enter()
        smooth_transition(0.6)

        # Screen 3: Call trans opt message
        display_protocol_message()
        smooth_transition(0.8)

        # Screen 4: Welcome and tool registration
        display_welcome_panel()

    except KeyboardInterrupt:
        # Graceful handling of Ctrl+C
        console = Console()
        console.clear()
        console.print("\n[yellow]Intro sequence interrupted.[/yellow]")
        time.sleep(0.5)
    except Exception as e:
        # Fallback for any errors
        console = Console()
        console.clear()
        console.print(f"\n[red]Error in intro sequence: {e}[/red]")
        console.print("[yellow]Continuing to main application...[/yellow]")
        time.sleep(1)


# --- YOUR OTHER UI FUNCTIONS (UNCHANGED) ---
# This function remains the same
def typewriter_print(text: str, delay: float = 0.03) -> None:
    for char in text:
        print(char, end="", flush=True)
        time.sleep(delay)
    print()


def scramble_text_in(
    text: str, scramble_chars: int = 2, char_delay: float = 0.02
) -> None:
    """
    Display text with a scrambling effect that reveals characters from left to right.
    """
    from rich.live import Live

    console = Console()
    scramble_set = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%^&*()_+-=[]{}|;:,.<>?"
    lines = text.splitlines()

    for line in lines:
        if not line.strip():
            console.print()
            continue

        # Use Live context for smooth updating (reduced refresh rate to save CPU)
        revealed_text = Text()

        with Live(revealed_text, console=console, refresh_per_second=4) as live:
            for char in line:
                if char == " ":
                    revealed_text.append(" ")
                    live.update(revealed_text)
                    continue

                # Scramble effect
                for _ in range(scramble_chars):
                    scramble_display = revealed_text.copy()
                    scramble_display.append(
                        random.choice(scramble_set), style="rgb(100,100,100)"
                    )
                    live.update(scramble_display)
                    time.sleep(char_delay)

                # Reveal actual character
                revealed_text.append(char, style="rgb(0,250,0)")  # Bright green text
                live.update(revealed_text)
                time.sleep(char_delay)

        # Print final line to move cursor to next line
        console.print()


def scramble_panel(
    title: str, content_markup: str, border_style: str = "green"
) -> None:
    """
    Displays a Rich Panel by typing its content in, line by line.
    """
    console = Console()
    content_lines = content_markup.splitlines()
    revealed_lines = [""] * len(content_lines)
    panel_height = len(content_lines) + 2

    panel = Panel(
        "\n" * len(content_lines),
        title=title,
        border_style=border_style,
        height=panel_height,
    )

    with Live(panel, refresh_per_second=15, transient=False) as live:
        for i, line in enumerate(content_lines):
            revealed_line_content = ""
            for char_idx, char in enumerate(line):
                revealed_line_content += char
                revealed_lines[i] = revealed_line_content

                current_content = "\n".join(revealed_lines)
                live.update(
                    Panel(
                        current_content,
                        title=title,
                        border_style=border_style,
                        height=panel_height,
                    )
                )

                if char == " " or char_idx == len(line) - 1:
                    time.sleep(0.1)

        live.update(
            Panel(
                content_markup,
                title=title,
                border_style=border_style,
                height=panel_height,
            )
        )


def typewriter_prompt(text: str, delay: float = 0.05, show_cursor: bool = True) -> None:
    """Display text with typewriter effect and optional blinking cursor."""
    from rich.live import Live
    from rich.text import Text

    console = Console()

    if not show_cursor:
        # Simple version without cursor for compatibility
        for char in text:
            styled_char = Text(char, style="rgb(0,255,0)")
            console.print(styled_char, end="")
            time.sleep(delay)
        console.print()
        return

    # Enhanced version with blinking cursor
    current_text = Text("", style="rgb(0,255,0)")
    cursor = Text("_", style="rgb(0,255,0)")

    with Live(current_text + cursor, console=console, refresh_per_second=10) as live:
        for char in text:
            # Add character to text
            current_text.append(char)

            # Show text with cursor briefly
            live.update(current_text + cursor)
            time.sleep(delay * 0.7)  # Slightly faster for typing

            # Brief moment without cursor (typing effect)
            live.update(current_text)
            time.sleep(delay * 0.3)

        # Final blink sequence
        for _ in range(2):  # Reduced blinks to prevent lockup
            live.update(current_text + cursor)
            time.sleep(0.3)
            live.update(current_text)
            time.sleep(0.3)

    # Final newline
    console.print()


# Add this entire function to the end of ui/animations.py


def display_monks_illumination() -> None:
    """
    Orthodox monk's awakening to divine illumination - replaces 'WAKE UP...'
    The monk awakens from contemplative darkness to Christ's light
    """
    from rich.align import Align
    from rich.live import Live
    from rich.text import Text

    console = Console()
    console.clear()

    # Phase 1: The Vigil - Single point of light like a vigil candle
    vigil_light = Text("✦", style="#ffaa44")  # Warm candlelight color

    with Live(Align.center(vigil_light), console=console, refresh_per_second=8) as live:
        # Gentle flickering like a candle in prayer
        flicker_delays = [0.8, 0.6, 0.7, 0.9, 0.5, 0.8, 0.6]

        for delay in flicker_delays:
            # Bright phase
            vigil_light.stylize("#ffaa44")
            live.update(Align.center(vigil_light))
            time.sleep(delay)

            # Dim phase
            vigil_light.stylize("#664422")
            live.update(Align.center(vigil_light))
            time.sleep(delay * 0.3)

    time.sleep(0.8)

    # Phase 2: The Word - Greek text "rewritten" in English on same lines
    console.clear()

    # Greek and English pairs that will overlay each other
    proclamation_pairs = [
        ("Χριστὸς φῶς...", "Christ is the Light..."),
        ("τὸ φῶς τοῦ κόσμου", "the Light of the world..."),
        ("φωτίζει πάντα ἄνθρωπον", "illumines every person..."),
    ]

    try:
        center_row = console.size.height // 2 - len(proclamation_pairs) // 2
        terminal_width = console.size.width
    except (AttributeError, OSError):
        center_row = 8
        terminal_width = 80

    for i, (greek_text, english_text) in enumerate(proclamation_pairs):
        current_row = center_row + i

        # First, type the Greek text with precise positioning
        greek_padding = " " * max(0, (terminal_width - len(greek_text)) // 2)
        print(f"\x1b[{current_row};1H", end="")  # Position cursor at start of line

        # Custom typewriter that doesn't interfere with positioning
        full_greek_line = greek_padding + greek_text
        for char in full_greek_line:
            print(f"\x1b[38;5;220m{char}\x1b[0m", end="", flush=True)
            time.sleep(0.08)
        time.sleep(1.0)

        # Then "rewrite" with English on the exact same line
        english_padding = " " * max(0, (terminal_width - len(english_text)) // 2)
        print(f"\x1b[{current_row};1H", end="")  # Return to same line
        print(" " * terminal_width, end="")  # Clear the line
        print(f"\x1b[{current_row};1H", end="")  # Position again

        # Type English replacement
        full_english_line = english_padding + english_text
        for char in full_english_line:
            print(f"\x1b[38;5;82m{char}\x1b[0m", end="", flush=True)
            time.sleep(0.06)
        time.sleep(0.8)

    time.sleep(1.2)

    # Phase 3: Illumination - Cross symbol grows
    console.clear()

    # Progressive cross illumination
    cross_stages = ["✦", "✦✧✦", "✧✦☦✦✧", "✦✧☦✧✦", "☦"]

    cross_text = Text("", style="#44ff44")

    with Live(Align.center(cross_text), console=console, refresh_per_second=6) as live:
        for stage in cross_stages:
            cross_text.plain = stage
            live.update(Align.center(cross_text))
            time.sleep(0.6)

        # Hold the final cross
        time.sleep(1.0)

        # Gentle fade to sanctified green
        for intensity in range(255, 180, -8):
            fade_style = f"rgb(0,{intensity},0)"
            cross_text.stylize(fade_style)
            live.update(Align.center(cross_text))
            time.sleep(0.04)

    time.sleep(0.6)
    console.clear()


def display_wake_up_message() -> None:
    """Legacy compatibility - now calls the Orthodox monk illumination"""
    display_monks_illumination()


def wait_for_enter() -> None:
    """
    Display centered 'Press Enter' with progressive blinking 'Enter-->' cursor.
    """
    console = Console()
    console.clear()

    # Get terminal dimensions for centering
    size = console.size
    center_row = size.height // 2

    # Display centered "Press Enter" text
    for _ in range(center_row - 1):
        console.print()

    press_enter_text = "Press Enter"
    spaces_before = " " * max(0, (size.width - len(press_enter_text)) // 2)
    console.print(f"{spaces_before}[green]{press_enter_text}[/green]")
    console.print()  # Empty line between texts

    # Progressive blinking pattern for "Enter-->" - using Live context manager for proper updating
    from rich.align import Align
    from rich.live import Live
    from rich.text import Text

    blink_chars = ["E", "n", "t", "e", "r", "-", "-", ">"]

    # Create initial display
    arrow_text = Text("", style="bright_green")
    aligned_text = Align.center(arrow_text)

    with Live(aligned_text, refresh_per_second=10) as live:
        # Show animation cycles
        for cycle in range(3):  # 3 complete cycles
            for i in range(len(blink_chars) + 2):  # +2 for full display and pause
                if i < len(blink_chars):
                    visible_text = "".join(blink_chars[: i + 1])
                else:
                    visible_text = "Enter-->"

                arrow_text.plain = visible_text
                live.update(Align.center(arrow_text))
                time.sleep(0.3)

        # Final state - show complete text
        arrow_text.plain = "Enter-->"
        live.update(Align.center(arrow_text))

    # Wait for input without changing display
    input()
    console.clear()


def display_protocol_message() -> None:
    """
    Screen 3: The Monk's Consecration - Orthodox blessing of the digital workspace
    """
    console = Console()
    console.clear()

    now = datetime.datetime.now()
    datetime_str = now.strftime("%Y.%m.%d::%H:%M:%S")

    # Monk's illumination sequence
    display_monks_illumination()
    time.sleep(0.8)

    # Sanctified protocol acknowledgment
    protocol_message = f"PROTOCOL.MONK initialized {datetime_str}"
    scramble_text_in(protocol_message, scramble_chars=2, char_delay=0.025)
    time.sleep(1.0)

    # Orthodox consecration of digital space
    consecrations = [
        "Through the Cross, joy came into all the world...",
        "Christ sanctifies this digital realm...",
        "The machine serves the Logos...",
    ]

    for consecration in consecrations:
        typewriter_prompt(consecration, delay=0.06, show_cursor=True)
        time.sleep(0.8)

    time.sleep(0.5)

    # Final prayer - traditional Orthodox blessing
    typewriter_prompt(
        "Through the prayers of our holy Fathers, O Lord Jesus Christ our God, bless this work and save us. Amen.",
        delay=0.04,
        show_cursor=True,
    )
    time.sleep(1.8)


def display_welcome_panel() -> None:
    """
    Screen 4: The Monk's Consecrated Workspace - Orthodox Christian manifesto
    """
    console = Console()
    console.clear()

    # Sacred light cursor - like a vigil lamp
    cursor_text = Text("✦", style="#ffaa44")
    empty_text = Text("")
    with Live(cursor_text, console=console, refresh_per_second=10) as live:
        for delay in [0.5, 0.4, 0.35, 0.3]:
            live.update(cursor_text)
            time.sleep(delay)
            live.update(empty_text)
            time.sleep(delay * 0.4)
    time.sleep(0.5)

    # The Monk's sacred mission
    welcome_lines = [
        "[bold #44ff44]✠ PROTOCOL.MONK // SANCTIFIED WORKSPACE ✠[/]",
        '[#ffaa44]"Through code I serve the Logos. Through prayer I debug creation."[/]',
        "",
        "[bold #44ff44]COMMANDS OF CONTEMPLATIVE PRACTICE:[/]",
        "/help               - Receive guidance in the digital monastery",
        "/model <name>       - Choose your spiritual guide for the work",
        "/status             - Examine the state of your digital asceticism",
        "/clear              - Purify the workspace of all distractions",
        "/system <prompt>    - Set the spiritual foundation of your work",
        "/quit               - Depart with blessing when the work is complete",
        "",
        "[bold #44ff44]TOOLS OF SACRED LABOR:[/]",
        "Tools are granted as needed for each task",
        "The agent discerns when files must be read, created, or sanctified",
        "Scripts execute in service of the greater work",
        "All operations proceed under divine providence",
        "",
        "[bold #ffaa44]UNIFIED EXPERIENCE:[/]",
        "Simply speak your need - no modes, no /chat commands",
        "Ask about files, request changes, seek understanding",
        "The monk serves through conversation and tools alike",
        "",
        "[#44ff44]✠ The workspace is blessed. Speak your intention, faithful servant. ✠[/]",
    ]

    for line in welcome_lines:
        if line.startswith("["):
            console.print(line, highlight=False)
        else:
            typewriter_prompt(line, delay=0.025, show_cursor=False)
        time.sleep(0.04 if any(x in line for x in ["-", "✠", "/"]) else 0.08)

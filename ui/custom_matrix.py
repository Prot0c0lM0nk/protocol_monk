import math
import os
import random
import time
import sys
import atexit
from dataclasses import dataclass
from typing import Optional


# Configuration dataclass for magic numbers
@dataclass
class AnimationConfig:
    """Configuration constants for matrix animations"""

    # Timing constants
    BASE_REVEAL_TIME: float = 3.5
    CHAR_REVEAL_DELAY: float = 0.15
    CHAR_REVEAL_JITTER: float = 0.05
    FADE_START_TIME: float = 6.0
    FADE_DURATION: float = 4.0
    PROTOCOL_TEXT_START: float = 3.0
    PROTOCOL_REVEAL_START: float = 3.5
    PROTOCOL_REVEAL_DURATION: float = 1.5
    SANCTIFIED_TRANSITION_START: float = 2.0
    SANCTIFIED_TRANSITION_DURATION: float = 3.0

    # Glitch effect probabilities
    GLITCH_DURING_REVEAL: float = 0.3
    GLITCH_BEFORE_REVEAL: float = 0.1
    SACRED_CHAR_GLITCH_PROB: float = 0.2

    # Phase progression thresholds
    PRAYER_PHASE_THRESHOLD: float = 0.7
    ILLUMINATION_PHASE_THRESHOLD: float = 0.3

    # Blend weights
    CHAOS_WEIGHT_MULTIPLIER: int = 4
    ILLUMINATION_WEIGHT_MULTIPLIER: int = 12


CONFIG = AnimationConfig()


# Terminal control utility class
class Term:
    """Utility class for ANSI terminal sequences"""

    BLANK = " "
    CLEAR = "\x1b[H"
    RESET = "\x1b[0m"
    HIDE_CURSOR = "\x1b[?25l"
    SHOW_CURSOR = "\x1b[?25h"

    @staticmethod
    def move_to(row: int, col: int) -> str:
        """Move cursor to specific position"""
        return f"\x1b[{row};{col}H"

    @staticmethod
    def color_rgb(r: int, g: int, b: int) -> str:
        """Create RGB color code"""
        return f"\x1b[38;2;{r};{g};{b}m"

    @staticmethod
    def color_256(code: int) -> str:
        """Create 256-color code"""
        return f"\x1b[38;5;{code}m"


# Legacy constants for backwards compatibility
BLANK_CHAR = Term.BLANK
CLEAR_CHAR = Term.CLEAR
RESET = Term.RESET
HIDE_CURSOR = Term.HIDE_CURSOR
SHOW_CURSOR = Term.SHOW_CURSOR


# Emergency cursor restoration on exit
def _restore_cursor():
    print(Term.SHOW_CURSOR, end="", flush=True)


atexit.register(_restore_cursor)

# Sacred glyph sets for Orthodox Christian thematic progression
CHAOS_CHARS = "ｱｲｳｵｶｷｸｹｺｻｼｽｾｿﾀﾁﾂﾃﾄﾅﾆﾇﾈﾉﾊﾋﾌﾍﾎﾏﾐﾑﾒﾓﾔﾕﾖﾗﾘﾙﾚﾛﾜﾝ"

# Enhanced liturgical characters for monk's illumination
PRAYER_CHARS = "ΚύριεἐλέησονἉγίαΣοφίαΦῶςΧριστοῦΔόξαΘεῷ☦♱†✠ΙΧΘΥΣΑΩΟΝΝικᾶἸησοῦςΧριστός"

# Contemplative characters - balanced between chaos and prayer
ILLUMINATION_CHARS = "ΑΒΓΔΕΖΗΘΙΚΛΜΝΞΟΠΡΣΤΥΦΧΨΩαβγδεζηθικλμνξοπρστυφχψω☦♱†✠ΦῶςΛόγος"

# Traditional Church Slavonic and additional Orthodox symbols
SACRED_CHARS = "☦♱†✠⚰︎⛪︎🕯️✦✧✩★☩⊕⊗☨☪︎ΙΧΘΥΣΝικᾶΦῶςΛόγος"

DEFAULT_CHARS = ILLUMINATION_CHARS

# Drop state of each cell
STATE_NONE = 0
STATE_FRONT = 1
STATE_TAIL = 2

# Drop lengths
MIN_LEN = 5
MAX_LEN = 12

# Drop colours
BODY_CLRS = [
    "\x1b[38;5;48m",
    "\x1b[38;5;41m",
    "\x1b[38;5;35m",
    "\x1b[38;5;238m",
]
FRONT_CLR = "\x1b[38;5;231m"
TOTAL_CLRS = len(BODY_CLRS)


class Matrix(list):
    def __init__(self, wait: int, glitch_freq: int, drop_freq: int, char_set=None):
        self.rows = 0
        self.cols = 0
        # Validate char_set is not None and not empty
        if char_set is None or char_set == "":
            self.char_set = CHAOS_CHARS
        else:
            self.char_set = char_set

        self.wait = 0.06 / (wait / 100)
        self.glitch_freq = 0.01 / (glitch_freq / 100)
        self.drop_freq = 0.1 * (drop_freq / 100)

    def __str__(self):
        text = ""
        # Display all rows - don't skip MAX_LEN anymore since we fixed get_prompt_size
        for row in self:
            for cell in row:
                c, s, l = cell
                if s == STATE_NONE:
                    text += BLANK_CHAR
                elif s == STATE_FRONT:
                    text += f"{FRONT_CLR}{c}{RESET}"
                else:
                    text += f"{BODY_CLRS[l]}{c}{RESET}"
        return text

    def get_prompt_size(self):
        try:
            size = os.get_terminal_size()
            # Fix: Don't add MAX_LEN to avoid over-printing on small terminals
            # Just use actual terminal size
            return size.lines, size.columns
        except (OSError, AttributeError):
            return 25, 80

    # ✅ FIXED: Instance method - no @staticmethod, no confusion
    def get_random_char(self):
        return random.choice(self.char_set)

    def update_cell(
        self,
        r: int,
        c: int,
        *,
        char: Optional[str] = None,
        state: Optional[int] = None,
        length: Optional[int] = None,
    ) -> None:
        if char is not None:
            self[r][c][0] = char
        if state is not None:
            self[r][c][1] = state
        if length is not None:
            self[r][c][2] = length

    def fill(self) -> None:
        self[:] = [
            [[self.get_random_char(), STATE_NONE, 0] for _ in range(self.cols)]
            for _ in range(self.rows)
        ]

    def apply_glitch(self) -> None:
        total = self.cols * self.rows * self.glitch_freq
        for _ in range(int(total)):
            c = random.randint(0, self.cols - 1)
            r = random.randint(0, self.rows - 1)
            self.update_cell(r, c, char=self.get_random_char())

    def drop_col(self, col: int) -> bool:
        dropped = self[self.rows - 1][col][1] == STATE_FRONT
        for r in reversed(range(self.rows)):
            _, state, length = self[r][col]
            if state == STATE_NONE:
                continue
            if r != self.rows - 1:
                self.update_cell(r + 1, col, state=state, length=length)
            self.update_cell(r, col, state=STATE_NONE, length=0)
        return dropped

    def add_drop(self, row: int, col: int, length: int) -> None:
        for i in reversed(range(length)):
            r = row + (length - i)
            if i == 0:
                self.update_cell(r, col, state=STATE_FRONT, length=length)
            else:
                l = math.ceil((TOTAL_CLRS - 1) * i / length)
                self.update_cell(r, col, state=STATE_TAIL, length=l)

    def screen_check(self) -> None:
        p = self.get_prompt_size()
        if (self.rows, self.cols) != p:
            self.rows, self.cols = p
            self.fill()

    def update(self) -> None:
        dropped = sum(self.drop_col(c) for c in range(self.cols))
        total = self.cols * self.rows * self.drop_freq
        # Prevent negative missing when dropped > total
        missing = (
            max(0, math.ceil((total - dropped) / self.cols)) if self.cols > 0 else 0
        )
        for _ in range(missing):
            col = random.randint(0, self.cols - 1)
            length = random.randint(MIN_LEN, MAX_LEN)
            self.add_drop(0, col, length)

    def start(
        self, duration: Optional[float] = None, show_protocol_monk: bool = False
    ) -> None:
        start_time = time.time()
        initial_drop_freq = self.drop_freq
        print(HIDE_CURSOR, end="", flush=True)

        protocol_monk_text = "PROTOCOL MONK"
        char_reveal_times = []

        if show_protocol_monk:
            protocol_monk_len = len(protocol_monk_text)
            for i in range(protocol_monk_len):
                reveal_time = (
                    CONFIG.BASE_REVEAL_TIME
                    + (i * CONFIG.CHAR_REVEAL_DELAY)
                    + random.uniform(
                        -CONFIG.CHAR_REVEAL_JITTER, CONFIG.CHAR_REVEAL_JITTER
                    )
                )
                char_reveal_times.append(reveal_time)

        try:
            while True:
                current_time = time.time() - start_time
                print(CLEAR_CHAR, end="")

                self.screen_check()
                print(self, end="", flush=True)

                if (
                    show_protocol_monk
                    and duration
                    and current_time > CONFIG.PROTOCOL_TEXT_START
                ):
                    try:
                        size = os.get_terminal_size()
                        center_row = size.lines // 2
                        center_col = max(
                            0, size.columns // 2 - len(protocol_monk_text) // 2
                        )

                        revealed_text = ""
                        for i, char in enumerate(protocol_monk_text):
                            if current_time >= char_reveal_times[i]:
                                if (
                                    current_time - char_reveal_times[i]
                                    < CONFIG.GLITCH_DURING_REVEAL
                                ):
                                    if random.random() < CONFIG.GLITCH_DURING_REVEAL:
                                        glitch_char = self.get_random_char()
                                        revealed_text += glitch_char
                                    else:
                                        revealed_text += char
                                else:
                                    revealed_text += char
                            else:
                                if (
                                    current_time > CONFIG.PROTOCOL_TEXT_START
                                    and random.random() < CONFIG.GLITCH_BEFORE_REVEAL
                                ):
                                    revealed_text += self.get_random_char()
                                else:
                                    revealed_text += " "

                        print(f"\x1b[{center_row};{center_col}H", end="")
                        print(f"{FRONT_CLR}{revealed_text}{RESET}", end="", flush=True)
                    except (OSError, AttributeError):
                        pass

                # Fix: Allow fade even when duration is None or 0
                if show_protocol_monk and current_time > CONFIG.FADE_START_TIME:
                    fade_progress = min(
                        1.0,
                        (current_time - CONFIG.FADE_START_TIME) / CONFIG.FADE_DURATION,
                    )
                    self.drop_freq = initial_drop_freq * (1 - fade_progress)
                    self.glitch_freq *= 1 - fade_progress * 0.8

                self.apply_glitch()
                self.update()
                time.sleep(self.wait)

                if duration is not None and current_time >= duration:
                    break
        except KeyboardInterrupt:
            # Allow graceful shutdown on Ctrl+C
            pass
        finally:
            print(SHOW_CURSOR + RESET, end="", flush=True)
            self.drop_freq = initial_drop_freq


def blink_protocol_monk_text(
    text: str = "PROTOCOL MONK", blink_duration: float = 3
) -> None:
    start_time = time.time()
    try:
        size = os.get_terminal_size()
        center_row = size.lines // 2
        center_col = max(0, size.columns // 2 - len(text) // 2)
    except (OSError, AttributeError):
        center_row = 12
        center_col = max(0, 40 - len(text) // 2)

    print(HIDE_CURSOR, end="", flush=True)
    print(CLEAR_CHAR, end="")
    print("\n" * (center_row - 1), end="")

    try:
        while time.time() - start_time < blink_duration:
            progress = (time.time() - start_time) / blink_duration
            blink_speed = 0.8 * (1 - progress) + 0.05
            print(
                f"\x1b[{center_row};{center_col}H{FRONT_CLR}{text}{RESET}",
                end="",
                flush=True,
            )
            time.sleep(blink_speed / 2)
            print(
                f"\x1b[{center_row};{center_col}H{' ' * len(text)}", end="", flush=True
            )
            time.sleep(blink_speed / 2)
        print(CLEAR_CHAR, end="")
    except KeyboardInterrupt:
        pass
    finally:
        print(SHOW_CURSOR, end="", flush=True)


def run_sanctified_transition(duration: float = 6.0) -> None:
    """Enhanced Orthodox transition: Chaos → Illumination → Prayer"""
    matrix = Matrix(
        wait=150, glitch_freq=199, drop_freq=150, char_set=CHAOS_CHARS
    )  # Start with chaos
    start_time = time.time()
    initial_wait = matrix.wait
    initial_glitch = matrix.glitch_freq
    print(HIDE_CURSOR, end="", flush=True)

    try:
        while time.time() - start_time < duration:
            current_time = time.time() - start_time

            # Orthodox progression: Chaos → Illumination → Prayer
            if current_time > CONFIG.SANCTIFIED_TRANSITION_START:
                progress = min(
                    1.0,
                    (current_time - CONFIG.SANCTIFIED_TRANSITION_START)
                    / CONFIG.SANCTIFIED_TRANSITION_DURATION,
                )
                matrix.wait = initial_wait / (0.5 + 0.5 * progress)
                matrix.glitch_freq = initial_glitch * (
                    1.2 - progress * 0.8
                )  # Reduce chaos over time

                # Store old char set to detect changes
                old_char_set = matrix.char_set

                if progress > CONFIG.PRAYER_PHASE_THRESHOLD:
                    # Final phase: Pure prayer and sacred symbols
                    matrix.char_set = PRAYER_CHARS
                elif progress > CONFIG.ILLUMINATION_PHASE_THRESHOLD:
                    # Middle phase: Illumination - balanced contemplation
                    matrix.char_set = ILLUMINATION_CHARS
                elif progress > 0.0:
                    # Transition phase: Blend chaos with illumination
                    chaos_weight = int((1 - progress) * CONFIG.CHAOS_WEIGHT_MULTIPLIER)
                    illumination_weight = int(
                        progress * CONFIG.ILLUMINATION_WEIGHT_MULTIPLIER
                    )
                    blended_set = (
                        CHAOS_CHARS * chaos_weight
                        + ILLUMINATION_CHARS * illumination_weight
                    )
                    matrix.char_set = blended_set if blended_set else ILLUMINATION_CHARS

                # Force character update when char set changes
                if old_char_set != matrix.char_set:
                    # Update existing characters to use new set
                    for row in range(matrix.rows):
                        for col in range(matrix.cols):
                            if matrix[row][col][1] != STATE_NONE:  # If cell is active
                                matrix.update_cell(
                                    row, col, char=matrix.get_random_char()
                                )

            matrix.screen_check()
            print(CLEAR_CHAR, end="")
            print(matrix, end="", flush=True)

            # Display consecrated protocol text
            if current_time > CONFIG.PROTOCOL_REVEAL_START:
                protocol_monk_text = "✠ PROTOCOL.MONK ✠"
                try:
                    size = os.get_terminal_size()
                    center_row = size.lines // 2
                    center_col = max(
                        0, size.columns // 2 - len(protocol_monk_text) // 2
                    )
                    reveal_progress = min(
                        1.0,
                        (current_time - CONFIG.PROTOCOL_REVEAL_START)
                        / CONFIG.PROTOCOL_REVEAL_DURATION,
                    )
                    reveal_point = int(reveal_progress * len(protocol_monk_text))
                    displayed_text = protocol_monk_text[:reveal_point]

                    # Add subtle glitch effect during reveal using sacred chars
                    if reveal_progress < 1.0:
                        final_chars = ""
                        for i, char in enumerate(displayed_text):
                            if (
                                i >= len(displayed_text) - 2
                                and random.random() < CONFIG.SACRED_CHAR_GLITCH_PROB
                            ):
                                # Gentle sacred character glitch
                                final_chars += random.choice("☦♱†✠")
                            else:
                                final_chars += char
                        displayed_text = final_chars

                    print(
                        f"\x1b[{center_row};{center_col}H{FRONT_CLR}{displayed_text}{RESET}",
                        end="",
                        flush=True,
                    )
                except (OSError, AttributeError):
                    pass

            matrix.apply_glitch()
            matrix.update()
            time.sleep(matrix.wait)

    except KeyboardInterrupt:
        pass
    finally:
        print(SHOW_CURSOR + RESET, end="", flush=True)
        print(CLEAR_CHAR, end="")


def run_enhanced_matrix_intro() -> None:
    run_sanctified_transition(duration=6.0)
    print(CLEAR_CHAR, end="")
    time.sleep(0.3)
    blink_protocol_monk_text("PROTOCOL.MONK//v0.1", blink_duration=3)


def run_animation(
    duration: float = 10, speed: int = 100, glitches: int = 100, frequency: int = 100
) -> None:
    for arg in (speed, glitches, frequency):
        if not 0 <= arg <= 1000:
            raise ValueError(
                "Speed, glitches, and frequency must be between 1 and 1000"
            )
    matrix = Matrix(speed, glitches, frequency)  # ✅ FIXED: lowercase 'matrix'
    matrix.start(duration=duration)

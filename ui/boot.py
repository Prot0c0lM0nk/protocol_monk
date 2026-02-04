import time
import random
from rich.live import Live
from rich.align import Align
from rich.panel import Panel
from rich.text import Text
from rich.console import Console
from rich import box

# ---------------------------------------------------------------------------
# Fixed‑size panel handling
# ---------------------------------------------------------------------------
# Rich recalculates a panel’s width from the longest line of the renderable.
# During progressive‑reveal many lines are just spaces, causing the panel to
# shrink and then expand.  We compute the maximum line length across **all**
# ASCII‑art assets, add the horizontal padding and border width, and force every
# Panel to use this constant width.
_PADDINGS = (5, 20)  # (vertical, horizontal) padding for all panels
_GLOBAL_MAX_CONTENT_WIDTH = max(
    len(line)
    for art in (
        r"""
 _                                                                                              
| |____ _______ ________ __  __   _______ ________  ______ __________   __________ ______ ____  
|____  |.  __  |.  ___  |  \/  | |____  .|.  ___  ||____  |.  ___  \ \ / /.  ___  |____  |  _ \ 
    / / | |  | || |   | | |\/| |      | | | |   | |     | || |   | |  V / | |   | |    | | |_) |
   / /  | | _| || |___| | |  | |      | | | |___| |_____| || |___| | |\ \ | |___| |    | |  __/ 
  /_/   |_||___||_______|_|  |_|      | | |_______/________/_______|_| \_\|_______|    |_|_|     
                                      |_|                                                       
""",
        r"""
 _______                            __       __   __                 
(   _   )                           \ \     |  \ /  |                
 | | | | ___   ___ ___ _____   _____ \ \    |   v   | ___  _  ___  __
 | | | |/ _ \ / _ (   ) _ \ \ / / _ \ > \   | |\_/| |/ _ \| |/ / |/ /
 | | | | |_) | (_) ) ( (_) ) v ( (_) ) ^ \  | |   | ( (_) ) / /|   < 
 |_| |_|  __/ \___/ \_)___/ > < \___/_/ \_\ |_|   |_|\___/|__/ |_|\_\
       | |                 / ^ \                                     
       |_|                /_/ \_\                                    
""",
        r"""
##### ####   ###  #####  ###  #   #  ###  #####     #   #  ###  #   # #   # 
#   # #   # #   #   #   #   # #   # #   #  #  #     ## ## #   # #   # #  #  
#   # ####  #   #   #   #   #  #### #   #  #  #     # # # #   # ##### ###   
#   # #     #   #   #   #   #     # #   #  #  #     #   # #   # #   # #  #  
#   # #      ###    #    ###      #  ###  #   #     #   #  ###  #   # #   # 
""",
        r"""
▗▄▄▖  ▄▄▄ ▄▄▄     ■   ▄▄▄  ▗▞▀▘ ▄▄▄  █     ▗▖  ▗▖ ▄▄▄  ▄▄▄▄  █  ▄ 
▐▌ ▐▌█   █   █ ▗▄▟▙▄▖█   █ ▝▚▄▖█   █ █     ▐▛▚▞▜▌█   █ █   █ █▄▀  
▐▛▀▘ █   ▀▄▄▄▀   ▐▌  ▀▄▄▄▀     ▀▄▄▄▀ █     ▐▌  ▐▌▀▄▄▄▀ █   █ █ ▀▄ 
▐▌               ▐▌                  █     ▐▌  ▐▌            █  █ 
                 ▐▌                                               
""",
    )
    for line in art.strip("\n").split("\n")
)

# border adds 2 characters (one on each side)
_GLOBAL_PANEL_WIDTH = _GLOBAL_MAX_CONTENT_WIDTH + (_PADDINGS[1] * 2) + 2

# --- ASCII ART ASSETS (Raw Strings) ---
# I have manually corrected the line wrapping and alignment for each style.

# 1. HEBREW (Style: "Cybermedium")
# Represents the ancient, foundational protocol.
ART_HEBREW = r"""
 _                                                                                              
| |____ _______ ________ __  __   _______ ________  ______ __________   __________ ______ ____  
|____  |.  __  |.  ___  |  \/  | |____  .|.  ___  ||____  |.  ___  \ \ / /.  ___  |____  |  _ \ 
    / / | |  | || |   | | |\/| |      | | | |   | |     | || |   | |  V / | |   | |    | | |_) |
   / /  | | _| || |___| | |  | |      | | | |___| |_____| || |___| | |\ \ | |___| |    | |  __/ 
  /_/   |_||___||_______|_|  |_|      | | |_______/________/_______|_| \_\|_______|    |_|_|     
                                      |_|                                                       
"""

# 2. GREEK (Style: "Speed")
# Represents the transmission of knowledge.
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

# 3. RUSSIAN/CYRILLIC (Style: "Block")
# Represents the Northern/Monastic preservation.
ART_RUSSIAN = r"""
##### ####   ###  #####  ###  #   #  ###  #####     #   #  ###  #   # #   # 
#   # #   # #   #   #   #   # #   # #   #  #  #     ## ## #   # #   # #  #  
#   # ####  #   #   #   #   #  #### #   #  #  #     # # # #   # ##### ###   
#   # #     #   #   #   #   #     # #   #  #  #     #   # #   # #   # #  #  
#   # #      ###    #    ###      #  ###  #   #     #   #  ###  #   # #   # 
"""

# 4. ENGLISH (Style: "Unicode Blocks")
# The final resolved protocol.
ART_FINAL = r"""
▗▄▄▖  ▄▄▄ ▄▄▄     ■   ▄▄▄  ▗▞▀▘ ▄▄▄  █     ▗▖  ▗▖ ▄▄▄  ▄▄▄▄  █  ▄ 
▐▌ ▐▌█   █   █ ▗▄▟▙▄▖█   █ ▝▚▄▖█   █ █     ▐▛▚▞▜▌█   █ █   █ █▄▀  
▐▛▀▘ █   ▀▄▄▄▀   ▐▌  ▀▄▄▄▀     ▀▄▄▄▀ █     ▐▌  ▐▌▀▄▄▄▀ █   █ █ ▀▄ 
▐▌               ▐▌                  █     ▐▌  ▐▌            █  █ 
                 ▐▌                                               
"""

# Glitch characters for corruption effects
GLITCH_CHARS = "▓▒░█▄▀■□▪▫▲▼◄►◆◇○●◎◐◑★☆☂☀☁☽☾♠♣♥♦♪♫€¥£¢∞§¶†‡"
SCANLINE_CHARS = "▔▁▄▀█▌▐░▒▓"

# Pre-computed art data for performance
_ART_LINES = {}
_ART_MAX_LENGTH = {}


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
    glitch = GLITCH_CHARS
    rand = random.random
    choice = random.choice
    return "".join(
        choice(glitch) if char.strip() and rand() < intensity else char for char in text
    )


def apply_scanlines(text: str, intensity: float = 0.2) -> str:
    """Add CRT scanline effect to text."""
    if intensity <= 0:
        return text
    lines = text.split("\n")
    rand = random.random
    threshold = intensity
    return "\n".join(
        line.replace(" ", "░") if i % 2 == 0 and rand() < threshold else line
        for i, line in enumerate(lines)
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


def get_signal_indicator(strength: float, max_bars: int = 10) -> str:
    """Generate a signal strength indicator."""
    filled = int(strength * max_bars)
    bars = "█" * filled + "░" * (max_bars - filled)
    percentage = int(strength * 100)
    color = "green" if strength > 0.7 else "yellow" if strength > 0.4 else "red"
    return f"[{color}]SIGNAL: [{bars}] {percentage}%[/{color}]"


def get_panel(
    art,
    style="monk.border",
    subtitle="",
    signal_strength=1.0,
    corruption=0.0,
    scanlines=False,
    flicker=False,
    show_signal=True,
):
    """Wrap art in a consistent Rich Panel with optional visual effects."""
    # Get cached art lines and the *original* max line length.
    # The panel width is forced to the global constant `_GLOBAL_PANEL_WIDTH`
    # (see comment block at top). This stops the panel from shrinking
    # when a frame contains only spaces.
    lines = _get_art_lines(art)
    max_length = _get_max_length(art)

    # Build display art from cached lines
    display_art = "\n".join(lines)

    # Apply effects
    if corruption > 0:
        display_art = corrupt_text(display_art, corruption)

    if scanlines:
        display_art = apply_scanlines(display_art)

    # Flicker – randomly dim some blocks
    if flicker and random.random() < 0.3:
        dim_level = random.choice(["▓", "▒", "░"])
        display_art = display_art.replace("█", dim_level)

    # Normalize line lengths using the cached max for this piece,
    # then center the whole art block inside the global width.
    left_pad = max((_GLOBAL_MAX_CONTENT_WIDTH - max_length) // 2, 0)
    right_pad = max(_GLOBAL_MAX_CONTENT_WIDTH - max_length - left_pad, 0)
    normalized_lines = [
        (" " * left_pad) + line.ljust(max_length) + (" " * right_pad)
        for line in display_art.split("\n")
    ]
    normalized_art = "\n".join(normalized_lines)

    # Build content with optional signal indicator
    if show_signal and signal_strength is not None:
        # Create the signal indicator using Rich Text objects for proper styling
        filled = int(signal_strength * 10)
        bars = "█" * filled + "░" * (10 - filled)
        percentage = int(signal_strength * 100)

        # Determine color based on signal strength
        color = (
            "green"
            if signal_strength > 0.7
            else "yellow" if signal_strength > 0.4 else "red"
        )

        # Create a Text object for the signal indicator with proper styling
        signal_text = Text()
        signal_text.append("SIGNAL: ", style="bold")
        signal_text.append(bars, style=color)
        signal_text.append(f" {percentage}%", style=color)

        # Combine the art and signal indicator
        content = Text()
        content.append(normalized_art)
        content.append("\n\n")
        content.append(signal_text)
    else:
        content = Text(normalized_art, style=style)

    # NOTE: `width` forces the panel to stay the same size throughout the animation.
    return Panel(
        Align.center(content),
        box=box.DOUBLE,
        border_style=style,
        subtitle=f"[dim]{subtitle}[/]" if subtitle else None,
        expand=False,
        padding=_PADDINGS,
        width=_GLOBAL_PANEL_WIDTH,
    )


def run_boot_sequence(console: Console):
    """
    Enhanced boot sequence with progressive reveal, glitch effects, and signal decoding.
    """
    # The sequence: (Art, Base Style, Decoding Message)
    sequence = [
        (ART_HEBREW, "red", "DECODING ANCIENT PROTOCOLS..."),
        (ART_GREEK, "yellow", "TRANSMITTING BYZANTINE WISDOM..."),
        (ART_RUSSIAN, "cyan", "ESTABLISHING MONASTIC LINK..."),
        (ART_FINAL, "monk.border", "ORTHODOX PROTOCOL v1.0 INITIALIZED"),
    ]

    with Live(console=console, refresh_per_second=20, transient=True) as live:
        for idx, (art, style, message) in enumerate(sequence):
            is_final = idx == len(sequence) - 1
            panel_signal = (idx + 1) / len(sequence)

            # Phase 1: Signal acquisition (weak signal, high corruption)
            acquisition_frames = 8 if not is_final else 4
            for frame in range(acquisition_frames):
                corruption = 0.6 - (frame / acquisition_frames) * 0.3
                panel = get_panel(
                    art,
                    style=style,
                    subtitle=f"[dim]{message}[/]",
                    signal_strength=panel_signal,
                    corruption=corruption,
                    scanlines=True,
                    flicker=True,
                )
                live.update(panel)
                time.sleep(0.08)

            # Phase 2: Progressive decode (character reveal)
            reveal_steps = 20 if not is_final else 12
            for step in range(reveal_steps + 1):
                progress = step / reveal_steps
                revealed_art = progressive_reveal(art, progress)

                corruption = 0.4 * (1 - progress)

                panel = get_panel(
                    revealed_art,
                    style=style,
                    subtitle=f"[dim]{message}[/]",
                    signal_strength=panel_signal,
                    corruption=corruption,
                    scanlines=progress < 0.8,
                    flicker=progress < 0.6,
                )
                live.update(panel)
                delay = 0.05 + (1 - progress) * 0.08
                time.sleep(delay)

            # Phase 3: Lock‑on (stable display with subtle effects)
            if not is_final:
                lock_frames = 6
                for frame in range(lock_frames):
                    glitch_chance = 0.2 * (1 - frame / lock_frames)
                    corruption = glitch_chance if random.random() < glitch_chance else 0

                    panel = get_panel(
                        art,
                        style=style,
                        subtitle=f"[dim]{message} — LOCKED[/]",
                        signal_strength=panel_signal,
                        corruption=corruption,
                        scanlines=False,
                        flicker=frame < 2,
                    )
                    live.update(panel)
                    time.sleep(0.1)

            # Phase 4: Transition glitch (except for final frame)
            if not is_final:
                transition_frames = 5
                for frame in range(transition_frames):
                    corruption = 0.5 + (frame / transition_frames) * 0.4
                    panel = get_panel(
                        art,
                        style=style,
                        subtitle="[dim]TRANSMISSION INTERRUPTED...[/]",
                        signal_strength=panel_signal,
                        corruption=corruption,
                        scanlines=True,
                        flicker=True,
                    )
                    live.update(panel)
                    time.sleep(0.06)

        # Final static display
        final_panel = get_panel(
            ART_FINAL,
            style="monk.border",
            subtitle="ORTHODOX PROTOCOL v1.0 — SYSTEM READY",
            signal_strength=1.0,
        )
        live.update(final_panel)
        time.sleep(0.5)

    # Print the final static banner to remain on screen
    console.print(final_panel)
    console.print()

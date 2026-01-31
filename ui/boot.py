import time
from rich.live import Live
from rich.align import Align
from rich.panel import Panel
from rich.text import Text
from rich.console import Console
from rich import box

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

def get_panel(art, style="monk.border", subtitle=""):
    """Helper to wrap art in a consistent panel."""
    # Normalize line lengths by padding each line to the maximum length
    lines = art.strip().split('\n')
    max_length = max(len(line) for line in lines)
    normalized_lines = [line.ljust(max_length) for line in lines]
    normalized_art = '\n'.join(normalized_lines)
    
    return Panel(
        Align.center(Text(normalized_art, style=style)),
        box=box.DOUBLE,
        border_style=style,
        subtitle=f"[dim]{subtitle}[/]",
        expand=False,
        padding=(1, 4)
    )

def run_boot_sequence(console: Console):
    """
    Cycles through languages before landing on the main app.
    """
    # The sequence: (Art, Duration, Color Style)
    sequence = [
        (ART_HEBREW, 1.0, "red"),          # Ancient/Warning
        (ART_GREEK, 1.0, "yellow"),        # Gold/Byzantine
        (ART_RUSSIAN, 1.0, "tech.cyan"),        # Cold/Northern
        (ART_FINAL, 1.0, "monk.border"),   # The Final State
    ]

    # Create a Live display that updates in place
    with Live(console=console, refresh_per_second=10, transient=True) as live:
        for art, duration, style in sequence:
            panel = get_panel(art, style=style)
            live.update(panel)
            time.sleep(duration)
    
    # Print the final static banner to remain on screen
    final_panel = get_panel(ART_FINAL, style="monk.border", subtitle="v1.0 Orthodox Protocol")
    console.print(final_panel)
    console.print()
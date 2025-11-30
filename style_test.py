import time
from rich import box
from rich.console import Console, Group
from rich.markdown import Markdown
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn
from rich.style import Style
from rich.table import Table
from rich.text import Text
from rich.theme import Theme

# --- 1. THEME DEFINITION (The "Palette") ---
# We define the colors here so we can change them in one place.
ORTHODOX_MATRIX_THEME = Theme(
    {
        # Base Colors
        "monk.text": "green1",  # The Matrix Green (Main Text)
        "monk.border": "medium_purple1",  # Green Borders
        "holy.gold": "bold #ffaa44",  # Orthodox Gold (Icons/User)
        "tech.cyan": "bold #00d7ff",  # Machine/Tool Color
        # Functional Styles
        "success": "bold #44ff44",  # The specific green you liked
        "dim": "dim #44ff44",  # Faded matrix text
        # Markdown Overrides (Forces the text to be Green, not default white)
        "markdown.paragraph": "green1",
        "markdown.list": "spring_green1",
        "markdown.item": "green1",
        "markdown.code": "green1 on #111111",  # Code blocks are cyan on black
    }
)

# Apply the theme to the console
console = Console(theme=ORTHODOX_MATRIX_THEME)

# --- 2. RENDERERS ---


def render_user_message(text):
    """User input: Minimalist, using the Holy Gold color for the prompt."""
    console.print()
    # The 'User' label is dim, the arrow is Gold
    console.print(f"  [dim white]You[/] [holy.gold]›[/] [white]{text}[/]")


def render_agent_thinking():
    """
    The 'Reasoning' Phase.
    User wanted this to look like the Success message.
    """
    console.print()
    # We use a custom spinner that looks technical but colored in Gold/Green
    with console.status(
        "[success]Contemplating the Logos...[/]",
        spinner="dots",
        spinner_style="holy.gold",
    ):
        time.sleep(2.5)  # Delay to admire the colors


def render_agent_message(markdown_text):
    """
    The Monk speaks.
    We use the custom theme to force the text to be Green.
    """
    md = Markdown(markdown_text)

    panel = Panel(
        md,
        title="[monk.border]✠ Monk[/]",  # The Cross symbol
        title_align="left",
        border_style="monk.border",
        box=box.ROUNDED,
        padding=(1, 2),
        width=100,
    )
    console.print()
    console.print(panel)


def render_tool_call_pretty(action, params):
    """
    Tool Execution Request.
    We use Cyan (Machine) for the border, but Green/Gold for content.
    """
    # 1. Create a simple table for parameters
    param_table = Table(box=None, show_header=False, padding=(0, 2))
    param_table.add_column("Key", style="holy.gold")  # Keys are Gold
    param_table.add_column("Value", style="tech.cyan")  # Values are Cyan

    # 2. Add rows
    for key, value in params.items():
        if isinstance(value, bool):
            val_str = "✅ Yes" if value else "❌ No"
        else:
            val_str = str(value)

        # Add bullet point
        param_table.add_row(f"• {key.replace('_', ' ').title()}", val_str)

    # 3. Stack the content
    content = Group(
        Text(f"I must invoke the machine: {action}", style="monk.text"),
        Text(""),
        param_table,
        Text(""),
        Text("Authorize this action? [Y/n]", style="holy.gold"),
    )

    panel = Panel(
        content,
        title="[tech.cyan]🛠 Sacred Action[/]",
        border_style="tech.cyan",
        box=box.ROUNDED,
        padding=(1, 2),
    )
    console.print()
    console.print(panel)


def render_status_bar_simulation():
    """
    The progress bar for tools.
    User wanted the 'Success' text to match the parsing message.
    """
    console.print()
    with Progress(
        SpinnerColumn("dots", style="holy.gold"),
        TextColumn("[monk.text]{task.description}"),  # Green text
        BarColumn(bar_width=40, style="monk.border", complete_style="monk.text"),
        TextColumn("[monk.text]{task.percentage:>3.0f}%"),
        console=console,
        transient=True,
    ) as progress:
        task1 = progress.add_task("Parsing file structure...", total=100)
        for i in range(20):
            time.sleep(0.05)
            progress.update(task1, advance=5)

    # FINAL SUCCESS MESSAGE (The one you liked)
    console.print("  [success]✓ Protocol structure parsed successfully.[/]")


# --- 3. THE DEMO SCENARIO ---

# Header
console.print(
    Panel(
        "[monk.border]PROTOCOL.MONK[/]\n[dim]v0.1 // Sanctified Workspace[/]",
        style="on black",
        border_style="monk.border",
        box=box.HEAVY,
    )
)

# 1. User asks
render_user_message("Analyze the protocol_core directory.")

# 2. Monk Thinks (Green/Gold)
render_agent_thinking()

# 3. Monk Speaks (Matrix Green Text)
render_agent_message(
    """
I have received your intention. I will examine the structure of the `protocol_core` for spiritual and technical alignment.

I am looking for:
* Configuration files
* Python modules
* Missing dependencies
"""
)

# 4. Tool Request (Cyan/Gold/Green mix)
render_tool_call_pretty(
    "scan_directory",
    {
        "path": "./protocol_core",
        "recursive": True,
        "depth_limit": 3,
        "ignore_hidden": True,
    },
)

# 5. User approves
time.sleep(1)
console.print("  [success]✓ Approved[/]")

# 6. Tool Runs
render_status_bar_simulation()

# 7. Final Result
render_agent_message(
    """
**Analysis Complete.**

I have found 3 issues that require sanctification. The code structure is sound, but the tests are incomplete.
"""
)

# 8. Prompt
console.print()
console.print("[monk.border]Monk[/] [holy.gold]>[/] ", end="")

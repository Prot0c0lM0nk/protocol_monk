#!/usr/bin/env python3
"""
Tools Renderer - Orthodox Matrix Theme
"""

import time
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich import box
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.console import Group

from ui.styles import console


def render_tool_call_pretty(action: str, params: dict):
    """
    The 'Asking Permission' Screen.
    """
    # 1. Create a simple table for parameters
    param_table = Table(box=None, show_header=False, padding=(0, 2))
    param_table.add_column("Key", style="holy.gold")
    param_table.add_column("Value", style="tech.cyan")

    # 2. Add rows
    for key, value in params.items():
        if isinstance(value, bool):
            val_str = "✅ Yes" if value else "❌ No"
        else:
            val_str = str(value)

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


def render_tool_result(tool_name, success, output):
    """
    The 'Results' Screen.
    (This was missing, causing the 2 vs 3 arguments error).
    """
    console.print()
    if success:
        console.print(f"  [success]✓ {tool_name}[/] [dim]execution successful[/]")
        # Only show output if it exists
        if output:
            # Truncate if massive, otherwise print
            display_out = output[:500] + "..." if len(output) > 500 else output
            console.print(f"    [dim]{display_out}[/]")
    else:
        console.print(f"  [error]✗ {tool_name} Failed[/]")
        if output:
            console.print(f"    [error]{output}[/]")
    console.print()


def render_status_bar_simulation():
    """
    The Loading Bar.
    Removed 'self' and 'result' arguments so you can call it easily.
    """
    console.print()
    with Progress(
        SpinnerColumn("dots", style="#ffaa44"),  # Orthodox gold color
        TextColumn("[monk.text]{task.description}"),
        BarColumn(bar_width=40, style="monk.border", complete_style="monk.text"),
        TextColumn("[monk.text]{task.percentage:>3.0f}%"),
        console=console,
        transient=True,
    ) as progress:
        task1 = progress.add_task("Parsing file structure...", total=100)
        # Simulation loop
        for i in range(20):
            time.sleep(0.05)
            progress.update(task1, advance=5)

    console.print("  [success]✓ Protocol structure parsed successfully.[/]")

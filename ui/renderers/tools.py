#!/usr/bin/env python3
"""
Tools Renderer - Orthodox Matrix Theme
"""

import time
from rich import box
from rich.console import Group
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from ui.styles import console


def render_tool_call_pretty(action: str, params: dict):
    """
    The 'Asking Permission' Screen.
    SECURITY: Full display of scripts/commands. No truncation.
    """
    items = []

    # 1. Header Text
    items.append(Text(f"I must invoke the machine: {action}", style="monk.text"))
    items.append(Text(""))  # Spacer

    # 2. Parameter Rendering
    # We iterate through params. Simple ones go in a table.
    # Complex/Code ones get their own Syntax block.

    simple_params = {}
    complex_params = {}

    for key, value in params.items():
        str_val = str(value)
        # Threshold: Multi-line or > 80 chars gets its own block
        if "\n" in str_val or len(str_val) > 80:
            complex_params[key] = str_val
        else:
            simple_params[key] = value

    # A. Render Simple Parameters (Table)
    if simple_params:
        param_table = Table(box=None, show_header=False, padding=(0, 2))
        param_table.add_column("Key", style="holy.gold")
        param_table.add_column("Value", style="tech.cyan")

        for key, value in simple_params.items():
            if isinstance(value, bool):
                val_str = "✅ Yes" if value else "❌ No"
            else:
                val_str = str(value)
            param_table.add_row(f"• {key.replace('_', ' ').title()}", val_str)

        items.append(param_table)
        items.append(Text(""))  # Spacer

    # B. Render Complex Parameters (Syntax/Blocks)
    for key, value in complex_params.items():
        items.append(Text(f"• {key.replace('_', ' ').title()}:", style="holy.gold"))

        # Detect language (basic heuristic)
        lexer = "python" if "py" in key or "script" in key else "bash"
        if action == "run_programming_task":
            lexer = "python"

        # Render full code block
        code_block = Syntax(
            value, lexer, theme="monokai", line_numbers=True, word_wrap=True
        )
        items.append(Panel(code_block, border_style="dim white"))
        items.append(Text(""))  # Spacer

    # 3. Footer
    # 3. Footer - Removed (prompt handled by UI class)

    # 4. Final Panel
    panel = Panel(
        Group(*items),
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
    Results can be truncated to save space, unlike Inputs.
    """
    console.print()
    if success:
        console.print(f"  [success]✓ {tool_name}[/] [dim]execution successful[/]")
        # Show output if it exists
        if output:
            lines = output.split("\n")
            if len(lines) > 10:
                # Truncate to 10 lines
                preview = "\n".join(lines[:10])
                remaining = len(lines) - 10
                display_out = f"{preview}\n... ({remaining} more lines hidden)"
                console.print(Panel(Text(display_out, style="dim"), box=box.MINIMAL))
            else:
                console.print(Panel(Text(output, style="dim"), box=box.MINIMAL))
    else:
        console.print(f"  [error]✗ {tool_name} Failed[/]")
        if output:
            console.print(Panel(Text(output, style="error"), box=box.MINIMAL))
    console.print()

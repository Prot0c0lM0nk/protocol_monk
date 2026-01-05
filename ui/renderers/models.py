#!/usr/bin/env python3
"""
Model Renderer Module - Orthodox Matrix Theme

Contains pure rendering functions for model management UI components.
"""

from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from typing import Any, List

from ..rich.styles import console


def render_model_table(models: List[Any], current_model: str) -> None:
    """Render a matrix-style table of available models."""
    # Create the Table
    table = Table(
        title="Available Protocols",
        title_style="holy.gold",
        border_style="dim white",
        header_style="bold cyan",
        box=None,
        expand=True,
    )

    table.add_column("Model Name", style="white")
    table.add_column("Provider", style="dim")
    table.add_column("Context", justify="right", style="green")
    table.add_column("Status", justify="center")

    for model in models:
        # Handle both objects (ModelInfo) and dicts
        name = getattr(
            model, "name", model.get("name") if isinstance(model, dict) else str(model)
        )
        provider = getattr(
            model,
            "provider",
            model.get("provider", "unknown") if isinstance(model, dict) else "",
        )
        ctx = getattr(
            model,
            "context_window",
            model.get("context_window", 0) if isinstance(model, dict) else 0,
        )

        is_current = name == current_model

        # Formatting
        status_str = "ACTIVE" if is_current else ""
        row_style = "holy.gold" if is_current else None
        ctx_str = f"{ctx:,}"

        table.add_row(name, provider, ctx_str, status_str, style=row_style)

    console.print()
    console.print(table)
    console.print()


def render_switch_report(report: Any, current_model: str, target_model: str) -> None:
    """Render the Context Guardrail report."""
    # Extract data (handle object vs dict)
    safe = getattr(report, "safe", report.get("safe", False))
    curr = getattr(report, "current_tokens", 0)
    limit = getattr(report, "target_limit", 0)

    if safe:
        # Safe Switch - Small Green Notification
        console.print(f"  [success]✓ Context check passed ({curr:,} < {limit:,})[/]")
    else:
        # DANGER - Red Guardrail Panel
        excess = curr - limit

        msg = Text()
        msg.append("⚠️ CONTEXT OVERFLOW DETECTED\n", style="bold red")
        msg.append(f"Switching from ", style="dim")
        msg.append(current_model, style="bold white")
        msg.append(" to ", style="dim")
        msg.append(target_model, style="bold white")
        msg.append("\n\n")

        msg.append(f"Current Usage: {curr:,} tokens\n", style="red")
        msg.append(f"Target Limit:  {limit:,} tokens\n", style="red")
        msg.append(f"Excess:        +{excess:,} tokens\n", style="bold red underline")

        msg.append(
            "\n[!] You must Prune history or Archive context to proceed.",
            style="dim white",
        )

        panel = Panel(
            msg,
            border_style="red",
            title="[bold red]Protocol Guardrail[/]",
            padding=(1, 2),
        )

        console.print()
        console.print(panel)
        console.print()

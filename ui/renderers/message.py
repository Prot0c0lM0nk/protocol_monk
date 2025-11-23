#!/usr/bin/env python3
"""
Message Renderer - Orthodox Matrix Theme
"""
from rich.markdown import Markdown
from ui.styles import console, create_monk_panel

def render_user_message(text: str):
    """User input: Minimalist."""
    console.print()
    console.print(f"  [dim white]You[/] [holy.gold]›[/] [white]{text}[/]")

def render_agent_message(markdown_text: str):
    """
    The Monk speaks.
    Uses the shared factory for consistent styling.
    """
    md = Markdown(markdown_text)
    
    # Use the Factory!
    panel = create_monk_panel(md)
    
    console.print()
    console.print(panel)
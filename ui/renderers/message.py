#!/usr/bin/env python3
"""
Message Renderer - Orthodox Matrix Theme
"""
import re
from rich.markdown import Markdown

from ui.styles import console, create_monk_panel


def render_user_message(text: str):
    """User input: Minimalist."""
    console.print()
    console.print(f"  [dim white]You[/] [holy.gold]›[/] [white]{text}[/]")


def clean_think_tags(content: str) -> str:
    """
    Remove think tags and their content to prevent visual artifacts.
    
    Rich's Markdown parser treats <think> tags as unknown HTML elements,
    causing inconsistent rendering and visual artifacts in the monk panel.
    This function removes both the tags and their content entirely.
    
    Args:
        content: Raw markdown content that may contain think tags
        
    Returns:
        Cleaned content with think tags removed
    """
    # Use DOTALL flag to match newlines in think blocks
    pattern = r'<think>.*?</think>'
    return re.sub(pattern, '', content, flags=re.DOTALL)


def render_agent_message(markdown_text: str):
    """
    The Monk speaks.
    Uses the shared factory for consistent styling - now with think tag cleansing.
    """
    # Clean think tags before rendering to prevent visual artifacts
    cleaned_content = clean_think_tags(markdown_text)
    
    # Only render if there's actual content after cleaning
    if cleaned_content.strip():
        md = Markdown(cleaned_content)
        panel = create_monk_panel(md)
        console.print()
        console.print(panel)
    else:
        # If no content remains, show a minimal response to avoid empty panels
        console.print()
        console.print("  [dim]The Monk contemplates silently...[/]")

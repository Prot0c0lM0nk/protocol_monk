"""
ui/prompts.py
Async wrappers for Rich Prompts to ensure the event loop (spinners, etc.)
does not freeze during user input.

This module provides shared prompt utilities that can be used by both
PlainUI and RichUI implementations.
"""

import asyncio
from rich.console import Console
from rich.prompt import Prompt, Confirm, IntPrompt
from typing import Optional, List

# Shared console for default prompts (PlainUI fallback)
default_console = Console()


class AsyncPrompt:
    """
    Static namespace for Async-safe Prompt wrappers.
    Uses asyncio.to_thread to run blocking input() in a separate thread.

    This ensures that:
    1. The event loop continues running during user input
    2. Background tasks (spinners, timers) don't freeze
    3. UI updates can still occur while waiting for input
    """

    @staticmethod
    async def ask(
        prompt_text: str,
        password: bool = False,
        choices: Optional[List[str]] = None,
        default: Optional[str] = None,
        console: Optional[Console] = None,
    ) -> str:
        """
        Async wrapper for rich.prompt.Prompt.ask
        Accepts an optional 'console' for themed output.
        """
        target_console = console or default_console

        return await asyncio.to_thread(
            Prompt.ask,
            prompt_text,
            password=password,
            choices=choices,
            default=default,
            console=target_console,
        )

    @staticmethod
    async def confirm(
        prompt_text: str, default: bool = False, console: Optional[Console] = None
    ) -> bool:
        """
        Async wrapper for rich.prompt.Confirm.ask
        """
        target_console = console or default_console

        return await asyncio.to_thread(
            Confirm.ask, prompt_text, default=default, console=target_console
        )

    @staticmethod
    async def ask_int(
        prompt_text: str,
        default: Optional[int] = None,
        console: Optional[Console] = None,
        **kwargs,
    ) -> int:
        """
        Async wrapper for rich.prompt.IntPrompt.ask
        """
        target_console = console or default_console

        return await asyncio.to_thread(
            IntPrompt.ask,
            prompt_text,
            default=default,
            console=target_console,
            **kwargs,
        )

    @staticmethod
    async def ask_float(
        prompt_text: str,
        default: Optional[float] = None,
        console: Optional[Console] = None,
        **kwargs,
    ) -> float:
        """
        Async wrapper for rich.prompt.FloatPrompt.ask
        """
        from rich.prompt import FloatPrompt

        target_console = console or default_console

        return await asyncio.to_thread(
            FloatPrompt.ask,
            prompt_text,
            default=default,
            console=target_console,
            **kwargs,
        )

    @staticmethod
    async def select(
        prompt_text: str,
        choices: List[str],
        default: Optional[int] = None,
        console: Optional[Console] = None,
    ) -> str:
        """
        Async wrapper for selecting from a list of choices.
        Uses the provided console for printing the list.
        """
        target_console = console or default_console

        # Display numbered choices
        target_console.print(f"\n{prompt_text}")
        for i, choice in enumerate(choices):
            marker = "→" if i == default else " "
            target_console.print(f"  {marker} [{i}] {choice}")

        # Get user selection
        selection = await AsyncPrompt.ask_int(
            "Enter choice number",
            default=default if default is not None else 0,
            console=target_console,
        )

        # Validate selection
        if 0 <= selection < len(choices):
            return choices[selection]
        else:
            target_console.print(f"[red]Invalid selection. Using default.[/red]")
            return choices[default] if default is not None else choices[0]


# Convenience functions for direct use (Default Console)
async def ask(prompt_text: str, **kwargs) -> str:
    """Convenience function for text input"""
    return await AsyncPrompt.ask(prompt_text, **kwargs)


async def confirm(prompt_text: str, default: bool = False) -> bool:
    """Convenience function for yes/no confirmation"""
    return await AsyncPrompt.confirm(prompt_text, default)


async def ask_int(prompt_text: str, **kwargs) -> int:
    """Convenience function for integer input"""
    return await AsyncPrompt.ask_int(prompt_text, **kwargs)


async def ask_float(prompt_text: str, **kwargs) -> float:
    """Convenience function for float input"""
    return await AsyncPrompt.ask_float(prompt_text, **kwargs)


async def select(prompt_text: str, choices: List[str], **kwargs) -> str:
    """Convenience function for selection from list"""
    return await AsyncPrompt.select(prompt_text, choices, **kwargs)

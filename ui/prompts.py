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

# Shared console for prompts to ensure standard output handling
# We use stderr=True often for prompts to separate them from piped output,
# but for the main agent UI, standard stdout is usually fine.
console = Console()


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
        default: Optional[str] = None
    ) -> str:
        """
        Async wrapper for rich.prompt.Prompt.ask
        
        Args:
            prompt_text: The prompt message to display
            password: If True, mask the input (for passwords)
            choices: List of valid choices (auto-completes)
            default: Default value if user just presses Enter
            
        Returns:
            str: The user's input
            
        Example:
            >>> name = await AsyncPrompt.ask("Enter your name")
            >>> color = await AsyncPrompt.ask("Pick a color", choices=["red", "blue", "green"])
        """
        return await asyncio.to_thread(
            Prompt.ask,
            prompt_text,
            password=password,
            choices=choices,
            default=default,
            console=console
        )

    @staticmethod
    async def confirm(prompt_text: str, default: bool = False) -> bool:
        """
        Async wrapper for rich.prompt.Confirm.ask
        
        Args:
            prompt_text: The confirmation question
            default: Default value if user just presses Enter
            
        Returns:
            bool: True if user confirms, False otherwise
            
        Example:
            >>> if await AsyncPrompt.confirm("Continue?", default=True):
            ...     print("Proceeding...")
        """
        return await asyncio.to_thread(
            Confirm.ask,
            prompt_text,
            default=default,
            console=console
        )

    @staticmethod
    async def ask_int(prompt_text: str, default: Optional[int] = None, **kwargs) -> int:
        """
        Async wrapper for rich.prompt.IntPrompt.ask
        
        Args:
            prompt_text: The prompt message
            default: Default value if user just presses Enter
            **kwargs: Additional arguments for IntPrompt
            
        Returns:
            int: The user's integer input
            
        Example:
            >>> count = await AsyncPrompt.ask_int("How many items?", default=1)
        """
        return await asyncio.to_thread(
            IntPrompt.ask,
            prompt_text,
            default=default,
            console=console,
            **kwargs
        )

    @staticmethod
    async def ask_float(prompt_text: str, default: Optional[float] = None, **kwargs) -> float:
        """
        Async wrapper for rich.prompt.FloatPrompt.ask
        
        Args:
            prompt_text: The prompt message
            default: Default value if user just presses Enter
            **kwargs: Additional arguments for FloatPrompt
            
        Returns:
            float: The user's float input
        """
        from rich.prompt import FloatPrompt
        
        return await asyncio.to_thread(
            FloatPrompt.ask,
            prompt_text,
            default=default,
            console=console,
            **kwargs
        )

    @staticmethod
    async def select(prompt_text: str, choices: List[str], default: Optional[int] = None) -> str:
        """
        Async wrapper for selecting from a list of choices
        
        Args:
            prompt_text: The prompt message
            choices: List of choices to select from
            default: Default choice index (0-based)
            
        Returns:
            str: The selected choice
            
        Example:
            >>> fruit = await AsyncPrompt.select("Pick a fruit", ["apple", "banana", "orange"])
        """
        # Display numbered choices
        console.print(f"\n{prompt_text}")
        for i, choice in enumerate(choices):
            marker = "→" if i == default else " "
            console.print(f"  {marker} [{i}] {choice}")
        
        # Get user selection
        selection = await AsyncPrompt.ask_int(
            "Enter choice number",
            default=default if default is not None else 0
        )
        
        # Validate selection
        if 0 <= selection < len(choices):
            return choices[selection]
        else:
            console.print(f"[red]Invalid selection. Using default.[/red]")
            return choices[default] if default is not None else choices[0]


# Convenience functions for direct use
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
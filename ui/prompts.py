"""
ui/prompts.py
Async wrappers for Rich Prompts to ensure the event loop (spinners, etc.)
does not freeze during user input.
"""
import asyncio
from rich.console import Console
from rich.prompt import Prompt, Confirm, IntPrompt

# Shared console for prompts to ensure standard output handling
# We use stderr=True often for prompts to separate them from piped output,
# but for the main agent UI, standard stdout is usually fine.
console = Console()

class AsyncPrompt:
    """
    Static namespace for Async-safe Prompt wrappers.
    Uses asyncio.to_thread to run blocking input() in a separate thread.
    """

    @staticmethod
    async def ask(
        prompt_text: str,
        password: bool = False,
        choices: list[str] = None,
        default: str = None
    ) -> str:
        """Async wrapper for rich.prompt.Prompt.ask"""
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
        """Async wrapper for rich.prompt.Confirm.ask"""
        return await asyncio.to_thread(
            Confirm.ask,
            prompt_text,
            default=default,
            console=console
        )

    @staticmethod
    async def ask_int(prompt_text: str, default: int = None, **kwargs) -> int:
        """Async wrapper for rich.prompt.IntPrompt.ask"""
        return await asyncio.to_thread(
            IntPrompt.ask,
            prompt_text,
            default=default,
            console=console,
            **kwargs
        )
"""
Rich-styled input handler using prompt_toolkit with Rich console integration.
"""

import asyncio
from typing import Optional
from prompt_toolkit import PromptSession
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.keys import Keys
from prompt_toolkit.patch_stdout import patch_stdout

from .styles import console


class RichInputHandler:
    """
    Async input handler using prompt_toolkit with Rich styling.
    - Multiline support (Enter = submit, Ctrl+Enter = newline)
    - Arrow key navigation
    - Command history (in-memory only)
    - Ctrl+D = graceful shutdown (EOF)
    - Rich console integration for themed prompts
    """

    def __init__(self):
        self.history = InMemoryHistory()

        # Configure key bindings: Enter submits, Ctrl+Enter is newline
        kb = KeyBindings()

        @kb.add(Keys.Enter)
        def _(event):
            """Enter submits the input."""
            event.app.current_buffer.validate_and_handle()

        @kb.add("c-j")  # Ctrl+Enter / Ctrl+J
        def _(event):
            """Ctrl+Enter inserts a newline."""
            event.app.current_buffer.insert_text("\n")

        self.session = PromptSession(history=self.history, key_bindings=kb)
        self._prompt_lock = asyncio.Lock()

    async def get_input(self, prompt: str = "  › ") -> Optional[str]:
        """
        Get multiline input from user. Blocks until user submits.
        Uses Rich console for prompt styling.
        Returns None on empty input, cancellation, or Ctrl+D (EOF).
        """
        async with self._prompt_lock:
            try:
                # patch_stdout ensures printed text (events) appears ABOVE the prompt
                with patch_stdout():
                    result = await self.session.prompt_async(prompt)
                if result and result.strip():
                    self.history.append_string(result)
                    return result.strip()
                return None
            except EOFError:
                # Ctrl+D pressed - signal shutdown
                return None
            except (KeyboardInterrupt, Exception):
                # Other interruptions
                return None

    async def confirm(self, prompt: str, default: bool = True) -> bool:
        """
        Get yes/no confirmation from user using Rich prompts.
        Blocks until user responds.
        """
        from ui.prompts import AsyncPrompt
        suffix = " [Y/n]" if default else " [y/N]"
        full_prompt = f"{prompt}{suffix}"

        return await AsyncPrompt.confirm(full_prompt, default=default, console=console)

    async def select_with_arrows(self, prompt: str, options: list[str], default_index: int = 0) -> int:
        """
        Get selection from list using arrow keys (radiolist dialog).
        Returns the index of the selected option.
        Used for error recovery (Resend / Return control).
        """
        from prompt_toolkit.shortcuts import radiolist_dialog

        result = await radiolist_dialog(
            title=prompt,
            values=[(i, opt) for i, opt in enumerate(options)],
            default=default_index,
        ).run_async()

        if result is None:
            return default_index  # Cancelled, return default
        return result

    async def select(self, prompt: str, options: list[str], default: int = 0) -> str:
        """
        Get selection from list of options (number input).
        Returns the selected option string.
        Uses Rich-style selection display.
        """
        # Display numbered choices with Rich styling
        console.print(f"\n{prompt}")
        for i, option in enumerate(options):
            marker = "→" if i == default else " "
            console.print(f"  {marker} [{i}] {option}")

        # Get user selection using prompt_toolkit
        while True:
            try:
                response = await self.get_input("Enter choice number: ")
                if response is None:
                    return options[default]
                response = response.strip()

                if response.isdigit():
                    idx = int(response)
                    if 0 <= idx < len(options):
                        return options[idx]

                # Invalid, prompt again
                console.print("[red]Invalid selection. Try again.[/red]")
            except Exception:
                return options[default]
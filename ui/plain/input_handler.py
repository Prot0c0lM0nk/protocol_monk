"""
Input handler using prompt_toolkit for async multiline input.
"""

import asyncio
from typing import Optional

from prompt_toolkit import PromptSession
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.keys import Keys


class InputHandler:
    """
    Async input handler using prompt_toolkit.
    - Multiline support (Enter = submit, Ctrl+Enter = newline)
    - Arrow key navigation
    - Command history (in-memory only)
    - Ctrl+D = graceful shutdown (EOF)
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

    async def get_input(self, prompt: str = ">>> ") -> Optional[str]:
        """
        Get multiline input from user. Blocks until user submits.
        Returns None on empty input, cancellation, or Ctrl+D (EOF).
        """
        async with self._prompt_lock:
            try:
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
        Get yes/no confirmation from user.
        Blocks until user responds.
        """
        suffix = " [Y/n]" if default else " [y/N]"
        full_prompt = f"{prompt}{suffix}"

        while True:
            try:
                response = await self.session.prompt_async(full_prompt)
                response = response.strip().lower()

                if response in ("y", "yes"):
                    return True
                elif response in ("n", "no"):
                    return False
                elif response == "" or response.startswith("\r"):
                    return default
            except EOFError:
                # Ctrl+D - return default
                return default
            # Invalid input, prompt again

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
        """
        display = f"\n{prompt}\n"
        for i, option in enumerate(options):
            marker = "->" if i == default else " "
            display += f"  {marker} [{i}] {option}\n"
        display += f"Enter choice number: "

        while True:
            try:
                response = await self.session.prompt_async(display)
                response = response.strip()

                if response.isdigit():
                    idx = int(response)
                    if 0 <= idx < len(options):
                        return options[idx]

                # Try exact match
                if response in options:
                    return options[response]

                # Invalid, prompt again
            except EOFError:
                return options[default]
"""
ui/plain/input.py - Input Abstraction Layer
"""

import asyncio
from prompt_toolkit import PromptSession
from prompt_toolkit.patch_stdout import patch_stdout
from prompt_toolkit.formatted_text import HTML
from typing import Optional


class InputManager:
    """
    Manages all user input operations using prompt_toolkit.
    Ensures single input source and proper stdout patching.
    """

    def __init__(self):
        self.session = PromptSession()
        self._is_prompt_active: bool = False

    async def read_input(
        self, prompt_text: str = "", is_main_loop: bool = False
    ) -> Optional[str]:
        """
        Read user input with proper stdout patching.
        Returns None on KeyboardInterrupt/EOF to signal exit.
        """
        # 1. Prepare Label
        if is_main_loop:
            label = HTML("\nUSER &gt; ")
        else:
            clean_prompt = prompt_text.rstrip(" :>")
            label = HTML(
                f"\n<style fg='ansibrightblack'>[SYS] {clean_prompt}</style> &gt; "
            )

        # 2. Mark prompt active
        if self._is_prompt_active:
            # Prompt already active - return None to signal cancellation
            return None
        self._is_prompt_active = True

        # 3. Wait for Input
        try:
            with patch_stdout():
                return await self.session.prompt_async(label)
        except (KeyboardInterrupt, EOFError):
            return None  # Signal to the controller that we want to quit
        except asyncio.CancelledError:
            # Task was cancelled (e.g., by timeout)
            return None
        finally:
            self._is_prompt_active = False

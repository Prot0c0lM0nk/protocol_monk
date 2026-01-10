"""
ui/rich/input.py
PromptToolkit wrapper for the main chat loop.
"""

from prompt_toolkit import PromptSession
from prompt_toolkit.patch_stdout import patch_stdout
from prompt_toolkit.output import create_output
from prompt_toolkit.input import create_input
from .styles import console


class RichInput:
    def __init__(self):
        # Initialize session with safe defaults
        self.session = PromptSession(
            input=create_input(),
            output=create_output(),
            mouse_support=False,
            complete_while_typing=False,
        )

    async def get_input(self, prompt_text: str = "") -> str:
        """
        Get input using prompt_toolkit, protected by patch_stdout
        to ensure background logs don't destroy the prompt line.
        """
        # Render a nice prompt using our theme before the input line
        # We use a simple Unicode cross or standard prompt
        if prompt_text:
            console.print(f"[user.text]{prompt_text}[/]")

        # The prompt string itself (on the input line)
        pt_prompt = "  › "

        try:
            # patch_stdout ensures printed text (events) appears ABOVE the prompt
            with patch_stdout():
                return await self.session.prompt_async(pt_prompt)
        except (EOFError, KeyboardInterrupt):
            return ""

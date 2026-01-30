"""
Async prompts that integrate with AsyncInputManager.

These prompts work with the async keyboard capture system,
ensuring input is properly captured without blocking the event loop.
"""

import asyncio
from typing import Optional, List
from dataclasses import dataclass

from .async_input_interface import AsyncInputManager, InputEvent, InputEventType


@dataclass
class PromptResult:
    """Result of an async prompt."""
    value: str
    confirmed: bool = True
    cancelled: bool = False


class AsyncPrompts:
    """
    Async prompts that integrate with AsyncInputManager.
    
    Usage:
        prompts = AsyncPrompts(input_manager)
        result = await prompts.confirm("Execute command?")
        text = await prompts.text("Enter name:")
        choice = await prompts.select("Choose:", ["a", "b", "c"])
    """

    def __init__(self, input_manager: AsyncInputManager):
        self.input_manager = input_manager

    async def text(
        self,
        prompt_text: str,
        default: str = "",
        placeholder: Optional[str] = None,
    ) -> str:
        """Get text input from user."""
        # Display prompt
        print(f"{prompt_text}", end="", flush=True)
        
        # Collect input until Enter
        text = ""
        async for event in self.input_manager.get_current_events():
            if event.type == InputEventType.CHARACTER:
                text += event.data
                print(event.data, end="", flush=True)  # Echo character
            elif event.type == InputEventType.SPECIAL_KEY:
                if event.data == "enter":
                    print()  # Add newline on enter
                    break
                elif event.data == "backspace":
                    text = text[:-1]
                    print("\b \b", end="", flush=True)  # Erase character
            elif event.type == InputEventType.KEY:
                if event.data == "backspace":
                    text = text[:-1]
                    print("\b \b", end="", flush=True)  # Erase character
    async def confirm(self, prompt_text: str, default: bool = True) -> bool:
        """Get yes/no confirmation from user."""
        suffix = " [Y/n]" if default else " [y/N]"
        
        print(f"{prompt_text}{suffix}", end="", flush=True)
        
        while True:
            async for event in self.input_manager.get_current_events():
                if event.type in (InputEventType.CHARACTER, InputEventType.KEY):
                    key = event.data.lower()
                    if key in ("y", "yes"):
                        print()  # Add newline
                        return True
                    elif key in ("n", "no"):
                        print()  # Add newline
                        return False
                    elif key == "enter":
                        print()  # Add newline
                        return default
    async def select(
        self,
        prompt_text: str,
        choices: List[str],
        default: int = 0,
    ) -> str:
        """Get selection from a list of choices."""
        # Display prompt and choices
        print(f"\n{prompt_text}")
        for i, choice in enumerate(choices):
            marker = "→" if i == default else " "
            print(f"  {marker} [{i}] {choice}")
        print(f"Enter choice number:", end="", flush=True)
        
        # Collect number input
        num_str = ""
        async for event in self.input_manager.get_current_events():
            if event.type == InputEventType.CHARACTER:
                if event.data.isdigit():
                    num_str += event.data
                    print(event.data, end="", flush=True)
            elif event.type in (InputEventType.SPECIAL_KEY, InputEventType.KEY):
                if event.data == "enter":
                    print()  # Add newline on enter
                    break
                elif event.data == "backspace":
                    num_str = num_str[:-1]
                    print("\b \b", end="", flush=True)
                    num_str = num_str[:-1]
                    print("\b \b", end="", flush=True)
        
        try:
            idx = int(num_str) if num_str else default
            if 0 <= idx < len(choices):
                return choices[idx]
        except ValueError:
            pass
        
        return choices[default] if 0 <= default < len(choices) else choices[0]


# Factory function
def create_async_prompts(input_manager: AsyncInputManager) -> AsyncPrompts:
    """Create async prompts instance."""
    return AsyncPrompts(input_manager)
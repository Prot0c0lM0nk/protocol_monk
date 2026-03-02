"""Prompt-toolkit input helpers for the Rich runtime UI."""

from __future__ import annotations

import asyncio
import logging
from typing import Callable, Sequence

from prompt_toolkit import PromptSession
from prompt_toolkit.application import run_in_terminal
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.patch_stdout import patch_stdout
from rich.box import ROUNDED
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from .styles import console as default_console

logger = logging.getLogger("RichInputHandler")


class RichInputHandler:
    """Async input/confirmation primitives used by the Rich UI."""

    def __init__(self, on_ctrl_o: Callable[[], None] | None = None) -> None:
        self._history = InMemoryHistory()
        self._session = PromptSession(multiline=False, history=self._history)
        self._prompt_lock = asyncio.Lock()
        self._on_ctrl_o = on_ctrl_o
        self._keybindings = self._create_keybindings()

    def _create_keybindings(self) -> KeyBindings:
        """Create keybindings for the input handler."""
        kb = KeyBindings()

        @kb.add("c-o")  # Ctrl+O
        def _(event):
            _ = event
            if self._on_ctrl_o:
                run_in_terminal(self._on_ctrl_o, in_executor=False)

        return kb

    async def prompt(self, prompt_text: str) -> str:
        """Prompt for a single line of input."""
        async with self._prompt_lock:
            with patch_stdout():
                return await self._session.prompt_async(
                    prompt_text,
                    key_bindings=self._keybindings,
                )

    async def confirm_tool_execution(
        self,
        *,
        tool_name: str,
        parameters: dict,
        console: Console | None = None,
    ) -> str | None:
        """Return one of: approve, approve_auto, reject.

        Uses a scrollback-native panel-based approach - no modal dialogs.
        Waits for explicit user input indefinitely.
        """
        _ = parameters  # Parameters are displayed in the Rich confirmation panel.
        target_console = console or default_console

        # Print confirmation panel to scrollback
        target_console.print(Panel(
            Text(f"Approve tool execution: {tool_name}", style="monk.text"),
            title="Tool Confirmation",
            title_align="left",
            border_style="tech.cyan",
            box=ROUNDED,
        ))

        # Prompt for selection
        try:
            while True:
                answer = await self.prompt("Approve? [Y]es / [A]uto / [N]o (default N): ")
                normalized = answer.strip().lower()

                if not normalized:
                    return "reject"

                if normalized in {"y", "yes"}:
                    return "approve"
                if normalized in {"a", "auto"}:
                    return "approve_auto"
                if normalized in {"n", "no"}:
                    return "reject"

                target_console.print("[error]Invalid choice. Use Y, A, or N.[/]")

        except (EOFError, KeyboardInterrupt):
            return "reject"
        except Exception as exc:
            logger.error("Confirmation error: %s", exc, exc_info=True)
            return "reject"

    async def confirm_yes_no(self, prompt_text: str, *, default: bool = False) -> bool:
        """Simple text confirmation prompt for deferred UI actions."""
        suffix = " [Y/n]" if default else " [y/N]"
        while True:
            try:
                answer = await self.prompt(f"{prompt_text}{suffix} ")
            except (EOFError, KeyboardInterrupt):
                return default
            normalized = answer.strip().lower()
            if not normalized:
                return default
            if normalized in {"y", "yes"}:
                return True
            if normalized in {"n", "no"}:
                return False
            print("Invalid choice. Use y or n.")

    async def select_with_arrows(
        self,
        *,
        prompt_text: str,
        options: Sequence[str],
        default_index: int = 0,
    ) -> int:
        """Choose one option using panel-based selection.

        Note: Despite the name, this now uses number-based selection
        instead of arrow keys for scrollback-native behavior.
        """
        return await self.select_from_list(
            title=prompt_text,
            options=options,
            default_index=default_index,
        )

    async def select_from_list(
        self,
        *,
        title: str,
        options: Sequence[str],
        default_index: int = 0,
        console: Console | None = None,
    ) -> int:
        """Select from a list using a Rich panel and number input.

        This is a scrollback-native approach - no modal dialogs.
        Prints choices to terminal and prompts for number selection.

        Args:
            title: Panel title
            options: List of option strings to display
            default_index: Default selection if user presses Enter
            console: Rich console to use (defaults to styled console)

        Returns:
            Selected index (0-based)
        """
        target_console = console or default_console

        if not options:
            return default_index

        # Build choices text
        lines = []
        for i, option in enumerate(options):
            marker = "→" if i == default_index else " "
            lines.append(f"{marker} [{i}] {option}")

        content = Text("\n".join(lines), style="monk.text")

        # Print panel to scrollback
        target_console.print(Panel(
            content,
            title=title,
            title_align="left",
            border_style="monk.border",
            box=ROUNDED,
        ))

        # Prompt for selection
        max_index = len(options) - 1
        while True:
            try:
                answer = await self.prompt(f"Select [0-{max_index}] (default {default_index}): ")
                if not answer.strip():
                    return default_index
                selection = int(answer.strip())
                if 0 <= selection < len(options):
                    return selection
                target_console.print("[error]Invalid selection. Try again.[/]")
            except ValueError:
                target_console.print("[error]Please enter a number.[/]")
            except (EOFError, KeyboardInterrupt):
                return default_index

    @staticmethod
    def _format_parameters_for_dialog(parameters: dict) -> str:
        lines = []
        for key, value in parameters.items():
            text = str(value)
            if len(text) > 400:
                text = f"{text[:400]}... [truncated {len(text) - 400} chars]"
            lines.append(f"  {key}: {text}")
        return "\n".join(lines)

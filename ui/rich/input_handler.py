"""Prompt-toolkit input helpers for the Rich runtime UI."""

from __future__ import annotations

import asyncio
import logging
from typing import Sequence

from prompt_toolkit import PromptSession
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.patch_stdout import patch_stdout
from prompt_toolkit.shortcuts import button_dialog, radiolist_dialog

from .styles import ORTHODOX_DIALOG_STYLE

logger = logging.getLogger("RichInputHandler")


class RichInputHandler:
    """Async input/confirmation primitives used by the Rich UI."""

    def __init__(self) -> None:
        self._history = InMemoryHistory()
        self._session = PromptSession(multiline=False, history=self._history)
        self._prompt_lock = asyncio.Lock()

    async def prompt(self, prompt_text: str) -> str:
        """Prompt for a single line of input."""
        async with self._prompt_lock:
            with patch_stdout():
                return await self._session.prompt_async(prompt_text)

    async def confirm_tool_execution(
        self,
        *,
        tool_name: str,
        parameters: dict,
        timeout: float = 20.0,
    ) -> str | None:
        """Return one of: approve, approve_auto, reject."""
        _ = parameters  # Parameters are displayed in the Rich confirmation panel.
        try:
            result = await asyncio.wait_for(
                button_dialog(
                    title="Tool Confirmation",
                    text=f"Approve tool execution: {tool_name}",
                    buttons=[
                        ("Yes", "approve"),
                        ("Yes + Auto", "approve_auto"),
                        ("No", "reject"),
                    ],
                    style=ORTHODOX_DIALOG_STYLE,
                ).run_async(),
                timeout=timeout,
            )
            return result if result else "reject"
        except asyncio.TimeoutError:
            logger.warning(
                "Confirmation timed out for %s; rejecting by default.",
                tool_name,
            )
            return "reject"
        except (EOFError, KeyboardInterrupt):
            return "reject"
        except Exception as exc:
            logger.error("Confirmation dialog error: %s", exc, exc_info=True)
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
        """Choose one option using prompt-toolkit radiolist dialog."""
        result = await radiolist_dialog(
            title=prompt_text,
            values=[(index, option) for index, option in enumerate(options)],
            default=default_index,
            style=ORTHODOX_DIALOG_STYLE,
        ).run_async()
        if result is None:
            return default_index
        return int(result)

    @staticmethod
    def _format_parameters_for_dialog(parameters: dict) -> str:
        lines = []
        for key, value in parameters.items():
            text = str(value)
            if len(text) > 400:
                text = f"{text[:400]}... [truncated {len(text) - 400} chars]"
            lines.append(f"  {key}: {text}")
        return "\n".join(lines)

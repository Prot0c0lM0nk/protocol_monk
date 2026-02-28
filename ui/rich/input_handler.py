"""Prompt-toolkit input helpers for the Rich runtime UI."""

from __future__ import annotations

import asyncio
import logging
from typing import Sequence

from prompt_toolkit import PromptSession
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.patch_stdout import patch_stdout
from prompt_toolkit.shortcuts import button_dialog, radiolist_dialog

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
        """Return one of: approve, approve_auto, reject, or None (closed)."""
        dialog_text = (
            f"Execute tool: {tool_name}\n\n"
            "Choose an action (mouse click or keyboard Tab/Enter):\n\n"
            f"Parameters:\n{self._format_parameters_for_dialog(parameters)}"
        )
        try:
            async with self._prompt_lock:
                with patch_stdout():
                    return await asyncio.wait_for(
                        button_dialog(
                            title="Tool Execution",
                            text=dialog_text,
                            buttons=[
                                ("Yes", "approve"),
                                ("Yes + Auto-Approve Edits", "approve_auto"),
                                ("No (Return Control)", "reject"),
                            ],
                        ).run_async(),
                        timeout=timeout,
                    )
        except asyncio.TimeoutError:
            logger.warning(
                "Confirmation dialog timed out for %s; falling back to text prompt.",
                tool_name,
            )
            return await self.prompt_confirmation_text(tool_name)
        except Exception as exc:
            logger.error("Confirmation dialog error: %s", exc, exc_info=True)
            return "reject"

    async def prompt_confirmation_text(self, tool_name: str) -> str:
        """Fallback text confirmation prompt."""
        print(
            f"\n[Approval Fallback] {tool_name}\n"
            "Enter: y=approve, a=approve+auto, n=reject"
        )
        choices = {
            "y": "approve",
            "yes": "approve",
            "a": "approve_auto",
            "aa": "approve_auto",
            "n": "reject",
            "no": "reject",
            "r": "reject",
        }
        while True:
            try:
                answer = await self.prompt("(y/a/n) > ")
            except (EOFError, KeyboardInterrupt):
                return "reject"
            choice = answer.strip().lower()
            if choice in choices:
                return choices[choice]
            print("Invalid choice. Use y, a, or n.")

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

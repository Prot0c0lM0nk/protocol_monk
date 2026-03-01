"""Prompt-toolkit input helpers for the Rich runtime UI."""

from __future__ import annotations

import asyncio
import logging
from typing import Sequence

from prompt_toolkit import PromptSession
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.patch_stdout import patch_stdout
from prompt_toolkit.shortcuts import radiolist_dialog

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
        prompt_text = (
            f"Approve tool '{tool_name}'? [y]es / [a]uto / [n]o > "
        )
        loop = asyncio.get_running_loop()
        deadline = loop.time() + max(timeout, 0.1)
        decision_map = {
            "y": "approve",
            "yes": "approve",
            "a": "approve_auto",
            "aa": "approve_auto",
            "auto": "approve_auto",
            "n": "reject",
            "no": "reject",
            "r": "reject",
            "reject": "reject",
        }
        try:
            while True:
                remaining = deadline - loop.time()
                if remaining <= 0:
                    logger.warning(
                        "Confirmation timed out for %s; rejecting by default.",
                        tool_name,
                    )
                    return "reject"
                answer = await asyncio.wait_for(self.prompt(prompt_text), timeout=remaining)
                normalized = answer.strip().lower()
                if normalized in decision_map:
                    return decision_map[normalized]
                print("Invalid choice. Use y, a, or n.")
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

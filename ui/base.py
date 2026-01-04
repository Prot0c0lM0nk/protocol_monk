"""
ui/base.py
"""

import asyncio
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from dataclasses import dataclass


@dataclass
class ToolResult:
    success: bool
    output: str
    tool_name: Optional[str] = None
    tool_call_id: Optional[str] = None


class UI(ABC):
    """The Contract: What the Agent expects the UI to do."""

    def __init__(self):
        self._lock = asyncio.Lock()

    # --- BLOCKING INTERACTION METHODS (The Fix) ---
    @abstractmethod
    async def get_input(self) -> str:
        """
        Get user input for the main loop.
        BLOCKS until user provides input.
        """
        pass

    @abstractmethod
    async def confirm_tool_execution(self, tool_call_data: Dict[str, Any]) -> bool:
        """
        Ask user to confirm a tool execution.
        BLOCKS until user approves (True) or denies (False).
        """
        pass

    # --- Output Methods ---
    @abstractmethod
    async def print_stream(self, text: str):
        pass

    @abstractmethod
    async def print_error(self, message: str):
        pass

    @abstractmethod
    async def print_info(self, message: str):
        pass

    @abstractmethod
    async def start_thinking(self):
        pass

    @abstractmethod
    async def stop_thinking(self):
        pass

    # --- Compat Stubs ---
    async def close(self):
        pass

    async def display_tool_result(self, result: ToolResult, tool_name: str):
        pass

    async def prompt_user(self, prompt: str) -> str:
        return await self.get_input()

    # These can be implemented by subclasses or left as pass
    async def display_selection_list(self, title: str, items: List[Any]):
        pass

    async def display_startup_banner(self, greeting: str):
        pass

    async def display_execution_start(self, count: int):
        pass

    async def display_progress(self, current: int, total: int):
        pass

    async def display_task_complete(self, summary: str = ""):
        pass

    async def print_warning(self, message: str):
        pass

    async def set_auto_confirm(self, value: bool):
        pass

    async def display_model_list(self, models, current):
        pass

    async def display_switch_report(self, report, current, target):
        pass

    async def display_provider_switched(self, provider: str):
        pass

    async def shutdown(self):
        pass

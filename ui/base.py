#!/usr/bin/env python3
"""
Abstract async UI interface for Protocol Monk

Defines the contract for all UI implementations (Rich, Plain, Textual, etc.)
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Union, List
from dataclasses import dataclass
import asyncio


@dataclass
class ToolResult:
    """Result from executing a tool"""

    success: bool
    output: str
    tool_name: str = None


class UI(ABC):
    """Abstract async UI interface for all user interactions"""

    @abstractmethod
    async def confirm_tool_call(
        self, tool_call: Dict, auto_confirm: bool = False
    ) -> Union[bool, Dict]:
        """
        Ask user to confirm a tool call.

        Returns:
            bool: True if approved, False if rejected
            OR dict: {"modified": tool_call} if user modified parameters
        """
        pass

    @abstractmethod
    async def display_tool_call(self, tool_call: Dict, auto_confirm: bool = False):
        """Display a tool call to the user"""
        pass

    @abstractmethod
    async def display_tool_result(self, result: ToolResult, tool_name: str):
        """Display tool execution result"""
        pass

    @abstractmethod
    async def display_execution_start(self, count: int):
        """Display execution start notification"""
        pass

    @abstractmethod
    async def display_progress(self, current: int, total: int):
        """Display execution progress"""
        pass

    @abstractmethod
    async def display_task_complete(self, summary: str = ""):
        """Display task completion notification"""
        pass

    @abstractmethod
    async def print_error(self, message: str):
        """Display error message"""
        pass

    @abstractmethod
    async def print_warning(self, message: str):
        """Display warning message"""
        pass

    @abstractmethod
    async def print_info(self, message: str):
        """Display info message"""
        pass

    @abstractmethod
    async def set_auto_confirm(self, value: bool):
        """Set auto-confirm mode"""
        pass

    @abstractmethod
    async def print_stream(self, text: str):
        """Stream text output without newline (for LLM responses)"""
        pass

    @abstractmethod
    async def display_startup_banner(self, greeting: str):
        """Display startup banner/greeting"""
        pass

    @abstractmethod
    async def display_startup_frame(self, frame: str):
        """Display startup animation frame"""
        pass

    @abstractmethod
    async def prompt_user(self, prompt: str) -> str:
        """Prompt user for input"""
        pass

    @abstractmethod
    async def print_error_stderr(self, message: str):
        """Print error to stderr"""
        pass

    @abstractmethod
    async def start_thinking(self):
        """Start the thinking/loading animation"""

    @abstractmethod
    async def start_thinking(self):
        """Start the thinking/loading animation"""
        pass

    # --- NEW: MODEL MANAGER METHODS ---

    @abstractmethod
    async def display_model_list(self, models: List[Any], current_model: str):
        """
        Display list of available models.
        Args:
            models: List of ModelInfo objects (or dicts)
            current_model: The name of the currently active model
        """
        pass

    @abstractmethod
    async def display_switch_report(
        self, report: Any, current_model: str, target_model: str
    ):
        """
        Display the safety report for a proposed model switch.
        Args:
            report: SwitchReport object
            current_model: Name of model switching FROM
            target_model: Name of model switching TO
        """
        pass

# ui/base.py
import asyncio
from abc import ABC, abstractmethod
from typing import Dict, Union, Any, Optional, List
from dataclasses import dataclass

@dataclass
class ToolResult:
    success: bool
    output: str
    tool_name: Optional[str] = None

class UI(ABC):
    """The Contract: What the Agent expects the UI to do."""
    
    def __init__(self):
        self._lock = asyncio.Lock()

    # --- The Agent calls these ---
    @abstractmethod
    async def print_stream(self, text: str): pass
    
    @abstractmethod
    async def print_error(self, message: str): pass
    
    @abstractmethod
    async def print_info(self, message: str): pass
    
    @abstractmethod
    async def start_thinking(self): pass
    
    @abstractmethod
    async def stop_thinking(self): pass

    @abstractmethod
    async def prompt_user(self, prompt: str) -> str: pass

    @abstractmethod
    async def display_selection_list(self, title: str, items: List[Any]):
        """
        Display a selectable list of items (models, providers, files).
        For TUI: Shows a popup modal.
        For CLI: Prints a numbered list.
        """
        pass
    
    # --- Stubs for compatibility (we will fill these later) ---
    async def close(self): pass
    async def display_startup_banner(self, greeting: str): pass
    async def confirm_tool_call(self, tool_call: Dict, auto_confirm: bool = False): return True
    async def display_tool_call(self, tool_call: Dict, auto_confirm: bool = False): pass
    async def display_tool_result(self, result: ToolResult, tool_name: str): pass
    async def display_execution_start(self, count: int): pass
    async def display_progress(self, current: int, total: int): pass
    async def display_task_complete(self, summary: str = ""): pass
    async def print_warning(self, message: str): pass
    async def print_error_stderr(self, message: str): pass
    async def set_auto_confirm(self, value: bool): pass
    async def display_startup_frame(self, frame: str): pass
    async def display_model_list(self, models, current): pass
    async def display_switch_report(self, report, current, target): pass
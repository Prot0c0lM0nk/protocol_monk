"""
Async keyboard capture implementation.
Adapts low-level system keys to high-level InputEvents.
"""

import asyncio
import platform
import sys
import time
from typing import Optional, List, AsyncIterator
from dataclasses import dataclass

from .terminal_utils import TerminalState
# Import the shared definitions
from .async_input_interface import AsyncInputInterface, InputEvent, InputEventType


class AsyncKeyboardCapture(AsyncInputInterface):
    """Abstract base class for async keyboard capture."""

    def __init__(self):
        super().__init__()
        self._capture_task: Optional[asyncio.Task] = None

    async def display_prompt(self) -> None:
        # Keyboard capture doesn't handle rendering, so this is a no-op
        pass

    async def start_capture(self) -> None:
        if self._running:
            return
        if not self._is_terminal():
            return

        self._running = True
        self._capture_task = asyncio.create_task(self._capture_loop())

    async def stop_capture(self) -> None:
        self._running = False
        if self._capture_task:
            self._capture_task.cancel()
            try:
                await self._capture_task
            except asyncio.CancelledError:
                pass

    # --- Match the Interface Method Name ---
    async def get_input_events(self) -> AsyncIterator[InputEvent]:
        """Get keyboard events as they occur."""
        while self._running:
            try:
                event = await asyncio.wait_for(
                    self._event_queue.get(),
                    timeout=0.1
                )
                yield event
            except asyncio.TimeoutError:
                continue

    def _is_terminal(self) -> bool:
        try:
            return sys.stdin.isatty()
        except:
            return False

    async def _capture_loop(self) -> None:
        pass

    def _process_raw_data(self, raw_data: bytes) -> Optional[InputEvent]:
        pass


class LinuxAsyncKeyboardCapture(AsyncKeyboardCapture):
    """Linux/Unix implementation."""

    def __init__(self):
        super().__init__()
        self._terminal_state = TerminalState()
        self._stdin_fd = sys.stdin.fileno()

    async def _capture_loop(self) -> None:
        if not self._terminal_state.is_terminal():
            return
        if not self._terminal_state.enter_raw_mode():
            return

        loop = asyncio.get_event_loop()
        try:
            loop.add_reader(self._stdin_fd, self._on_stdin_ready)
            while self._running:
                await asyncio.sleep(0.1)
        except Exception as e:
            print(f"Error in Linux capture: {e}")
        finally:
            try:
                loop.remove_reader(self._stdin_fd)
            except:
                pass
            self._terminal_state.restore_mode()

    def _on_stdin_ready(self) -> None:
        try:
            raw_data = sys.stdin.read(1)
            if raw_data:
                event = self._process_raw_data(raw_data.encode())
                if event:
                    asyncio.create_task(self._emit_event(event))
        except Exception:
            pass

    def _process_raw_data(self, raw_data: bytes) -> Optional[InputEvent]:
        # Handle Enter
        if raw_data in (b'\r', b'\n'):
            return InputEvent(InputEventType.SPECIAL_KEY, "enter", time.time())
        # Handle Backspace
        elif raw_data == b'\x7f':
            return InputEvent(InputEventType.SPECIAL_KEY, "backspace", time.time())
        # Handle Ctrl+C
        elif raw_data == b'\x03':
            return InputEvent(InputEventType.INTERRUPT, "ctrl+c", time.time())
        # Normal Char
        else:
            try:
                char = raw_data.decode('utf-8')
                return InputEvent(InputEventType.CHARACTER, char, time.time())
            except:
                return None


class MacOSAsyncKeyboardCapture(LinuxAsyncKeyboardCapture):
    """MacOS implementation (reuses Linux logic for now as they are similar)."""
    pass


class WindowsAsyncKeyboardCapture(AsyncKeyboardCapture):
    """Windows implementation."""
    
    def __init__(self):
        super().__init__()
        
    async def _capture_loop(self) -> None:
        import msvcrt
        while self._running:
            if msvcrt.kbhit():
                # Read raw byte
                char = msvcrt.getch()
                event = self._process_raw_data(char)
                if event:
                    await self._emit_event(event)
            else:
                await asyncio.sleep(0.05)

    def _process_raw_data(self, raw_data: bytes) -> Optional[InputEvent]:
        if raw_data == b'\r':
            return InputEvent(InputEventType.SPECIAL_KEY, "enter", time.time())
        elif raw_data == b'\x08':
            return InputEvent(InputEventType.SPECIAL_KEY, "backspace", time.time())
        elif raw_data == b'\x03':
            return InputEvent(InputEventType.INTERRUPT, "ctrl+c", time.time())
        else:
            try:
                char = raw_data.decode('utf-8')
                return InputEvent(InputEventType.CHARACTER, char, time.time())
            except:
                return None


def create_keyboard_capture() -> AsyncKeyboardCapture:
    system = platform.system()
    if system == "Windows":
        return WindowsAsyncKeyboardCapture()
    elif system == "Darwin":
        return MacOSAsyncKeyboardCapture()
    else:
        return LinuxAsyncKeyboardCapture()
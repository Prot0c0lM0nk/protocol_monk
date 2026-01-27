"""
Async keyboard capture implementation for cross-platform non-blocking input.

This module provides a unified interface for capturing keyboard input asynchronously
across Linux, macOS, and Windows platforms.
"""

import asyncio
import platform
import sys
import termios
import tty
from abc import ABC, abstractmethod
from typing import AsyncIterator, Optional, Dict, Any, List
from dataclasses import dataclass
from enum import Enum

from .terminal_utils import TerminalState


class KeyType(Enum):
    """Types of keyboard events."""
    CHARACTER = "character"
    SPECIAL = "special"
    COMBINATION = "combination"
    SEQUENCE = "sequence"


@dataclass
class KeyEvent:
    """Represents a keyboard event."""
    key: str
    key_type: KeyType
    modifiers: List[str]
    timestamp: float
    raw_data: Optional[bytes] = None


class AsyncKeyboardCapture(ABC):
    """Abstract base class for async keyboard capture."""

    def __init__(self):
        self._running = False
        self._event_queue = asyncio.Queue()
        self._capture_task: Optional[asyncio.Task] = None

    def _is_terminal(self) -> bool:
        """Check if we're running in a terminal."""
        try:
            # Focus on input capability - stdin is what matters for keyboard capture
            # Many environments redirect stdout/stderr but still have functional stdin
            return sys.stdin.isatty()
        except:
            return False

    async def start_capture(self) -> None:
        """Start capturing keyboard events."""
        if self._running:
            return

        # Safety check: Only capture if we're in a terminal
        # Note: Platform-specific implementations will also check, so don't warn here
        if not self._is_terminal():
            return

        self._running = True
        self._capture_task = asyncio.create_task(self._capture_loop())

    async def stop_capture(self) -> None:
        """Stop capturing keyboard events."""
        self._running = False
        if self._capture_task:
            self._capture_task.cancel()
            try:
                await self._capture_task
            except asyncio.CancelledError:
                pass

    async def get_events(self) -> AsyncIterator[KeyEvent]:
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

    @abstractmethod
    async def _capture_loop(self) -> None:
        """Platform-specific capture loop."""
        pass

    @abstractmethod
    def _process_raw_data(self, raw_data: bytes) -> Optional[KeyEvent]:
        """Process raw keyboard data into KeyEvent."""
        pass

    async def _emit_event(self, event: KeyEvent) -> None:
        """Emit a keyboard event."""
        await self._event_queue.put(event)


class LinuxAsyncKeyboardCapture(AsyncKeyboardCapture):
    """Linux-specific async keyboard capture using termios and file descriptors."""

    def __init__(self):
        super().__init__()
        self._terminal_state = TerminalState()
        self._stdin_fd = sys.stdin.fileno()

    async def _capture_loop(self) -> None:
        """Linux capture loop using file descriptor monitoring."""
        # Safety: Only proceed if we have a proper terminal
        if not self._terminal_state.is_terminal():
            # Silently return - warning already handled by caller
            return

        # Enter raw mode safely
        if not self._terminal_state.enter_raw_mode():
            # Silently return - warning handled by TerminalState
            return

        try:
            # Get event loop and add reader
            loop = asyncio.get_event_loop()
            loop.add_reader(self._stdin_fd, self._on_stdin_ready)

            # Keep running until stopped
            while self._running:
                await asyncio.sleep(0.1)

        except Exception as e:
            print(f"Error in Linux keyboard capture: {e}")
        finally:
            # Remove reader
            try:
                loop.remove_reader(self._stdin_fd)
            except:
                pass

            # Always restore terminal state
            self._terminal_state.restore_mode()

    def _on_stdin_ready(self) -> None:
        """Handle stdin readiness."""
        try:
            # Read available data
            raw_data = sys.stdin.read(1)
            if raw_data:
                event = self._process_raw_data(raw_data.encode())
                if event:
                    asyncio.create_task(self._emit_event(event))
        except Exception as e:
            print(f"Error reading stdin: {e}")

    def _process_raw_data(self, raw_data: bytes) -> Optional[KeyEvent]:
        """Process raw Linux keyboard data."""
        import time

        # Handle escape sequences
        if raw_data == b'\x1b':
            # Start of escape sequence
            return self._handle_escape_sequence()
        elif raw_data == b'\r' or raw_data == b'\n':
            return KeyEvent(
                key="enter",
                key_type=KeyType.SPECIAL,
                modifiers=[],
                timestamp=time.time(),
                raw_data=raw_data
            )
        elif raw_data == b'\x7f':
            return KeyEvent(
                key="backspace",
                key_type=KeyType.SPECIAL,
                modifiers=[],
                timestamp=time.time(),
                raw_data=raw_data
            )
        elif raw_data == b'\t':
            return KeyEvent(
                key="tab",
                key_type=KeyType.SPECIAL,
                modifiers=[],
                timestamp=time.time(),
                raw_data=raw_data
            )
        elif raw_data == b'\x03':
            return KeyEvent(
                key="ctrl+c",
                key_type=KeyType.COMBINATION,
                modifiers=["ctrl"],
                timestamp=time.time(),
                raw_data=raw_data
            )
        elif raw_data[0] < 32 and raw_data[0] != 0:
            # Control character
            return KeyEvent(
                key=f"ctrl+{chr(raw_data[0] + 96)}",
                key_type=KeyType.COMBINATION,
                modifiers=["ctrl"],
                timestamp=time.time(),
                raw_data=raw_data
            )
        else:
            # Regular character
            return KeyEvent(
                key=raw_data.decode('utf-8', errors='ignore'),
                key_type=KeyType.CHARACTER,
                modifiers=[],
                timestamp=time.time(),
                raw_data=raw_data
            )

    def _handle_escape_sequence(self) -> Optional[KeyEvent]:
        """Handle escape sequences (arrow keys, function keys, etc.)."""
        import time

        # Try to read more characters for escape sequence
        try:
            # Use non-blocking read for escape sequence
            import select
            if select.select([sys.stdin], [], [], 0.1)[0]:
                seq = sys.stdin.read(2)
                if seq == '[A':
                    return KeyEvent("up", KeyType.SPECIAL, [], time.time())
                elif seq == '[B':
                    return KeyEvent("down", KeyType.SPECIAL, [], time.time())
                elif seq == '[C':
                    return KeyEvent("right", KeyType.SPECIAL, [], time.time())
                elif seq == '[D':
                    return KeyEvent("left", KeyType.SPECIAL, [], time.time())
                elif seq.startswith('[F'):
                    # Function key
                    return KeyEvent(f"f{seq[2:]}", KeyType.SPECIAL, [], time.time())
        except:
            pass

        # Just escape key
        return KeyEvent("escape", KeyType.SPECIAL, [], time.time())


class MacOSAsyncKeyboardCapture(AsyncKeyboardCapture):
    """macOS-specific async keyboard capture using safe termios approach."""

    def __init__(self):
        super().__init__()
        self._terminal_state = TerminalState()
        self._stdin_fd = sys.stdin.fileno()

    async def _capture_loop(self) -> None:
        """macOS capture loop using safe termios approach."""
        # Safety: Only proceed if we have a proper terminal
        if not self._terminal_state.is_terminal():
            # Silently return - warning already handled by caller
            return

        # Enter raw mode safely
        if not self._terminal_state.enter_raw_mode():
            # Silently return - warning handled by TerminalState
            return

        try:
            # Get event loop and add reader
            loop = asyncio.get_event_loop()
            loop.add_reader(self._stdin_fd, self._on_stdin_ready)

            # Keep running until stopped
            while self._running:
                await asyncio.sleep(0.1)

        except Exception as e:
            print(f"Error in macOS keyboard capture: {e}")
        finally:
            # Remove reader
            try:
                loop.remove_reader(self._stdin_fd)
            except:
                pass

            # Always restore terminal state
            self._terminal_state.restore_mode()

    def _on_stdin_ready(self) -> None:
        """Handle stdin readiness."""
        try:
            # Read available data
            raw_data = sys.stdin.read(1)
            if raw_data:
                event = self._process_raw_data(raw_data.encode())
                if event:
                    asyncio.create_task(self._emit_event(event))
        except Exception as e:
            print(f"Error reading stdin: {e}")

    def _process_raw_data(self, raw_data: bytes) -> Optional[KeyEvent]:
        """Process raw macOS keyboard data using termios."""
        import time

        # Handle escape sequences
        if raw_data == b'\x1b':
            # Start of escape sequence
            return self._handle_escape_sequence()
        elif raw_data == b'\r' or raw_data == b'\n':
            return KeyEvent(
                key="enter",
                key_type=KeyType.SPECIAL,
                modifiers=[],
                timestamp=time.time(),
                raw_data=raw_data
            )
        elif raw_data == b'\x7f':
            return KeyEvent(
                key="backspace",
                key_type=KeyType.SPECIAL,
                modifiers=[],
                timestamp=time.time(),
                raw_data=raw_data
            )
        elif raw_data == b'\t':
            return KeyEvent(
                key="tab",
                key_type=KeyType.SPECIAL,
                modifiers=[],
                timestamp=time.time(),
                raw_data=raw_data
            )
        elif raw_data == b'\x03':
            return KeyEvent(
                key="ctrl+c",
                key_type=KeyType.COMBINATION,
                modifiers=["ctrl"],
                timestamp=time.time(),
                raw_data=raw_data
            )
        elif raw_data[0] < 32 and raw_data[0] != 0:
            # Control character
            return KeyEvent(
                key=f"ctrl+{chr(raw_data[0] + 96)}",
                key_type=KeyType.COMBINATION,
                modifiers=["ctrl"],
                timestamp=time.time(),
                raw_data=raw_data
            )
        else:
            # Regular character
            return KeyEvent(
                key=raw_data.decode('utf-8', errors='ignore'),
                key_type=KeyType.CHARACTER,
                modifiers=[],
                timestamp=time.time(),
                raw_data=raw_data
            )

    def _handle_escape_sequence(self) -> Optional[KeyEvent]:
        """Handle escape sequences (arrow keys, function keys, etc.)."""
        import time

        # Try to read more characters for escape sequence
        try:
            # Use non-blocking read for escape sequence
            import select
            if select.select([sys.stdin], [], [], 0.1)[0]:
                seq = sys.stdin.read(2)
                if seq == '[A':
                    return KeyEvent("up", KeyType.SPECIAL, [], time.time())
                elif seq == '[B':
                    return KeyEvent("down", KeyType.SPECIAL, [], time.time())
                elif seq == '[C':
                    return KeyEvent("right", KeyType.SPECIAL, [], time.time())
                elif seq == '[D':
                    return KeyEvent("left", KeyType.SPECIAL, [], time.time())
                elif seq.startswith('[F'):
                    # Function key
                    return KeyEvent(f"f{seq[2:]}", KeyType.SPECIAL, [], time.time())
        except:
            pass

        # Just escape key
        return KeyEvent("escape", KeyType.SPECIAL, [], time.time())

class WindowsAsyncKeyboardCapture(AsyncKeyboardCapture):
    """Windows-specific async keyboard capture."""

    def __init__(self):
        super().__init__()
        self._hook = None

    async def _capture_loop(self) -> None:
        """Windows capture loop using Win32 API."""
        try:
            import win32con
            import win32api
            import win32gui

            # Define hook procedure
            def hook_procedure(nCode, wParam, lParam):
                if nCode >= 0 and wParam == win32con.WM_KEYDOWN:
                    # Extract key information
                    key_info = win32gui.GetKeyState(wParam)
                    key_event = self._process_key_info(wParam, lParam)

                    if key_event:
                        asyncio.create_task(self._emit_event(key_event))

                # Call next hook
                return win32gui.CallNextHookEx(self._hook, nCode, wParam, lParam)

            # Install hook
            self._hook = win32gui.SetWindowsHookEx(
                win32con.WH_KEYBOARD_LL,
                hook_procedure,
                win32api.GetModuleHandle(None),
                0
            )

            if not self._hook:
                print("Failed to install keyboard hook")
                return

            # Message loop
            while self._running:
                win32gui.PumpWaitingMessages()
                await asyncio.sleep(0.01)

        except ImportError:
            print("pywin32 not available. Using msvcrt fallback.")
            await self._msvcrt_fallback()
        except Exception as e:
            print(f"Error in Windows keyboard capture: {e}")
        finally:
            if self._hook:
                win32gui.UnhookWindowsHookEx(self._hook)

    async def _msvcrt_fallback(self) -> None:
        """Fallback using msvcrt for basic key capture."""
        import msvcrt
        import time

        while self._running:
            if msvcrt.kbhit():
                char = msvcrt.getch()
                event = self._process_raw_data(char)
                if event:
                    await self._emit_event(event)
            else:
                await asyncio.sleep(0.01)

    def _process_key_info(self, wParam: int, lParam: int) -> Optional[KeyEvent]:
        """Process Windows key information."""
        import time

        # Map virtual key codes
        vk_map = {
            13: ("enter", KeyType.SPECIAL),
            8: ("backspace", KeyType.SPECIAL),
            9: ("tab", KeyType.SPECIAL),
            27: ("escape", KeyType.SPECIAL),
            37: ("left", KeyType.SPECIAL),
            38: ("up", KeyType.SPECIAL),
            39: ("right", KeyType.SPECIAL),
            40: ("down", KeyType.SPECIAL),
        }

        if wParam in vk_map:
            key, key_type = vk_map[wParam]
            return KeyEvent(key, key_type, [], time.time())

        # Check for character keys
        if 65 <= wParam <= 90:  # A-Z
            # Check if shift is pressed
            import win32api
            shift_pressed = win32api.GetAsyncKeyState(win32con.VK_SHIFT) & 0x8000
            char = chr(wParam) if shift_pressed else chr(wParam + 32)
            return KeyEvent(char, KeyType.CHARACTER, [], time.time())

        return None

    def _process_raw_data(self, raw_data: bytes) -> Optional[KeyEvent]:
        """Process raw msvcrt data."""
        import time

        if raw_data == b'\r':
            return KeyEvent("enter", KeyType.SPECIAL, [], time.time())
        elif raw_data == b'\x08':
            return KeyEvent("backspace", KeyType.SPECIAL, [], time.time())
        elif raw_data == b'\t':
            return KeyEvent("tab", KeyType.SPECIAL, [], time.time())
        elif raw_data == b'\x1b':
            return KeyEvent("escape", KeyType.SPECIAL, [], time.time())
        elif raw_data[0] < 32:
            # Control character
            return KeyEvent(
                f"ctrl+{chr(raw_data[0] + 96)}",
                KeyType.COMBINATION,
                ["ctrl"],
                time.time(),
                raw_data
            )
        else:
            # Regular character
            return KeyEvent(
                raw_data.decode('utf-8', errors='ignore'),
                KeyType.CHARACTER,
                [],
                time.time(),
                raw_data
            )


def create_keyboard_capture() -> AsyncKeyboardCapture:
    """Factory function to create platform-appropriate keyboard capture."""
    system = platform.system()

    if system == "Linux":
        return LinuxAsyncKeyboardCapture()
    elif system == "Darwin":
        return MacOSAsyncKeyboardCapture()
    elif system == "Windows":
        return WindowsAsyncKeyboardCapture()
    else:
        # Fallback to Linux implementation
        print(f"Unsupported platform: {system}. Using Linux implementation.")
        return LinuxAsyncKeyboardCapture()


# Example usage
if __name__ == "__main__":
    async def main():
        capture = create_keyboard_capture()
        await capture.start_capture()

        print("Press keys (Ctrl+C to exit):")
        async for event in capture.get_events():
            print(f"Key: {event.key}, Type: {event.key_type}, Modifiers: {event.modifiers}")

            if event.key == "ctrl+c":
                break

        await capture.stop_capture()

    asyncio.run(main())
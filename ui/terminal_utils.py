"""
Terminal utility functions for safe terminal operations.
"""

import sys
import termios
import tty
from typing import Optional


class TerminalState:
    """Manages terminal state safely."""

    def __init__(self):
        self._original_settings: Optional[termios.struct_termios] = None
        self._in_raw_mode = False

    def is_terminal(self) -> bool:
        """Check if stdin is a terminal."""
        try:
            return sys.stdin.isatty() and sys.stdout.isatty()
        except:
            return False

    def enter_raw_mode(self) -> bool:
        """Enter raw mode safely."""
        if not self.is_terminal():
            return False

        try:
            # Save original settings
            self._original_settings = termios.tcgetattr(sys.stdin.fileno())

            # Set raw mode
            tty.setraw(sys.stdin.fileno())
            self._in_raw_mode = True
            return True
        except Exception as e:
            print(f"Warning: Could not enter raw mode: {e}")
            return False

    def restore_mode(self) -> None:
        """Restore original terminal mode."""
        if self._original_settings and self._in_raw_mode:
            try:
                termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, self._original_settings)
                self._in_raw_mode = False
            except Exception as e:
                print(f"Warning: Could not restore terminal mode: {e}")

    def __del__(self):
        """Ensure terminal is restored on cleanup."""
        self.restore_mode()


def safe_terminal_operation(func):
    """Decorator to ensure terminal operations are safe."""
    def wrapper(*args, **kwargs):
        if not sys.stdin.isatty():
            print("Warning: Terminal operation requested but not in a terminal.")
            return None
        try:
            return func(*args, **kwargs)
        except Exception as e:
            print(f"Terminal operation failed: {e}")
            return None
    return wrapper
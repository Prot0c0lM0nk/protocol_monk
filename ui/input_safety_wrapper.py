"""
Safety wrapper for input handling to ensure zero regression.

This module provides safety mechanisms that:
1. Check USE_ASYNC_INPUT flag before enabling async input
2. Use async input when enabled, traditional input otherwise
3. Ensure original functionality is preserved

Note: The previous fallback mechanism (using a new event loop in an executor)
has been removed as it was fundamentally broken and caused hangups.
"""

import sys
import asyncio
from typing import Optional, AsyncIterator
from config.static import settings
from .async_input_interface import InputEventType


class SafeInputManager:
    """
    Safety wrapper that manages input without broken fallback.

    This class ensures:
    - Zero regression by preserving original input methods
    - Feature flag controlled async input activation
    - Traditional input runs in main event loop (not in broken executor)
    """

    def __init__(self, ui_type: str = "plain"):
        self.ui_type = ui_type
        self._async_manager = None
        self._traditional_manager = None
        self._using_async = False

    def _is_terminal(self) -> bool:
        """Check if we're running in a terminal."""
        try:
            # Focus on input capability - stdin is what matters for keyboard capture
            # Many environments redirect stdout/stderr but still have functional stdin
            return sys.stdin.isatty()
        except:
            return False

    def _initialize_managers(self):
        """Initialize both async and traditional managers."""
        from .plain.input import InputManager as PlainInputManager

        # Initialize traditional manager (always available)
        if self.ui_type == "plain":
            self._traditional_manager = PlainInputManager()
        # Add other UI types as needed

        # Initialize async manager only if feature flag is enabled
        # AND we're in a terminal (security check)
        if settings.ui.use_async_input and self._is_terminal():
            try:
                from .async_input_interface import AsyncInputManager
                from .plain.async_input import PlainAsyncInput

                self._async_manager = AsyncInputManager()
                self._async_manager.register_capture(
                    "plain", PlainAsyncInput()
                )
            except Exception as e:
                # Log error but don't fail - safety first
                print(f"Warning: Failed to initialize async input: {e}")
                self._async_manager = None
        elif settings.ui.use_async_input:
            print("Warning: Async input requested but not in a terminal. Using traditional input.")
            self._async_manager = None

    async def read_input_safe(self, prompt_text: str = "", is_main_loop: bool = False) -> Optional[str]:
        """
        Read input with safety mechanisms.

        This method:
        1. Checks if async input is enabled and available
        2. Uses async input when enabled, traditional otherwise
        3. Ensures traditional input runs in main event loop (not in broken executor)

        Note: The broken fallback mechanism (new event loop in executor) has been removed.
        """
        # Initialize on first use
        if self._traditional_manager is None:
            self._initialize_managers()

        # Use async input if enabled and available
        if settings.ui.use_async_input and self._async_manager is not None:
            try:
                # Check if current capture is actually running (not just initialized)
                # This handles the case where capture was stopped after text submission
                current_capture = self._async_manager._current_capture
                print(f"[DEBUG] read_input_safe: current_capture={current_capture}, is_running={current_capture.is_running if current_capture else None}")
                if not current_capture or not current_capture.is_running:
                    print(f"[DEBUG] read_input_safe: Starting capture")
                    await self._async_manager.start_capture(self.ui_type)
                self._using_async = True

                # Read with timeout to prevent blocking
                print(f"[DEBUG] read_input_safe: Waiting for events...")
                async for event in self._async_manager.get_current_events():
                    print(f"[DEBUG] read_input_safe: Got event: {event.event_type}")
                    if event.event_type == InputEventType.TEXT_SUBMITTED:
                        return event.data
                    elif event.event_type == InputEventType.INTERRUPT:
                        return None

                # If we get here, no event was received
                print(f"[DEBUG] read_input_safe: No event received, returning None")
                return None

            except Exception as e:
                # Log error but don't fall back - the fallback is broken
                print(f"Async input error: {e}")
                return None

        # If async input not available, use traditional directly in main loop
        if self._traditional_manager:
            return await self._traditional_manager.read_input(prompt_text, is_main_loop)

        return None

    async def cleanup(self):
        """Cleanup resources."""
        if self._using_async and self._async_manager is not None:
            try:
                await self._async_manager.stop_all_captures()
            except Exception:
                pass
        self._using_async = False


def create_safe_input_manager(ui_type: str = "plain") -> SafeInputManager:
    """Factory function to create a safe input manager."""
    return SafeInputManager(ui_type)
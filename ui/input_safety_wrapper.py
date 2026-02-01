"""
Safety wrapper for input handling to ensure zero regression.

This module provides safety mechanisms that:
1. Check USE_ASYNC_INPUT flag before enabling async input
2. Use async input when enabled, traditional input otherwise
3. Ensure original functionality is preserved

Note: The previous fallback mechanism (using a new event loop in an executor)
has been removed as it was fundamentally broken and caused hangups.
"""

import logging
import sys
import logging
import sys
import asyncio
from typing import Optional, AsyncIterator
from config.static import settings
from .async_input_interface import InputEventType
from .async_prompts import AsyncPrompts

logger = logging.getLogger(__name__)


class SafeInputManager:
    """
    Safety wrapper that manages input without broken fallback.

    This class ensures:
    - Zero regression by preserving original input methods
    - Feature flag controlled async input activation
    - Traditional input runs in main event loop (not in broken executor)
    """

    def __init__(self, ui_type: str = "plain", lock: Optional[asyncio.Lock] = None):
        self.ui_type = ui_type
        self._lock = lock
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
                from .plain.async_input import PlainAsyncInputWithHistory

                # Create async manager and set up prompts
                self._async_manager = AsyncInputManager()
                plain_input = PlainAsyncInputWithHistory(lock=self._lock)
                plain_input.prompts = AsyncPrompts(self._async_manager)  # Set prompts reference
                self._async_manager.register_capture("plain", plain_input)
            except Exception as e:
                # Log error but don't fail - safety first
                print(f"Warning: Failed to initialize async input: {e}")
                self._async_manager = None
        elif settings.ui.use_async_input:
            print("Warning: Async input requested but not in a terminal. Using traditional input.")
            self._async_manager = None
            
    async def start_capture(self):
        """Initialize and start the async input capture."""
        if self._traditional_manager is None:
            self._initialize_managers()

        if settings.ui.use_async_input and self._async_manager is not None:
            await self._async_manager.start_capture(self.ui_type)
            self._using_async = True

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
                # Start capture if not already running
                if not self._using_async:
                    logger.debug("read_input_safe: Starting capture...")
                    await self.start_capture()

                # Display prompt before waiting for input
                await self.display_prompt()

                # Read with timeout to prevent blocking
                logger.debug("read_input_safe: Waiting for events...")
                async for event in self._async_manager.get_current_events():
                    logger.debug(f"read_input_safe: Got event: {event.event_type}")
                    if event.event_type == InputEventType.TEXT_SUBMITTED:
                        return event.data
                    elif event.event_type == InputEventType.INTERRUPT:
                        # On interrupt, we want to break the input loop.
                        # We need to signal this up to the main loop.
                        # Returning None is the established contract for this.
                        return None
            except Exception as e:
                # Log error but don't fall back - the fallback is broken
                logger.error(f"Async input error: {e}")
                return None

        # If async input not available, use traditional directly in main loop
        if self._traditional_manager:
            return await self._traditional_manager.read_input(prompt_text, is_main_loop)

        return None

    async def read_input(self, prompt_text: str = "", is_main_loop: bool = False) -> Optional[str]:
        """
        Read input - wrapper for compatibility with existing code.

        This provides the same interface as InputManager.read_input() but uses
        the async input mechanism when enabled.

        Args:
            prompt_text: The prompt text to display
            is_main_loop: Whether this is the main loop input (affects prompt style)

        Returns:
            The user's input, or None if interrupted
        """
        return await self.read_input_safe(prompt_text, is_main_loop)

    async def display_prompt(self):
        """Display the prompt for the current input method."""
        if self._using_async and self._async_manager:
            await self._async_manager.display_current_prompt()

    async def cleanup(self):
        """Cleanup resources."""
        if self._using_async and self._async_manager is not None:
            try:
                await self._async_manager.stop_all_captures()
            except Exception:
                pass
        self._using_async = False


def create_safe_input_manager(ui_type: str = "plain", lock: Optional[asyncio.Lock] = None) -> SafeInputManager:
    """Factory function to create a safe input manager."""
    return SafeInputManager(ui_type, lock=lock)
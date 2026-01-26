"""
Safety wrapper for input handling to ensure zero regression.

This module provides safety mechanisms that:
1. Check USE_ASYNC_INPUT flag before enabling async input
2. Provide fallback to traditional blocking input
3. Ensure original functionality is preserved
"""

import asyncio
from typing import Optional, AsyncIterator
from config.static import settings


class SafeInputManager:
    """
    Safety wrapper that manages input with fallback mechanisms.

    This class ensures:
    - Zero regression by preserving original input methods
    - Feature flag controlled async input activation
    - Automatic fallback on any failure
    """

    def __init__(self, ui_type: str = "plain"):
        self.ui_type = ui_type
        self._async_manager = None
        self._traditional_manager = None
        self._using_async = False

    def _initialize_managers(self):
        """Initialize both async and traditional managers."""
        from .plain.input import InputManager as PlainInputManager

        # Initialize traditional manager (always available)
        if self.ui_type == "plain":
            self._traditional_manager = PlainInputManager()
        # Add other UI types as needed

        # Initialize async manager only if feature flag is enabled
        if settings.ui.use_async_input:
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

    async def read_input_safe(self, prompt_text: str = "", is_main_loop: bool = False) -> Optional[str]:
        """
        Read input with safety mechanisms.

        This method:
        1. Checks if async input is enabled and available
        2. Falls back to traditional input if needed
        3. Ensures no blocking in async context
        """
        # Initialize on first use
        if self._traditional_manager is None:
            self._initialize_managers()

        # Try async input if enabled and available
        if settings.ui.use_async_input and self._async_manager is not None:
            try:
                # Get the current capture
                if not self._using_async:
                    await self._async_manager.start_capture(self.ui_type)
                    self._using_async = True

                # Read with timeout to prevent blocking
                async for event in self._async_manager.get_current_events():
                    if event.event_type == "text_submitted":
                        return event.data
                    elif event.event_type == "interrupt":
                        return None

                # If we get here, no event was received
                return None

            except Exception as e:
                # Fallback to traditional input on any error
                print(f"Async input failed, falling back: {e}")
                if settings.ui.async_input_fallback:
                    return await self._traditional_input(prompt_text, is_main_loop)
                return None

        # Use traditional input
        return await self._traditional_input(prompt_text, is_main_loop)

    async def _traditional_input(self, prompt_text: str, is_main_loop: bool) -> Optional[str]:
        """Use traditional blocking input in async-safe way."""
        if self._traditional_manager is None:
            return None

        # Run blocking input in executor to avoid blocking event loop
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            self._sync_traditional_input,
            prompt_text,
            is_main_loop
        )

    def _sync_traditional_input(self, prompt_text: str, is_main_loop: bool) -> Optional[str]:
        """Synchronous traditional input method."""
        try:
            # Import asyncio here to avoid issues
            import asyncio
            # For plain UI, we need to run the async method
            if hasattr(self._traditional_manager, 'read_input'):
                # Create new event loop for this thread
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    return loop.run_until_complete(
                        self._traditional_manager.read_input(prompt_text, is_main_loop)
                    )
                finally:
                    loop.close()
            return None
        except Exception as e:
            print(f"Traditional input error: {e}")
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
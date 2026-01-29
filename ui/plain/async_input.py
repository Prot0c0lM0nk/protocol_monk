"""
Async input implementation for Plain UI using keyboard capture.
"""

import asyncio
import logging
import sys
from typing import AsyncIterator, Optional, List
from dataclasses import dataclass
import time

from ..async_input_interface import AsyncInputInterface, InputEvent, InputEventType
from ..async_keyboard_capture import create_keyboard_capture, KeyEvent, KeyType

logger = logging.getLogger(__name__)


@dataclass
class InputBuffer:
    """Buffer for building input text."""
    text: str = ""
    cursor_pos: int = 0


class PlainAsyncInput(AsyncInputInterface):
    """Async input handler for Plain UI."""

    def __init__(self, prompt_text: str = "USER > "):
        super().__init__()
        self.prompt_text = prompt_text
        self._keyboard_capture = create_keyboard_capture()
        self._input_buffer = InputBuffer()
        self._capture_task: Optional[asyncio.Task] = None
        self._echo_enabled = True

    def _has_terminal_focus(self) -> bool:
        """Check if this terminal has focus."""
        # Simple check: verify stdin is a tty
        try:
            return sys.stdin.isatty()
        except:
            return False

    async def get_input_events(self) -> AsyncIterator[InputEvent]:
        """Get input events as they occur."""
        while self._running:
            try:
                event = await self._event_queue.get()
                yield event
            except asyncio.CancelledError:
                break

    async def start_capture(self) -> None:
        """Start async input capture."""
        if self._running:
            logger.debug("start_capture: Already running, returning early")
            return

        logger.debug(f"start_capture: Starting capture, _running={self._running}, keyboard_running={self._keyboard_capture.is_running}")
        self._running = True
        self._capture_task = asyncio.create_task(self._capture_loop())
        logger.debug("start_capture: Created capture task")

    async def stop_capture(self) -> None:
        """Stop async input capture."""
        logger.debug(f"stop_capture: Called, _running={self._running}")
        self._running = False

        if self._keyboard_capture.is_running:
            logger.debug("stop_capture: Stopping keyboard capture")
            await self._keyboard_capture.stop_capture()

        if self._capture_task:
            logger.debug("stop_capture: Cancelling capture task")
            self._capture_task.cancel()
            try:
                await self._capture_task
            except asyncio.CancelledError:
                pass
        logger.debug("stop_capture: Completed")

    async def _capture_loop(self) -> None:
        """Main capture loop with focus control."""
        # Safety: Only start capture when actively waiting for input
        logger.debug(f"_capture_loop: Starting, _running={self._running}")
        # Start keyboard capture
        await self._keyboard_capture.start_capture()

        # Display initial prompt
        self._display_prompt()
        logger.debug("_capture_loop: Prompt displayed, entering event loop")

        try:
            # Process keyboard events
            async for key_event in self._keyboard_capture.get_events():
                if not self._running:
                    break

                # Safety: Process only if we have terminal focus
                if self._has_terminal_focus():
                    # Process key event
                    input_event = self._process_key_event(key_event)
                    if input_event:
                        await self._emit_event(input_event)

                        # Handle special events
                        if input_event.event_type == InputEventType.TEXT_SUBMITTED:
                            # Instead of stopping, just reset buffer and prepare for next input
                            logger.debug("_capture_loop: TEXT_SUBMITTED, resetting for next input")
                            sys.stdout.write("\n")
                            sys.stdout.flush()
                            self._input_buffer = InputBuffer()
                            # Display a new prompt for the next input
                            self._display_prompt()
                        elif input_event.event_type == InputEventType.INTERRUPT:
                            # Handle Ctrl+C interrupt
                            had_text = bool(self._input_buffer.text.strip())

                            # Clear buffer
                            self._input_buffer = InputBuffer()
                            print("\r\033[K^C", flush=True)  # Clear line and show ^C

                            # Always show new prompt after interrupt
                            self._display_prompt()

                            # Note: The INTERRUPT event is already emitted above,
                            # so the event bus and UI listeners can handle it
                            # (e.g., for graceful shutdown on repeated Ctrl+C)
                # No need to log focus loss - it's normal behavior

        except Exception as e:
            print(f"\nError in input capture: {e}", flush=True)
        finally:
            logger.debug("_capture_loop: Finally block, stopping keyboard capture")
            await self._keyboard_capture.stop_capture()
            logger.debug("_capture_loop: Exiting")

    def _process_key_event(self, key_event: KeyEvent) -> Optional[InputEvent]:
        """Process a key event into an input event."""
        # Handle special keys
        if key_event.key_type == KeyType.SPECIAL:
            if key_event.key == "enter":
                # Submit current text
                text = self._input_buffer.text
                if text:
                    print(flush=True)  # New line after prompt
                    return InputEvent(
                        event_type=InputEventType.TEXT_SUBMITTED,
                        data=text,
                        timestamp=key_event.timestamp,
                        metadata={"cursor_pos": self._input_buffer.cursor_pos}
                    )
            elif key_event.key == "backspace":
                # Delete character
                if self._input_buffer.text and self._input_buffer.cursor_pos > 0:
                    pos = self._input_buffer.cursor_pos - 1
                    self._input_buffer.text = (
                        self._input_buffer.text[:pos] +
                        self._input_buffer.text[pos + 1:]
                    )
                    self._input_buffer.cursor_pos = pos
                    self._redisplay_input()
            # Handle Ctrl+C combinations
            elif key_event.key == "ctrl+c" or key_event.key_type == KeyType.COMBINATION and "ctrl" in key_event.modifiers and key_event.key.endswith("+c"):
                # Interrupt - emit event and clear buffer
                return InputEvent(
                    event_type=InputEventType.INTERRUPT,
                    data="",
                    timestamp=key_event.timestamp,
                    metadata={"signal": "SIGINT"}
                )
            elif key_event.key == "escape":
                # Clear input
                self._input_buffer = InputBuffer()
                self._redisplay_input()

        # Handle character input
        elif key_event.key_type == KeyType.CHARACTER:
            # Insert character at cursor position
            pos = self._input_buffer.cursor_pos
            self._input_buffer.text = (
                self._input_buffer.text[:pos] +
                key_event.key +
                self._input_buffer.text[pos:]
            )
            self._input_buffer.cursor_pos += 1
            self._redisplay_input()

        # Handle arrow keys for cursor movement
        elif key_event.key in ["left", "right"]:
            if key_event.key == "left" and self._input_buffer.cursor_pos > 0:
                self._input_buffer.cursor_pos -= 1
            elif key_event.key == "right" and self._input_buffer.cursor_pos < len(self._input_buffer.text):
                self._input_buffer.cursor_pos += 1

        return None

    def _display_prompt(self) -> None:
        """Display the input prompt."""
        # Clear line first (consistent with _redisplay_input to prevent ghost characters)
        sys.stdout.write("\r\033[K")
        # Display prompt and text
        sys.stdout.write(f"\r{self.prompt_text}{self._input_buffer.text}")
        self._position_cursor()
        sys.stdout.flush()

    def _redisplay_input(self) -> None:
        """Redisplay the current input."""
        # Clear current line and reposition at start
        sys.stdout.write("\r\033[K")
        # Display prompt and text
        sys.stdout.write(f"{self.prompt_text}{self._input_buffer.text}")
        self._position_cursor()
        sys.stdout.flush()

    def _position_cursor(self) -> None:
        """Position cursor at correct location."""
        # Calculate total position from start of line
        prompt_len = len(self.prompt_text)
        target_pos = prompt_len + self._input_buffer.cursor_pos

        # Move cursor to absolute column position (1-indexed)
        # First go to start of line, then move right
        if target_pos > 0:
            sys.stdout.write(f"\r\033[{target_pos}C")
        else:
            sys.stdout.write("\r")

    async def resume_capture_for_input(self) -> None:
        """DEPRECATED: Capture now runs continuously."""
        pass


class PlainAsyncInputWithHistory(PlainAsyncInput):
    """Async input with history support."""

    def __init__(self, prompt_text: str = "USER > ", history_size: int = 100):
        super().__init__(prompt_text)
        self.history: List[str] = []
        self.history_size = history_size
        self.history_index = -1
        self._saved_input = ""

    def _process_key_event(self, key_event: KeyEvent) -> Optional[InputEvent]:
        """Process key event with history navigation."""
        # Handle up/down for history
        if key_event.key == "up":
            self._navigate_history(-1)
            return None
        elif key_event.key == "down":
            self._navigate_history(1)
            return None

        # Let parent handle other keys
        result = super()._process_key_event(key_event)

        # Add to history on submit
        if result and result.event_type == InputEventType.TEXT_SUBMITTED:
            self._add_to_history(result.data)

        return result

    def _navigate_history(self, direction: int) -> None:
        """Navigate through command history."""
        if not self.history:
            return

        # Save current input if at end of history
        if self.history_index == -1 and direction == -1:
            self._saved_input = self._input_buffer.text

        # Calculate new index
        new_index = self.history_index + direction

        # Bounds check
        if new_index < -1:
            new_index = -1
        elif new_index >= len(self.history):
            new_index = len(self.history) - 1

        # Update if changed
        if new_index != self.history_index:
            self.history_index = new_index

            if self.history_index == -1:
                # Restore saved input
                self._input_buffer.text = self._saved_input
            else:
                # Load from history
                self._input_buffer.text = self.history[self.history_index]

            self._input_buffer.cursor_pos = len(self._input_buffer.text)
            self._redisplay_input()

    def _add_to_history(self, text: str) -> None:
        """Add text to history."""
        # Don't add empty lines or duplicates of last entry
        if text and (not self.history or self.history[-1] != text):
            self.history.append(text)

            # Trim history if too large
            if len(self.history) > self.history_size:
                self.history.pop(0)

        # Reset history navigation
        self.history_index = -1
        self._saved_input = ""


# Integration with Plain UI
class PlainUIAsyncAdapter:
    """Adapter to integrate async input with Plain UI."""

    def __init__(self, input_manager):
        self.input_manager = input_manager
        self.async_input = PlainAsyncInputWithHistory()
        self._input_future: Optional[asyncio.Future] = None

    async def get_input_async(self) -> Optional[str]:
        """Get input asynchronously."""
        # Capture is now started and managed externally.
        self._input_future = asyncio.Future()

        # Monitor events
        async def wait_for_input():
            async for event in self.async_input.get_input_events():
                if event.event_type == InputEventType.TEXT_SUBMITTED:
                    if not self._input_future.done():
                        self._input_future.set_result(event.data)
                    break
                elif event.event_type == InputEventType.INTERRUPT:
                    if not self._input_future.done():
                        self._input_future.set_result(None)
                    break

        # Start waiting
        wait_task = asyncio.create_task(wait_for_input())

        try:
            # Wait for input or cancellation
            result = await self._input_future
            return result
        finally:
            wait_task.cancel()
            try:
                await wait_task
            except asyncio.CancelledError:
                pass
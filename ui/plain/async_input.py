"""
Async input implementation for Plain UI using keyboard capture.
"""

import asyncio
import sys
from typing import AsyncIterator, Optional
from dataclasses import dataclass
import time

from ..async_input_interface import AsyncInputInterface, InputEvent, InputEventType
from ..async_keyboard_capture import create_keyboard_capture, KeyEvent, KeyType


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

    async def start_capture(self) -> None:
        """Start async input capture."""
        if self._running:
            return

        self._running = True
        self._capture_task = asyncio.create_task(self._capture_loop())

    async def stop_capture(self) -> None:
        """Stop async input capture."""
        self._running = False

        if self._keyboard_capture.is_running:
            await self._keyboard_capture.stop_capture()

        if self._capture_task:
            self._capture_task.cancel()
            try:
                await self._capture_task
            except asyncio.CancelledError:
                pass

    async def _capture_loop(self) -> None:
        """Main capture loop."""
        # Start keyboard capture
        await self._keyboard_capture.start_capture()

        # Display initial prompt
        self._display_prompt()

        try:
            # Process keyboard events
            async for key_event in self._keyboard_capture.get_events():
                if not self._running:
                    break

                # Process key event
                input_event = self._process_key_event(key_event)
                if input_event:
                    await self._emit_event(input_event)

                    # Handle special events
                    if input_event.event_type == InputEventType.TEXT_SUBMITTED:
                        # Reset buffer for next input
                        self._input_buffer = InputBuffer()
                        self._display_prompt()
                    elif input_event.event_type == InputEventType.INTERRUPT:
                        # Clear buffer and show new prompt
                        self._input_buffer = InputBuffer()
                        print("^C", flush=True)
                        self._display_prompt()

        except Exception as e:
            print(f"\nError in input capture: {e}", flush=True)
        finally:
            await self._keyboard_capture.stop_capture()

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
            elif key_event.key == "ctrl+c":
                # Interrupt
                return InputEvent(
                    event_type=InputEventType.INTERRUPT,
                    data="",
                    timestamp=key_event.timestamp
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
        sys.stdout.write(f"\r{self.prompt_text}{self._input_buffer.text}")
        self._position_cursor()
        sys.stdout.flush()

    def _redisplay_input(self) -> None:
        """Redisplay the current input."""
        # Clear current line
        sys.stdout.write("\r\033[K")
        # Display prompt and text
        sys.stdout.write(f"{self.prompt_text}{self._input_buffer.text}")
        self._position_cursor()
        sys.stdout.flush()

    def _position_cursor(self) -> None:
        """Position cursor at correct location."""
        # Move cursor to position after prompt
        prompt_len = len(self.prompt_text)
        cursor_pos = prompt_len + self._input_buffer.cursor_pos
        sys.stdout.write(f"\r\033[{cursor_pos + 1}G")


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
        # Start capture if not running
        if not self.async_input.is_running:
            await self.async_input.start_capture()

        # Wait for next text submission
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
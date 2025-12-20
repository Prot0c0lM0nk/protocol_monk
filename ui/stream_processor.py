import re
import sys
import asyncio
from enum import Enum
from typing import Tuple, Deque, Optional
from collections import deque


class StreamProcessorMode(Enum):
    TEXT = 1
    TOOL_DETECTED = 2


class StreamProcessor:
    # 50 chars gives us enough buffer to catch '{\n  "action":' across token splits
    SAFETY_MARGIN = 50
    # Bounded buffer constants to prevent memory exhaustion
    MAX_BUFFER_SIZE = 1_000_000  # 1MB max buffer
    MAX_SAFETY_MARGIN = 1000  # Max safety margin

    # Regex to catch { followed by whitespace/newlines and then "action"
    # This handles: {"action":...} AND { \n "action":... }
    TOOL_PATTERN = re.compile(r'\{\s*"action"')

    def __init__(self):
        self._lock: asyncio.Lock = asyncio.Lock()  # Thread safety for all operations
        self.buffer: Deque[str] = deque()  # Bounded buffer using deque
        self.buffer_size = 0  # Track current buffer size
        self.visible_text = ""
        self.tool_buffer = ""
        self.mode = StreamProcessorMode.TEXT
        self._buffer_limit_exceeded = False  # Track if we've hit the limit

    async def feed(self, chunk: str):
        """Append a chunk of data to the buffer with size checking. Thread-safe."""
        async with self._lock:
            # Check if adding this chunk would exceed our buffer limit
            if self.buffer_size + len(chunk) > self.MAX_BUFFER_SIZE:
                # Calculate how much we can safely add
                remaining_space = self.MAX_BUFFER_SIZE - self.buffer_size
                if remaining_space > 0:
                    # Add only what fits
                    self.buffer.append(chunk[:remaining_space])
                    self.buffer_size += remaining_space
                self._buffer_limit_exceeded = True
            else:
                # Normal case - add the full chunk
                self.buffer.append(chunk)
                self.buffer_size += len(chunk)

    async def tick(self):
        """Process the current state of the buffer (called every frame). Thread-safe."""
        try:
            async with self._lock:
                # 1. If we are already building a tool, shunt everything there.
                if self.mode == StreamProcessorMode.TOOL_DETECTED:
                    # Convert deque to string for tool buffer
                    buffer_content = "".join(self.buffer)
                    self.tool_buffer += buffer_content
                    self.buffer.clear()
                    self.buffer_size = 0
                    return

                # 2. Convert deque to string for regex search
                buffer_content = "".join(self.buffer)

                # 3. Regex Search for the start of a tool call
                match = self.TOOL_PATTERN.search(buffer_content)

                if match:
                    # FOUND IT!
                    start_index = match.start()

                    # Split buffer exactly at the start of the '{'
                    # Left side = Safe Text (The conversation)
                    # Right side = JSON Tool Call (The "Sacred Action")
                    safe_text = buffer_content[:start_index]

                    # Move safe text to visible, rest to tool buffer
                    self.visible_text += safe_text
                    self.tool_buffer += buffer_content[start_index:]

                    # Switch modes and clear buffer
                    self.mode = StreamProcessorMode.TOOL_DETECTED
                    self.buffer.clear()
                    self.buffer_size = 0

                else:
                    # 4. The Typewriter Logic - adapted for complete SDK-aligned chunks
                    # For complete chunks from aligned providers, we can release more aggressively
                    # since we're not dealing with partial JSON streaming artifacts

                    # If this is a complete chunk (from SDK-aligned providers),
                    # we can be less conservative with the safety margin
                    is_complete_chunk = (
                        len(buffer_content) < self.MAX_BUFFER_SIZE // 10
                    )  # Heuristic

                    if (
                        is_complete_chunk
                        and len(buffer_content) > self.SAFETY_MARGIN // 2
                    ):
                        # For complete chunks, use reduced safety margin
                        safe_len = len(buffer_content) - (self.SAFETY_MARGIN // 2)
                        self.visible_text += buffer_content[:safe_len]
                        await self._remove_from_buffer(safe_len)
                    elif len(buffer_content) > self.SAFETY_MARGIN:
                        # Original logic for potentially partial chunks
                        safe_len = len(buffer_content) - self.SAFETY_MARGIN
                        self.visible_text += buffer_content[:safe_len]
                        await self._remove_from_buffer(safe_len)
        except asyncio.CancelledError:
            # Handle cancellation gracefully - don't leave processor in inconsistent state
            # Just return without processing - let the cancellation propagate
            return  # Best effort - let the cancellation propagate

    async def _remove_from_buffer(self, chars_to_remove: int):
        try:
            async with self._lock:
                remaining = chars_to_remove
                while remaining > 0 and self.buffer:
                    # Get the first chunk
                    first_chunk = self.buffer[0]

                    if len(first_chunk) <= remaining:
                        # Remove entire chunk
                        self.buffer.popleft()
                        self.buffer_size -= len(first_chunk)
                        remaining -= len(first_chunk)
                    else:
                        # Remove partial chunk
                        self.buffer[0] = first_chunk[remaining:]
                        self.buffer_size -= remaining
                        remaining = 0
        except asyncio.CancelledError:
            # Handle cancellation gracefully - don't leave buffer in inconsistent state
            # Just reset the critical state without modifying buffer
            pass  # Best effort - let the cancellation propagate

    async def flush(self):
        """Force the remaining buffer into visible text (call on stream end). Thread-safe."""
        async with self._lock:
            # Only flush if we NEVER detected a tool.
            # If we are in TOOL_DETECTED mode, the buffer is part of the tool
            # and should be hidden (handled by the tool renderer), not printed as text.
            if self.mode == StreamProcessorMode.TEXT:
                buffer_content = "".join(self.buffer)
                self.visible_text += buffer_content
                self.buffer.clear()
                self.buffer_size = 0

    def get_view_data(self) -> Tuple[str, bool, int]:
        """Return the text to display, tool mode status, and tool data byte count."""
        return (
            self.visible_text,
            self.mode == StreamProcessorMode.TOOL_DETECTED,
            len(self.tool_buffer),
        )

    def close(self):
        """Clean up any streaming resources."""
        # Force release any locked state by acquiring and immediately releasing
        try:
            # Use a short timeout to avoid hanging if lock is held
            if self._lock.locked():
                # If locked, we can't safely clean up from another thread
                # Just clear what we can without the lock
                self.visible_text = ""
                self.tool_buffer = ""
                self._buffer_limit_exceeded = False
                return

            # If not locked, we can safely clean up everything
            self.buffer.clear()
            self.visible_text = ""
            self.tool_buffer = ""
            self.buffer_size = 0
            self.mode = StreamProcessorMode.TEXT
            self._buffer_limit_exceeded = False
        except Exception:
            # Even if something goes wrong, try to reset critical state
            self.visible_text = ""
            self.tool_buffer = ""
            self._buffer_limit_exceeded = False

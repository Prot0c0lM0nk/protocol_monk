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
    MAX_SAFETY_MARGIN = 1000     # Max safety margin

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
        async with self._lock:
            # 1. If we are already building a tool, shunt everything there.
            if self.mode == StreamProcessorMode.TOOL_DETECTED:
                # Convert deque to string for tool buffer
                buffer_content = ''.join(self.buffer)
                self.tool_buffer += buffer_content
                self.buffer.clear()
                self.buffer_size = 0
                return

            # 2. Convert deque to string for regex search
            buffer_content = ''.join(self.buffer)
            
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
                # 4. The Typewriter Logic - adapted for deque
                # We must hold back enough text (SAFETY_MARGIN) to ensure we don't
                # accidentally print a partial '{' that turns out to be a tool call later.
                
                if len(buffer_content) > self.SAFETY_MARGIN:
                    # Calculate how much we can safely reveal
                    # We keep the last SAFETY_MARGIN chars in the buffer just in case
                    safe_len = len(buffer_content) - self.SAFETY_MARGIN
                    
                    # Add the safe portion to visible text
                    self.visible_text += buffer_content[:safe_len]
                    
                    # Remove the processed portion from deque
                    await self._remove_from_buffer(safe_len)
    async def _remove_from_buffer(self, chars_to_remove: int):
        """Remove characters from the front of the deque buffer. Thread-safe."""
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
    async def flush(self):
        """Force the remaining buffer into visible text (call on stream end). Thread-safe."""
        async with self._lock:
            # Only flush if we NEVER detected a tool.
            # If we are in TOOL_DETECTED mode, the buffer is part of the tool
            # and should be hidden (handled by the tool renderer), not printed as text.
            if self.mode == StreamProcessorMode.TEXT:
                buffer_content = ''.join(self.buffer)
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

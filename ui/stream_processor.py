import re
from enum import Enum
from typing import Tuple


class StreamProcessorMode(Enum):
    TEXT = 1
    TOOL_DETECTED = 2


class StreamProcessor:
    # 50 chars gives us enough buffer to catch '{\n  "action":' across token splits
    SAFETY_MARGIN = 50

    # Regex to catch { followed by whitespace/newlines and then "action"
    # This handles: {"action":...} AND { \n "action":... }
    TOOL_PATTERN = re.compile(r'\{\s*"action"')

    def __init__(self):
        self.buffer = ""
        self.visible_text = ""
        self.tool_buffer = ""
        self.mode = StreamProcessorMode.TEXT

    def feed(self, chunk: str):
        """Append a chunk of data to the buffer."""
        self.buffer += chunk

    def tick(self):
        """Process the current state of the buffer (called every frame)."""
        # 1. If we are already building a tool, shunt everything there.
        if self.mode == StreamProcessorMode.TOOL_DETECTED:
            self.tool_buffer += self.buffer
            self.buffer = ""
            return

        # 2. Regex Search for the start of a tool call
        match = self.TOOL_PATTERN.search(self.buffer)

        if match:
            # FOUND IT!
            start_index = match.start()

            # Split buffer exactly at the start of the '{'
            # Left side = Safe Text (The conversation)
            # Right side = JSON Tool Call (The "Sacred Action")
            safe_text = self.buffer[:start_index]

            # Move safe text to visible, rest to tool buffer
            self.visible_text += safe_text
            self.tool_buffer += self.buffer[start_index:]

            # Switch modes
            self.mode = StreamProcessorMode.TOOL_DETECTED
            self.buffer = ""

        else:
            # 3. The Typewriter Logic
            # We must hold back enough text (SAFETY_MARGIN) to ensure we don't
            # accidentally print a partial '{' that turns out to be a tool call later.

            if len(self.buffer) > self.SAFETY_MARGIN:
                # Calculate how much we can safely reveal
                # We keep the last SAFETY_MARGIN chars in the buffer just in case
                safe_len = len(self.buffer) - self.SAFETY_MARGIN

                self.visible_text += self.buffer[:safe_len]
                self.buffer = self.buffer[safe_len:]

    def flush(self):
        """Force the remaining buffer into visible text (call on stream end)."""
        # Only flush if we NEVER detected a tool.
        # If we are in TOOL_DETECTED mode, the buffer is part of the tool
        # and should be hidden (handled by the tool renderer), not printed as text.
        if self.mode == StreamProcessorMode.TEXT:
            self.visible_text += self.buffer
            self.buffer = ""

    def get_view_data(self) -> Tuple[str, bool, int]:
        """Return the text to display, tool mode status, and tool data byte count."""
        return (
            self.visible_text,
            self.mode == StreamProcessorMode.TOOL_DETECTED,
            len(self.tool_buffer),
        )

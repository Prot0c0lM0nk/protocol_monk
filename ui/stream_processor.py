from enum import Enum
from typing import Tuple

class StreamProcessorMode(Enum):
    TEXT = 1
    TOOL_DETECTED = 2

class StreamProcessor:
    SAFETY_MARGIN = 25
    TOOL_SIGNATURE = '{"action":'

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

        # 2. Lookahead scan for the TOOL_SIGNATURE
        signature_index = self.buffer.find(self.TOOL_SIGNATURE)
        
        if signature_index != -1:
            # FOUND IT! 
            # Split buffer exactly at the start of the signature.
            # Left side = Safe Text
            # Right side (inclusive) = JSON Tool Call
            safe_text = self.buffer[:signature_index]
            
            # Move safe text to visible, rest to tool buffer
            self.visible_text += safe_text
            self.tool_buffer += self.buffer[signature_index:]
            
            # Switch modes
            self.mode = StreamProcessorMode.TOOL_DETECTED
            self.buffer = ""
            
        else:
            # 3. The Typewriter Logic
            # Only move text if we have enough to satisfy the safety margin
            if len(self.buffer) > self.SAFETY_MARGIN:
                # Calculate how much we can safely reveal
                # e.g. Buffer 30 chars, Margin 25 -> Reveal top 5 chars
                safe_len = len(self.buffer) - self.SAFETY_MARGIN
                
                self.visible_text += self.buffer[:safe_len]
                self.buffer = self.buffer[safe_len:]

    def flush(self):
        """Force the remaining buffer into visible text (call on stream end)."""
        if self.mode == StreamProcessorMode.TEXT:
            self.visible_text += self.buffer
            self.buffer = ""

    def get_view_data(self) -> Tuple[str, bool, int]:
        """Return the text to display, tool mode status, and tool data byte count."""
        return (self.visible_text, self.mode == StreamProcessorMode.TOOL_DETECTED, len(self.tool_buffer))
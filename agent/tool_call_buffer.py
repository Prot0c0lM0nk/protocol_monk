"""
Tool Call Buffering for Streaming Responses

This module handles the detection and buffering of JSON tool calls in streaming responses
to prevent incomplete JSON parsing when tool calls are split across multiple chunks.
"""

import json
import logging
from typing import Tuple, Optional, List, Dict, Any

logger = logging.getLogger(__name__)


class ToolCallBuffer:
    """
    Buffers streaming content to detect and collect complete JSON tool calls.

    When a tool call is detected (starting with ```json or [{), this buffer
    collects chunks until the complete JSON is available, then yields it as
    a single unit for proper parsing.
    """

    def __init__(self):
        self.buffer = ""
        self.is_collecting_tool = False
        self.tool_start_markers = ["```json", "[{", '[ {"']

        self.brace_count = 0
        self.in_string = False
        self.escape_next = False

    def add_chunk(self, chunk: str) -> Tuple[List[str], bool]:
        """
        Add a chunk and return any complete content/tool calls.

        Returns:
            Tuple of (list of content pieces, bool indicating if tool call was completed)
        """
        completed_tools = False
        output_chunks = []

        # Add to buffer
        self.buffer += chunk

        # Check if we should start collecting a tool call
        if not self.is_collecting_tool:
            self._check_for_tool_start()

        # If we're collecting a tool call, try to find its end
        if self.is_collecting_tool:
            complete_json = self._check_for_complete_json()
            if complete_json:
                # Found complete tool call - yield it as one chunk
                output_chunks.append(complete_json)
                self._reset_buffer()
                completed_tools = True
            else:
                # Still collecting - don't yield anything yet
                pass
        else:
            # Not collecting a tool - yield regular content
            # Find the last complete thought/sentence if possible
            last_complete = self._find_last_complete_segment()
            if last_complete:
                output_chunks.append(last_complete)
                self.buffer = self.buffer[len(last_complete) :]

        return output_chunks, completed_tools

    def _check_for_tool_start(self):
        """Check if buffer contains the start of a tool call."""
        buffer_stripped = self.buffer.strip()
        for marker in self.tool_start_markers:
            if marker in buffer_stripped:
                self.is_collecting_tool = True
                logger.debug("Detected tool call start with marker: %s", marker)
                break

    def _check_for_complete_json(self) -> Optional[str]:
        """
        Check if buffer contains complete JSON by counting braces.
        Returns the complete JSON if found, None otherwise.
        """
        # Reset counters
        self.brace_count = 0
        self.in_string = False
        self.escape_next = False

        # Handle ```json blocks
        if "```json" in self.buffer:
            return self._check_json_fence_complete()

        # Handle raw JSON arrays
        return self._check_bracket_balance()

    def _check_json_fence_complete(self) -> Optional[str]:
        """Check for complete ```json ... ``` block."""
        start_fence = "```json"
        end_fence = "```"

        start_idx = self.buffer.find(start_fence)
        if start_idx == -1:
            return None

        # Find content after start fence
        content_start = start_idx + len(start_fence)
        content = self.buffer[content_start:]

        # Look for end fence
        end_idx = content.find(end_fence)
        if end_idx == -1:
            return None

        # Extract complete JSON
        json_content = content[:end_idx].strip()
        full_block = self.buffer[start_idx : content_start + end_idx + len(end_fence)]

        # Verify it's valid JSON
        try:
            json.loads(json_content)
            return full_block
        except json.JSONDecodeError:
            logger.debug("Found JSON fence but content is invalid JSON")
            return None

    def _check_bracket_balance(self) -> Optional[str]:
        """Check for balanced brackets in JSON array."""
        # Find start of JSON array
        start_idx = -1
        for i, char in enumerate(self.buffer):
            if char == "[":
                start_idx = i
                break

        if start_idx == -1:
            return None

        # Count brackets to find balance
        bracket_count = 0
        in_string = False
        escape_next = False

        for i in range(start_idx, len(self.buffer)):
            char = self.buffer[i]

            if escape_next:
                escape_next = False
                continue

            if char == "\\\\":
                escape_next = True
                continue

            if char == '"' and not in_string:
                in_string = True
            elif char == '"' and in_string:
                in_string = False
            elif not in_string:
                if char == "[":
                    bracket_count += 1
                elif char == "]":
                    bracket_count -= 1

                if bracket_count == 0:
                    # Found complete JSON array
                    json_content = self.buffer[start_idx : i + 1]
                    try:
                        json.loads(json_content)
                        return json_content
                    except json.JSONDecodeError:
                        logger.debug(
                            "Bracket balance found but invalid JSON: %s", json_content
                        )
                        return None
        return None

    def _find_last_complete_segment(self) -> Optional[str]:
        """Find the last complete sentence or thought in non-tool content."""
        # Simple approach: yield up to last sentence boundary
        sentences = self.buffer.split(". ")
        if len(sentences) > 1:
            # Return all but the last sentence (which might be incomplete)
            complete_part = ". ".join(sentences[:-1]) + "."
            return complete_part

        # If no complete sentences, return empty to keep buffering
        return None

    def _reset_buffer(self):
        """Reset buffer state after completing a tool call."""
        self.buffer = ""
        self.is_collecting_tool = False
        self.brace_count = 0
        self.in_string = False
        self.escape_next = False

    def flush(self) -> List[str]:
        """
        Flush any remaining content in the buffer.

        Returns:
            List of remaining content chunks
        """
        remaining = []

        if self.buffer.strip():
            if self.is_collecting_tool:
                # Incomplete tool call - yield as regular text
                logger.warning("Incomplete tool call flushed: %s", self.buffer)
                remaining.append(self.buffer)
            else:
                # Regular content
                remaining.append(self.buffer)

        self._reset_buffer()
        return remaining

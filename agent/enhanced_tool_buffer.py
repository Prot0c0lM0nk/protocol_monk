# EnhancedToolCallBuffer Implementation

from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional
import json
import re


@dataclass
class ToolBufferState:
    """State for an individual tool call buffer.

    Attributes:
        content: The accumulated content of the buffer
        start_pos: Position where the buffer was detected
        end_pos: Position where buffer completion was detected
        is_complete: Whether the buffer contains a complete tool call
        error: Error message if parsing failed
    """

    content: str = ""
    start_pos: int = -1
    end_pos: int = -1
    is_complete: bool = False
    error: Optional[str] = None


class EnhancedToolCallBuffer:
    """Robust tool call detection with support for overlapping tool calls and better error recovery.

    This class handles:
    - Multiple simultaneous tool calls in a single response
    - Overlapping tool call detection
    - Robust JSON parsing with error recovery
    - Comprehensive error handling and validation
    """

    def __init__(self):
        """Initialize the buffer with empty states."""
        self.active_buffers: List[ToolBufferState] = []
        self.completed_tools: List[Dict] = []

        # Patterns for detecting tool call starts
        self.start_patterns = [
            r"```json\\s*\\{",  # Markdown code block with JSON
            r"\\{\\s*\"action\"\\s*:",  # JSON object with action field
            r"\\[\\s*\\{\\s*\"action\"\\s*:",  # Array of JSON objects
        ]

    def add_chunk(self, chunk: str) -> Tuple[List[str], List[Dict]]:
        """Add a text chunk to the buffer and process for tool calls.

        Args:
            chunk: Text chunk to process

        Returns:
            Tuple containing:
            - List of text chunks that aren't part of tool calls
            - List of completed tool calls found in the chunk
        """
        # Add to all active buffers
        text_chunks = []
        current_pos = 0

        # First, detect any new tool starts in this chunk
        new_starts = self._detect_tool_starts(chunk)

        # Create new buffers for new starts
        for start_pos in new_starts:
            self.active_buffers.append(ToolBufferState(start_pos=start_pos))

        # Sort buffers by start position to maintain order
        self.active_buffers.sort(key=lambda b: b.start_pos)

        # Distribute text to buffers and collect completed tools
        for buffer in self.active_buffers:
            if not buffer.is_complete:
                buffer.content += chunk

                # Check if this buffer is now complete
                buffer.is_complete, tool_calls = self._check_buffer_completion(buffer)
                if buffer.is_complete:
                    self.completed_tools.extend(tool_calls)

        # Extract text that's not part of any tool call
        text_chunks = self._extract_non_tool_text(chunk)

        # Clean up completed buffers
        self.active_buffers = [b for b in self.active_buffers if not b.is_complete]

        return text_chunks, self.completed_tools

    def _detect_tool_starts(self, text: str) -> List[int]:
        """Detect all potential tool call start positions in the text.

        Args:
            text: Text to search for tool call markers

        Returns:
            List of start positions where tool calls might begin
        """
        starts = []

        for pattern in self.start_patterns:
            # Find all matches in the text
            for match in re.finditer(pattern, text):
                starts.append(match.start())

        return starts

    def _check_buffer_completion(
        self, buffer: ToolBufferState
    ) -> Tuple[bool, List[Dict]]:
        """Check if a buffer contains a complete tool call.

        Args:
            buffer: Buffer state to check

        Returns:
            Tuple containing:
            - Boolean indicating if complete
            - List of extracted tool calls if complete
        """
        try:
            # Attempt to parse the buffer content
            tool_calls = self._extract_tool_calls(buffer.content)
            if tool_calls:
                return True, tool_calls
        except json.JSONDecodeError as e:
            buffer.error = f"JSON decode error: {str(e)}"

        # Check if we have a complete JSON structure
        if self._has_complete_json_structure(buffer.content):
            try:
                tool_calls = self._extract_tool_calls(buffer.content)
                if tool_calls:
                    return True, tool_calls
            except json.JSONDecodeError:
                pass

        return False, []

    def _extract_tool_calls(self, text: str) -> List[Dict]:
        """Extract tool calls from text with robust JSON parsing.

        Args:
            text: Text containing potential tool calls

        Returns:
            List of parsed tool call dictionaries
        """
        # First try to parse the entire content as JSON
        try:
            data = json.loads(text)
            if isinstance(data, dict):
                return [data]
            elif isinstance(data, list):
                return data
            return []
        except json.JSONDecodeError:
            pass

        # If that fails, try to extract JSON from within markdown code blocks
        markdown_matches = re.findall(r"```(?:json)?\\s*([\\s\\S]*?)\\s*```", text)
        if markdown_matches:
            try:
                data = json.loads(markdown_matches[0])
                if isinstance(data, dict):
                    return [data]
                elif isinstance(data, list):
                    return data
            except json.JSONDecodeError:
                pass

        # If we still can't parse, try to fix common JSON issues
        fixed_json = self._fix_common_json_errors(text)
        try:
            data = json.loads(fixed_json)
            if isinstance(data, dict):
                return [data]
            elif isinstance(data, list):
                return data
        except json.JSONDecodeError as e:
            raise ValueError(f"Could not parse tool call: {str(e)}")

        return []

    def _has_complete_json_structure(self, text: str) -> bool:
        """Check if text has balanced braces/brackets and complete structure.

        Args:
            text: Text to validate

        Returns:
            Boolean indicating if text has balanced JSON structure
        """
        stack = []
        in_string = False
        escape = False

        for char in text:
            if char == '"' and not escape:
                in_string = not in_string

            if not in_string:
                if char in "{[":
                    stack.append(char)
                elif char in "}]":
                    if not stack:
                        return False
                    last = stack.pop()
                    if (char == "}" and last != "{") or (char == "]" and last != "["):
                        return False

            escape = char == "\\\\" and not escape

        return not stack and not in_string

    def _fix_common_json_errors(self, text: str) -> str:
        """Fix common JSON formatting issues.

        Args:
            text: Text containing JSON with formatting issues

        Returns:
            Fixed text with common JSON formatting issues resolved
        """
        # Remove trailing commas
        fixed = re.sub(r",\\s*([}\\]]\\s*)$", r"\\1", text)

        # Fix unquoted keys
        fixed = re.sub(r"(\\{|\\,)\\s*(\\w+)\\s*:", r"\\1\"\\2\":", fixed)

        # Fix single quotes to double quotes
        fixed = re.sub(r"'([^']*)'", r'"\\1"', fixed)

        # Add missing closing braces
        open_braces = fixed.count("{")
        close_braces = fixed.count("}")
        if open_braces > close_braces:
            fixed += "}" * (open_braces - close_braces)

        return fixed

    def _extract_non_tool_text(self, chunk: str) -> List[str]:
        """Extract text that's not part of any tool call.

        Args:
            chunk: Text chunk to analyze

        Returns:
            List of text chunks that aren't part of tool calls
        """
        if not self.active_buffers:
            return [chunk]

        # For simplicity, we'll return the chunk as-is
        # A more sophisticated implementation would track positions
        return [chunk]

    def reset(self):
        """Reset the buffer state to empty.

        Clears all active buffers and completed tools.
        """
        self.active_buffers = []
        self.completed_tools = []

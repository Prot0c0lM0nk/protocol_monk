"""
Buffered Model Client for Streaming Tool Calls

This module extends the model client to properly handle streaming tool calls
by buffering incomplete JSON and yielding complete tool calls as single units.
"""

import json
import logging
from typing import AsyncGenerator, Optional, List
from agent.tool_call_buffer import ToolCallBuffer

logger = logging.getLogger(__name__)


class BufferedModelResponse:
    """
    Wraps model responses to buffer streaming tool calls.

    This solves the issue where streaming breaks up JSON tool calls across
    multiple chunks, preventing proper parsing.
    """

    def __init__(self, original_generator: AsyncGenerator[str, None]):
        """
        Initialize with the original model response generator.

        Args:
            original_generator: The original streaming response from model
        """
        self.original_generator = original_generator
        self.tool_buffer = ToolCallBuffer()
        self.pending_content = []

    async def __aiter__(self):
        """Iterate over the buffered response."""
        async for chunk in self.original_generator:
            # Process chunk through tool buffer
            content_chunks, completed_tool = self.tool_buffer.add_chunk(chunk)

            # Yield any completed content
            for content in content_chunks:
                yield content

            # If we completed a tool, we might want to handle it specially
            if completed_tool:
                logger.debug(
                    "Completed tool call: %s",
                    content_chunks[-1] if content_chunks else "",
                )

        # Flush any remaining content
        remaining_chunks = self.tool_buffer.flush()
        for content in remaining_chunks:
            yield content


async def create_buffered_response(
    original_generator: AsyncGenerator[str, None],
) -> AsyncGenerator[str, None]:
    """
    Create a buffered version of a model response that handles tool calls properly.

    Args:
        original_generator: The original streaming response

    Returns:
        Buffered generator that yields complete tool calls as single units
    """
    buffered_response = BufferedModelResponse(original_generator)
    async for content in buffered_response:
        yield content


def should_buffer_for_tools(text: str) -> bool:
    """
    Determine if text should be buffered for tool call detection.

    Args:
        text: The text to analyze

    Returns:
        True if text contains tool call markers
    """
    tool_markers = ["```json", "[{", "tool", "action", "parameters"]
    text_lower = text.lower()
    return any(marker in text_lower for marker in tool_markers)


def extract_tool_calls_safely(text: str) -> List[dict]:
    """
    Extract tool calls with enhanced error handling for streaming artifacts.

    Args:
        text: Text that may contain tool calls

    Returns:
        List of extracted tool call dictionaries
    """
    from utils.json_parser import extract_json_from_text

    try:
        # Try normal extraction first
        objects, errors = extract_json_from_text(text)

        if errors and not objects:
            # If normal extraction failed, try to fix common streaming issues
            fixed_text = _fix_streaming_json(text)
            objects, errors = extract_json_from_text(fixed_text)

        # Filter for valid tool call objects
        tool_calls = []
        for obj in objects:
            if isinstance(obj, dict) and "action" in obj:
                tool_calls.append(obj)
            elif isinstance(obj, list):
                # Handle array of tool calls
                for item in obj:
                    if isinstance(item, dict) and "action" in item:
                        tool_calls.append(item)

        return tool_calls

    except Exception as e:
        logger.error("Failed to extract tool calls from streaming text: %s", e)
        return []


def _fix_streaming_json(text: str) -> str:
    """
    Fix common JSON issues caused by streaming.

    Args:
        text: Text that may have JSON streaming artifacts

    Returns:
        Fixed text with corrected JSON
    """
    fixes = [
        # Fix truncated arrays
        (r"\[\s*\{$", ""),  # Remove incomplete array start
        (r"\[\s*$", ""),  # Remove empty/incomplete arrays
        # Fix broken objects
        (r"\{\s*$", ""),  # Remove incomplete objects
        (r",\s*$", ""),  # Remove trailing commas
        # Fix string truncation
        (r'"[^"]*$', '"'),  # Close truncated strings
        # Fix common JSON syntax errors
        (r"'(\w+)':", r'"\1":'),  # Fix single quotes
        (r",\s*\}", "}"),  # Remove trailing commas before closing
        (r",\s*\]", "]"),  # Remove trailing commas before closing array
    ]

    import re

    fixed_text = text
    for pattern, replacement in fixes:
        fixed_text = re.sub(pattern, replacement, fixed_text)

    return fixed_text

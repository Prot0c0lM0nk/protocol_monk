"""
JSON Parsing Utilities.

This module provides robust JSON extraction capabilities, capable of handling
Markdown code fences and raw JSON objects embedded in text. It uses a
dual-strategy approach (Regex Fencing + Bracket Counting) to maximize
extraction success rates from LLM outputs.
"""

import json
import logging
import re
from typing import Any, Dict, List, Tuple

from utils.exceptions import JsonParsingError

logger = logging.getLogger(__name__)


def extract_json_from_text(
    text: str,
) -> Tuple[List[Dict[str, Any]], List[JsonParsingError]]:
    """
    Robustly extracts JSON objects with detailed error tracking.

    Strategies:
    1. STRICT FENCING: Looks for ```json ... ``` blocks first.
    2. FALLBACK: Looks for raw JSON objects if no fences are found.

    Returns:
        Tuple of (successful_objects, parsing_errors)
    """
    # Strategy 1: Markdown Code Blocks (Preferred)
    objects, errors = _extract_by_fencing(text)
    if objects or errors:
        return objects, errors

    # Strategy 2: Bracket Counting (Fallback)
    parser = _BracketParser(text)
    return parser.parse()


def _extract_by_fencing(
    text: str,
) -> Tuple[List[Dict[str, Any]], List[JsonParsingError]]:
    """Attempt to extract JSON from Markdown code blocks."""
    json_objects = []
    parsing_errors = []

    fence_pattern = r"```json\s*([\s\S]*?)\s*```"
    matches = re.findall(fence_pattern, text, re.DOTALL)

    for match in matches:
        try:
            obj = json.loads(match)
            if isinstance(obj, (dict, list)):
                json_objects.append(obj)
        except json.JSONDecodeError as e:
            error = JsonParsingError(
                f"Failed to parse fenced JSON: {e}", original_error=e
            )
            parsing_errors.append(error)
            logger.warning("Failed to parse fenced JSON: %s", e)

    return json_objects, parsing_errors


class _BracketParser:
    """
    Helper class for stateful bracket counting parsing.
    Encapsulates state to avoid passing 7+ arguments between functions.
    """

    # pylint: disable=too-few-public-methods

    def __init__(self, text: str):
        self.text = text
        self.objects: List[Any] = []
        self.errors: List[JsonParsingError] = []
        self._stack: List[str] = []
        self._start_indices: List[int] = []
        self._in_string = False
        self._escape = False

    def parse(self) -> Tuple[List[Dict[str, Any]], List[JsonParsingError]]:
        """Run the parsing logic."""
        if "{" not in self.text and "[" not in self.text:
            return [], []

        for i, char in enumerate(self.text):
            self._process_char(i, char)

        return self.objects, self.errors

    def _process_char(self, i: int, char: str):
        """Process a single character and update state."""
        if self._escape:
            self._escape = False
            return
        if char == "\\":
            self._escape = True
            return
        if char == '"' and not self._escape:
            self._in_string = not self._in_string
            return
        if self._in_string:
            return

        if char in "{[":
            if not self._stack:
                self._start_indices.append(i)
            self._stack.append(char)

        elif char in "}]":
            self._handle_closing(char, i)

    def _handle_closing(self, char: str, current_index: int):
        """Handle closing brackets and attempt JSON parsing."""
        expected_open = "{" if char == "}" else "["

        if self._stack and self._stack[-1] == expected_open:
            self._stack.pop()

            if not self._stack and self._start_indices:
                start_index = self._start_indices.pop()
                self._attempt_parse(start_index, current_index)

    def _attempt_parse(self, start_index: int, current_index: int):
        """Attempt to parse the substring as JSON."""
        candidate = self.text[start_index : current_index + 1]
        try:
            obj = json.loads(candidate)
            if isinstance(obj, (dict, list)):
                self.objects.append(obj)
        except json.JSONDecodeError as e:
            error = JsonParsingError(
                f"Failed to parse JSON candidate at {start_index}: {e}",
                original_error=e,
                position=start_index,
            )
            self.errors.append(error)


def extract_json_with_feedback(text: str) -> Tuple[List[Dict[str, Any]], bool]:
    """
    Wrapper for compatibility with agent logic.
    Returns: (List of objects, boolean indicating if JSON objects were extracted)
    """
    try:
        objects, errors = extract_json_from_text(text)

        for error in errors:
            logger.warning("JSON Parsing Error: %s", error.message)

        return objects, len(objects) > 0
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("JSON Extraction failed: %s", e, exc_info=True)
        return [], False

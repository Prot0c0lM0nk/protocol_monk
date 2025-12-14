# JSON Parser Version 2 (JSONParserV2)

import json
import re
from typing import List, Tuple, Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)


class JSONParserV2:
    """Enhanced JSON parsing with retry logic and better error recovery.

    Features:
    - Automatic retry mechanism for malformed JSON
    - Common JSON error correction
    - Strict validation of tool call schemas
    - Detailed error reporting
    - Support for markdown code blocks
    - Multiple parsing strategies with fallback mechanisms
    """

    def __init__(self, max_attempts: int = 3):
        """Initialize the JSON parser.

        Args:
            max_attempts: Maximum number of parsing attempts (default: 3)
        """
        self.max_attempts = max_attempts

    def extract_json_objects(self, text: str) -> Tuple[List[Dict], List[str]]:
        """Extract JSON objects from text with retry logic.

        Args:
            text: Input text potentially containing JSON objects

        Returns:
            Tuple containing:
            - List of valid tool call objects
            - List of error messages from failed attempts
        """
        attempts = 0
        errors = []
        text_to_parse = text.strip()

        while attempts < self.max_attempts:
            attempts += 1

            try:
                # Try direct JSON parsing first
                if text_to_parse.startswith("[") and text_to_parse.endswith("]"):
                    data = json.loads(text_to_parse)
                    if isinstance(data, list):
                        valid_objects = self._validate_tool_calls(data)
                        return valid_objects, errors

                # Try parsing as single object
                if text_to_parse.startswith("{") and text_to_parse.endswith("}"):
                    data = json.loads(text_to_parse)
                    if isinstance(data, dict):
                        valid_objects = self._validate_tool_calls([data])
                        return valid_objects, errors

                # Try extracting from markdown code blocks
                markdown_objects = self._extract_from_markdown(text_to_parse)
                if markdown_objects:
                    return markdown_objects, errors

                # Try fixing common issues and parsing again
                if attempts < self.max_attempts:
                    text_to_parse = self._fix_common_errors(text_to_parse)
                    continue

            except json.JSONDecodeError as e:
                errors.append(f"Attempt {attempts}: {str(e)}")
                if attempts < self.max_attempts:
                    text_to_parse = self._fix_common_errors(text_to_parse)
                    continue

            # If we've exhausted attempts, try a more aggressive approach
            if attempts >= self.max_attempts:
                return self._extract_with_fallback(text_to_parse, errors)

        return [], errors

    def _extract_from_markdown(self, text: str) -> Optional[List[Dict]]:
        """Extract JSON from markdown code blocks.

        Args:
            text: Text containing markdown code blocks

        Returns:
            List of valid JSON objects found in markdown blocks or None if none found
        """
        # Try to find JSON in markdown code blocks
        code_blocks = re.findall(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
        if not code_blocks:
            return None

        # Try each code block until we find valid JSON
        for block in code_blocks:
            try:
                data = json.loads(block)
                if isinstance(data, dict):
                    return self._validate_tool_calls([data])
                elif isinstance(data, list):
                    return self._validate_tool_calls(data)
            except json.JSONDecodeError:
                continue

        return None

    def _fix_common_errors(self, text: str) -> str:
        """Fix common JSON formatting issues.

        Args:
            text: Text containing JSON with formatting issues

        Returns:
            Text with common JSON formatting issues resolved
        """
        # Remove non-printable characters
        text = "".join(
            char for char in text if 32 <= ord(char) <= 126 or char in "\n\r\t"
        )

        # Fix trailing commas
        text = re.sub(r",(\s*[}\]])\s*", r"\1", text)

        # Fix unquoted keys
        text = re.sub(r"(\{|\[|,)\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*:", r'\1"\2":', text)

        # Fix single quotes to double quotes for keys and string values
        text = re.sub(r"'([^']*)'(?=\s*:)", r'"\1"', text)  # Keys
        text = re.sub(r"'([^']*)'(?=\s*[,}\]])", r'"\1"', text)  # String values

        # Fix missing commas between objects in arrays
        text = re.sub(r"}\s*(?={)", "}, ", text)

        # Add missing closing braces/brackets
        open_braces = text.count("{")
        close_braces = text.count("}")
        if open_braces > close_braces:
            text += "}" * (open_braces - close_braces)

        open_brackets = text.count("[")
        close_brackets = text.count("]")
        if open_brackets > close_brackets:
            text += "]" * (open_brackets - close_brackets)

        return text

    def _extract_with_fallback(
        self, text: str, errors: List[str]
    ) -> Tuple[List[Dict], List[str]]:
        """Final attempt to extract JSON using more aggressive methods.

        Args:
            text: Input text to parse
            errors: List of error messages from previous attempts

        Returns:
            Tuple containing:
            - List of valid tool call objects found
            - List of error messages
        """
        try:
            # Look for objects that look like tool calls
            tool_call_pattern = r'{\s*"action"\s*:\s*"[a-zA-Z_]+"\s*[^}]*}'
            matches = re.finditer(tool_call_pattern, text)

            json_objects = []
            for match in matches:
                try:
                    obj = json.loads(match.group(0))
                    if isinstance(obj, dict):
                        json_objects.append(obj)
                except json.JSONDecodeError as e:
                    errors.append(f"Failed to parse potential tool call: {str(e)}")
                    continue

            if json_objects:
                return self._validate_tool_calls(json_objects), errors

        except Exception as e:
            errors.append(f"Fallback extraction failed: {str(e)}")

        return [], errors

    def _validate_tool_calls(self, potential_calls: List[Dict]) -> List[Dict]:
        """Validate that the extracted objects are valid tool calls.

        Args:
            potential_calls: List of potential tool call objects

        Returns:
            List of validated tool call objects
        """
        valid_calls = []

        for call in potential_calls:
            if not isinstance(call, dict):
                continue

            # Check for required fields
            if "action" not in call:
                continue
            if "parameters" not in call:
                continue  # Parameters field is required
            # Ensure parameters is a dictionary if present
            if "parameters" in call and not isinstance(call["parameters"], dict):
                continue

            # Ensure reasoning is a string if present
            if "reasoning" in call and not isinstance(call["reasoning"], str):
                continue

            valid_calls.append(call)

        return valid_calls


# Convenience function for simple use cases
def extract_json_with_retry(
    text: str, max_attempts: int = 3
) -> Tuple[List[Dict], List[str]]:
    """Extract JSON objects from text with retry logic.

    Args:
        text: Input text potentially containing JSON objects
        max_attempts: Maximum number of parsing attempts (default: 3)

    Returns:
        Tuple containing:
        - List of valid tool call objects
        - List of error messages from failed attempts
    """
    parser = JSONParserV2(max_attempts=max_attempts)
    return parser.extract_json_objects(text)

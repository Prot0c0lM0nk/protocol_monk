from typing import List, Dict, Any, Tuple, Optional
import json
import re
import logging

from utils.exceptions import JsonParsingError

logger = logging.getLogger(__name__)

class JsonParsingError(Exception):
    """Custom exception for JSON parsing errors with context"""
    def __init__(self, message: str, original_error: Optional[Exception] = None, position: Optional[int] = None):
        super().__init__(message)
        self.original_error = original_error
        self.position = position
        self.message = message

def extract_json_from_text(text: str) -> Tuple[List[Dict[str, Any]], List[JsonParsingError]]:
    """
    Robustly extracts JSON objects with detailed error tracking.
    
    Strategies:
    1. STRICT FENCING: Looks for ```json ... ``` blocks first.
    2. FALLBACK: Looks for raw JSON objects if no fences are found.
    
    Returns:
        Tuple of (successful_objects, parsing_errors)
    """
    json_objects = []
    parsing_errors = []
    
    # --- Strategy 1: Markdown Code Blocks (Preferred) ---
    # Matches ```json {content} ``` with multiline support
    fence_pattern = r"```json\s*([\s\S]*?)\s*```"
    matches = re.findall(fence_pattern, text, re.DOTALL)
    
    if matches:
        for match in matches:
            try:
                obj = json.loads(match)
                # We only care about Dictionaries (JSON Objects) or Lists (JSON Arrays)
                if isinstance(obj, (dict, list)):
                    json_objects.append(obj)
            except json.JSONDecodeError as e:
                error = JsonParsingError(
                    f"Failed to parse fenced JSON: {e}",
                    original_error=e
                )
                parsing_errors.append(error)
                logger.warning(f"Failed to parse fenced JSON: {e}")
        
        # If we found fenced content, we return it. We do not mix strategies.
        return json_objects, parsing_errors
    
    # --- Strategy 2: Bracket Counting (Fallback) ---
    # Used only if the model forgets to fence the code.
    if '{' not in text and '[' not in text:
        return json_objects, parsing_errors
    
    # Track both object {} and array [] brackets
    bracket_stack = []
    start_indices = []
    in_string = False
    escape = False
    
    for i, char in enumerate(text):
        if escape:
            escape = False
            continue
        if char == '\\':
            escape = True
            continue
        if char == '"' and not escape:
            in_string = not in_string
            continue
        if in_string:
            continue
        
        if char in '{[':
            if len(bracket_stack) == 0:
                start_indices.append(i)
            bracket_stack.append(char)
        
        elif char in '}':
            if bracket_stack and bracket_stack[-1] == '{':
                bracket_stack.pop()
                
                if len(bracket_stack) == 0 and start_indices:
                    start_index = start_indices.pop()
                    candidate = text[start_index : i + 1]
                    try:
                        obj = json.loads(candidate)
                        if isinstance(obj, (dict, list)):
                            json_objects.append(obj)
                    except json.JSONDecodeError as e:
                        error = JsonParsingError(
                            f"Failed to parse JSON object at position {start_index}: {e}",
                            original_error=e,
                            position=start_index
                        )
                        parsing_errors.append(error)
        
        elif char in ']':
            if bracket_stack and bracket_stack[-1] == '[':
                bracket_stack.pop()
                
                if len(bracket_stack) == 0 and start_indices:
                    start_index = start_indices.pop()
                    candidate = text[start_index : i + 1]
                    try:
                        obj = json.loads(candidate)
                        if isinstance(obj, (dict, list)):
                            json_objects.append(obj)
                    except json.JSONDecodeError as e:
                        error = JsonParsingError(
                            f"Failed to parse JSON array at position {start_index}: {e}",
                            original_error=e,
                            position=start_index
                        )
                        parsing_errors.append(error)
    
    return json_objects, parsing_errors

def extract_json_with_feedback(text: str) -> Tuple[List[Dict[str, Any]], bool]:
    """
    Wrapper for compatibility with agent logic.
    Returns: (List of objects, boolean indicating if extraction occurred)
    """
    try:
        objects, errors = extract_json_from_text(text)
        
        # Log any errors via EnhancedLogger
        for error in errors:
            logger.warning(f"JSON Parsing Error: {error.message}")
        
        return objects, len(objects) > 0
    except Exception as e:
        logger.error(f"JSON Extraction failed: {e}")
        # Return empty list rather than crashing the agent loop
        return [], False
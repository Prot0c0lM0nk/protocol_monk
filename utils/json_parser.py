from typing import List, Dict, Any, Tuple
import json
import re
import logging

from utils.exceptions import JsonParsingError

logger = logging.getLogger(__name__)

def extract_json_from_text(text: str) -> List[Dict[str, Any]]:
    """
    Robustly extracts JSON objects.
    
    Strategies:
    1. STRICT FENCING: Looks for ```json ... ``` blocks first.
    2. FALLBACK: Looks for raw JSON objects if no fences are found.
    """
    json_objects = []
    
    # --- Strategy 1: Markdown Code Blocks (Preferred) ---
    # Matches ```json {content} ```
    fence_pattern = r"```json\s*(\{.*?\})\s*```"
    matches = re.findall(fence_pattern, text, re.DOTALL)
    
    if matches:
        for match in matches:
            try:
                obj = json.loads(match)
                if isinstance(obj, dict):
                    json_objects.append(obj)
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse fenced JSON: {e}")
                # Don't raise immediately, try other matches
                continue
        
        # If we found fenced content, we return it. We do not mix strategies.
        if json_objects:
            return json_objects

    # --- Strategy 2: Bracket Counting (Fallback) ---
    # Used only if the model forgets to fence the code.
    if '{' not in text:
        return []

    brace_depth = 0
    start_index = -1
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

        if char == '{':
            if brace_depth == 0:
                start_index = i
            brace_depth += 1
        
        elif char == '}':
            if brace_depth > 0:
                brace_depth -= 1
                
                if brace_depth == 0 and start_index != -1:
                    candidate = text[start_index : i + 1]
                    try:
                        obj = json.loads(candidate)
                        if isinstance(obj, dict):
                            # --- CRITICAL FIX: The missing append line ---
                            json_objects.append(obj) 
                    except json.JSONDecodeError:
                        continue
                    finally:
                        start_index = -1

    return json_objects

def extract_json_with_feedback(text: str) -> Tuple[List[Dict[str, Any]], bool]:
    """
    Wrapper for compatibility with agent logic.
    Returns: (List of objects, boolean indicating if extraction occurred)
    """
    try:
        objects = extract_json_from_text(text)
        return objects, len(objects) > 0
    except Exception as e:
        logger.error(f"JSON Extraction failed: {e}")
        # Return empty list rather than crashing the agent loop
        return [], False
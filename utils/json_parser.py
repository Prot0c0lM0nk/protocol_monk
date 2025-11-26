from typing import List, Dict, Any
import json
import re
import logging

logger = logging.getLogger(__name__)

def extract_json_from_text(text: str) -> List[Dict[str, Any]]:
    """
    Robustly extracts JSON objects from mixed text/code content.
    
    Strategies:
    1. Finds standard JSON blocks enclosed in braces {}.
    2. Handles nested braces using a depth counter.
    3. Validates parsing with json.loads().
    
    Returns:
        List[Dict]: A list of successfully parsed JSON dictionaries.
    """
    json_objects = []
    
    # Quick optimization: if no braces, return early
    if '{' not in text or '}' not in text:
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
                        # Attempt to parse the candidate block
                        obj = json.loads(candidate)
                        
                        # We only care about Dictionaries (JSON Objects), not Lists or primitives
                        if isinstance(obj, dict):
                            json_objects.append(obj)
                    except json.JSONDecodeError:
                        # Common issue: The model might output invalid JSON (e.g., trailing commas)
                        # In a future iteration, we can add "heuristic repair" here.
                        logger.debug(f"Failed to parse candidate JSON block: {candidate[:50]}...")
                        continue
                    finally:
                        start_index = -1

    return json_objects

# Backward compatibility alias
def extract_json_with_feedback(text: str) -> tuple[List[Dict[str, Any]], bool]:
    objects = extract_json_from_text(text)
    return objects, False
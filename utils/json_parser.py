from typing import List, Dict, Any, Tuple
import json
import re
import logging

logger = logging.getLogger(__name__)

def extract_json_with_feedback(text: str) -> Tuple[List[Dict[str, Any]], bool]:
    """
    Extracts JSON and detects if the output was likely truncated (cutoff).
    
    Strategies:
    1. Finds standard JSON blocks enclosed in braces {}.
    2. Handles nested braces using a depth counter.
    3. Detects truncation based on unclosed braces or dangling syntax.
    
    Returns:
        (json_objects, is_truncated)
    """
    json_objects = []
    is_truncated = False
    
    # State tracking
    brace_depth = 0
    in_string = False
    escape = False
    
    # Quick optimization: if empty, return early
    if not text:
        return [], False

    # 1. Brace Scanning Loop
    # We run this even if '{' isn't present initially to safely track state 
    # (though usually optimization skips it, we want robust depth tracking)
    if '{' in text:
        start_index = -1
        
        for i, char in enumerate(text):
            if escape:
                escape = False
                continue
            if char == '\\':
                escape = True
                continue
            if char == '"':
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
                                json_objects.append(obj)
                        except json.JSONDecodeError:
                            pass
                        finally:
                            start_index = -1

    # 2. Check for Truncation/Cutoff Signs
    
    # CRITICAL FIX: If we finished the loop and brace_depth > 0, 
    # it means we opened a JSON object but never closed it. 
    # This is the DEFINITION of truncation.
    if brace_depth > 0:
        is_truncated = True

    # If brace_depth is 0, we might still have dangling syntax at the very end
    # (e.g. "Here is the json: " or "{"key": "value",")
    else:
        stripped = text.strip()
        
        # Only check these heuristics if we didn't find any valid objects OR 
        # if the text looks like it was trying to continue.
        
        # Heuristic 1: Ends with partial JSON syntax
        if stripped.endswith((',', ':')):
            is_truncated = True
            
        # Heuristic 2: We are inside a string that never closed
        elif in_string:
            is_truncated = True
            
        # Heuristic 3: It looks like it started a list or object at the very end
        elif stripped.endswith(('{', '[')):
            is_truncated = True

    return json_objects, is_truncated

# Backward compatibility alias
def extract_json_from_text(text: str) -> List[Dict[str, Any]]:
    objects, _ = extract_json_with_feedback(text)
    return objects
"""
Response Parsing Logic
======================
Pure functions for extracting intent and content from model responses.
"""
import json
import logging
from typing import List, Tuple, Union, Dict, Any

logger = logging.getLogger(__name__)

class ToolCallExtractor:
    """Extracts tool calls from various model response formats."""

    @staticmethod
    def extract(response_data: Union[str, Dict, Any]) -> Tuple[List[Dict], bool]:
        """
        Parse response and return (actions, has_actions).
        Handles: Ollama Objects, Structured Dicts, Tool Call Arrays.
        """
        actions = []

        # CASE 0: Ollama ChatResponse object
        if hasattr(response_data, "message"):
            if hasattr(response_data.message, "tool_calls") and response_data.message.tool_calls:
                for tool_call in response_data.message.tool_calls:
                    func = tool_call.function
                    actions.append({
                        "action": func.name,
                        "parameters": (
                            json.loads(func.arguments)
                            if isinstance(func.arguments, str)
                            else func.arguments
                        ),
                        "id": getattr(tool_call, "id", None),
                    })
                return actions, len(actions) > 0

        # CASE 1: Dictionary (Structured API Call)
        if isinstance(response_data, dict):
            # Check for standard 'tool_calls' array (OpenAI/OpenRouter style)
            if "tool_calls" in response_data:
                for tc in response_data["tool_calls"]:
                    func = tc.get("function", {})
                    actions.append({
                        "action": func.get("name"),
                        "parameters": (
                            json.loads(func.get("arguments", "{}"))
                            if isinstance(func.get("arguments"), str)
                            else func.get("arguments")
                        ),
                        "id": tc.get("id"),
                    })
            # Check for direct action/parameters (Custom/Ollama style)
            elif "action" in response_data and "parameters" in response_data:
                actions.append(response_data)
            
            return actions, len(actions) > 0

        # CASE 2: String (No tools)
        return [], False


class ModelResponseParser:
    """Handles text accumulation and stream parsing."""
    
    @staticmethod
    def merge_tool_call_chunks(accumulator: Dict, new_chunk: Dict) -> Dict:
        """Merge a new tool call chunk into the accumulator."""
        if accumulator is None:
            accumulator = {"tool_calls": []}
            
        if "tool_calls" not in accumulator:
            accumulator["tool_calls"] = []

        for i, new_tc in enumerate(new_chunk["tool_calls"]):
            if i < len(accumulator["tool_calls"]):
                # Merge with existing
                existing = accumulator["tool_calls"][i]
                if new_tc.get("id"): existing["id"] = new_tc["id"]
                if new_tc.get("type"): existing["type"] = new_tc["type"]
                
                if new_tc.get("function"):
                    if "function" not in existing: existing["function"] = {}
                    if new_tc["function"].get("name"):
                        existing["function"]["name"] = new_tc["function"]["name"]
                    if new_tc["function"].get("arguments"):
                        existing["function"]["arguments"] = (
                            existing["function"].get("arguments", "") + 
                            new_tc["function"]["arguments"]
                        )
            else:
                # Add new
                accumulator["tool_calls"].append(new_chunk["tool_calls"][i])
        
        return accumulator
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
    def _safe_arguments(value: Any) -> Dict[str, Any]:
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                return parsed if isinstance(parsed, dict) else {}
            except json.JSONDecodeError:
                return {}
        return {}

    @staticmethod
    def extract(response_data: Union[str, Dict, Any]) -> Tuple[List[Dict], bool]:
        """
        Parse response and return (actions, has_actions).
        Handles: Ollama Objects, Structured Dicts, Tool Call Arrays.
        """
        actions = []

        # CASE 0: Ollama ChatResponse object
        if hasattr(response_data, "message"):
            if (
                hasattr(response_data.message, "tool_calls")
                and response_data.message.tool_calls
            ):
                for tool_call in response_data.message.tool_calls:
                    func = tool_call.function
                    actions.append(
                        {
                            "action": func.name,
                            "parameters": ToolCallExtractor._safe_arguments(
                                getattr(func, "arguments", "{}")
                            ),
                            "id": getattr(tool_call, "id", None),
                        }
                    )
                return actions, len(actions) > 0

        # CASE 1: Dictionary (Structured API Call)
        if isinstance(response_data, dict):
            message = response_data.get("message")
            if isinstance(message, dict):
                nested_tool_calls = message.get("tool_calls")
                if isinstance(nested_tool_calls, list):
                    for tc in nested_tool_calls:
                        if not isinstance(tc, dict):
                            continue
                        func = tc.get("function", {})
                        if not isinstance(func, dict):
                            continue
                        actions.append(
                            {
                                "action": func.get("name"),
                                "parameters": ToolCallExtractor._safe_arguments(
                                    func.get("arguments", "{}")
                                ),
                                "id": tc.get("id"),
                            }
                        )
                    return actions, len(actions) > 0

            # Check for standard 'tool_calls' array (OpenAI/OpenRouter style)
            if "tool_calls" in response_data:
                for tc in response_data["tool_calls"]:
                    func = tc.get("function", {})
                    if not isinstance(func, dict):
                        continue
                    actions.append(
                        {
                            "action": func.get("name"),
                            "parameters": ToolCallExtractor._safe_arguments(
                                func.get("arguments", "{}")
                            ),
                            "id": tc.get("id"),
                        }
                    )
            # Check for direct action/parameters (Custom/Ollama style)
            elif "action" in response_data and "parameters" in response_data:
                actions.append(response_data)

            return actions, len(actions) > 0

        # CASE 2: String (No tools)
        return [], False


class ModelResponseParser:
    """Handles text accumulation and stream parsing."""

    @staticmethod
    def _is_valid_json(value: str) -> bool:
        try:
            json.loads(value)
            return True
        except Exception:
            return False

    @staticmethod
    def _merge_argument_fragments(existing_args: str, incoming_args: str) -> str:
        """
        Merge streaming function.arguments safely across providers.

        Some providers stream incremental fragments, others send cumulative/full
        arguments repeatedly. This logic avoids producing invalid duplicated JSON.
        """
        existing = str(existing_args or "")
        incoming = str(incoming_args or "")

        if not incoming:
            return existing
        if not existing:
            return incoming
        if incoming == existing:
            return existing
        if incoming.startswith(existing):
            # Cumulative payload: replace with fuller incoming string.
            return incoming
        if existing.startswith(incoming):
            # Incoming is an earlier subset; keep the fuller existing value.
            return existing
        if ModelResponseParser._is_valid_json(incoming):
            # Incoming already complete; prefer complete JSON over mixed fragments.
            return incoming

        return existing + incoming

    @staticmethod
    def merge_tool_call_chunks(accumulator: Dict, new_chunk: Dict) -> Dict:
        """Merge a new tool call chunk into the accumulator."""
        if accumulator is None:
            accumulator = {"tool_calls": []}

        if "tool_calls" not in accumulator:
            accumulator["tool_calls"] = []

        for i, new_tc in enumerate(new_chunk.get("tool_calls", [])):
            if i < len(accumulator["tool_calls"]):
                # Merge with existing
                existing = accumulator["tool_calls"][i]
                if new_tc.get("id"):
                    existing["id"] = new_tc["id"]
                if new_tc.get("type"):
                    existing["type"] = new_tc["type"]

                if new_tc.get("function"):
                    if "function" not in existing:
                        existing["function"] = {}
                    if new_tc["function"].get("name"):
                        existing["function"]["name"] = new_tc["function"]["name"]
                    if new_tc["function"].get("arguments"):
                        existing["function"]["arguments"] = (
                            ModelResponseParser._merge_argument_fragments(
                                existing["function"].get("arguments", ""),
                                new_tc["function"]["arguments"],
                            )
                        )
            else:
                # Add new
                accumulator["tool_calls"].append(new_chunk["tool_calls"][i])

        return accumulator

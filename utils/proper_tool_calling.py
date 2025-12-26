#!/usr/bin/env python3
"""
Proper Tool Calling Implementation
===============================

This module implements proper API-based tool calling
instead of text-based parsing.

The issue: We were doing text-based tool calling:
1. Model generates text with JSON
2. We parse the text (fails constantly)
3. Execute tools

The solution: Proper API-based tool calling:
1. Send tools/functions schema in API request
2. Model returns structured tool calls in API response
3. Execute tools directly (no parsing)
"""

import json
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ToolCall:
    """Structured tool call from API response"""

    id: str
    action: str
    parameters: Dict[str, Any]
    reasoning: Optional[str] = None


class ProperToolCalling:
    """
    Implements proper API-based tool calling for Ollama and OpenRouter.

    This eliminates all the JSON parsing issues by using the
    native tool calling APIs that both providers support.
    """

    def __init__(self, tool_registry):
        self.tool_registry = tool_registry

    def get_tools_schema(self) -> List[Dict[str, Any]]:
        """
        Convert tool registry to OpenAI-compatible tools schema.

        Returns:
            List of tool definitions in OpenAI format
        """
        tools = []

        for tool_name, tool_instance in self.tool_registry._tools.items():
            schema = tool_instance.schema
            tool_def = {
                "type": "function",
                "function": {
                    "name": schema.name,
                    "description": schema.description,
                    "parameters": self._convert_parameters(schema.parameters),
                },
            }
            tools.append(tool_def)

        return tools

    def _convert_parameters(self, params: Dict) -> Dict:
        """
        Convert tool parameters to JSON schema format.

        Args:
            params: Tool parameters from registry

        Returns:
            JSON schema parameters
        """
        if not params:
            return {"type": "object", "properties": {}}

        properties = {}
        required = []

        for param_name, param_info in params.items():
            if isinstance(param_info, dict):
                properties[param_name] = {
                    "type": param_info.get("type", "string"),
                    "description": param_info.get(
                        "description", f"Parameter {param_name}"
                    ),
                }

                if param_info.get("required", False):
                    required.append(param_name)
            else:
                # Simple string parameter
                properties[param_name] = {
                    "type": "string",
                    "description": str(param_info),
                }

        return {"type": "object", "properties": properties, "required": required}

    def prepare_api_request(
        self,
        messages: List[Dict],
        tools: Optional[List[Dict]] = None,
        tool_choice: str = "auto",
    ) -> Dict[str, Any]:
        """
        Prepare API request with proper tool calling.

        Args:
            messages: Conversation messages
            tools: List of available tools (optional, will generate if None)
            tool_choice: How to choose tools ("auto", "none", "required")

        Returns:
            API request payload with tools
        """
        if tools is None:
            tools = self.get_tools_schema()

        payload = {
            "messages": messages,
            "tools": tools,
            "tool_choice": tool_choice if tools else "none",
        }

        return payload

    def extract_tool_calls(self, api_response: Dict[str, Any]) -> List[ToolCall]:
        tool_calls = []
    
        # Extract the message object regardless of top-level key (choices or message)
        message = {}
        if "choices" in api_response:
            message = api_response["choices"][0].get("message", {})
        elif "message" in api_response:
            message = api_response["message"]

        raw_calls = message.get("tool_calls", [])
        if not raw_calls:
            return []

        for tc in raw_calls:
            func = tc.get("function", {})
            name = func.get("name", "")
            raw_args = func.get("arguments", {})

            # HANDLE STRING VS DICT ARGUMENTS
            if isinstance(raw_args, str):
                try:
                    parameters = json.loads(raw_args)
                except json.JSONDecodeError:
                    parameters = {} # Or handle partial JSON
            else:
                parameters = raw_args if isinstance(raw_args, dict) else {}

            tool_calls.append(ToolCall(
                id=tc.get("id", ""),
                action=name,
                parameters=parameters,
                reasoning=message.get("content") # Use assistant text as reasoning
            ))

        return tool_calls

    def format_tool_response(self, tool_call_id: str, result: str) -> Dict[str, Any]:
        """
        Format tool result for API response.

        Args:
            tool_call_id: ID of the tool call
            result: Result from tool execution

        Returns:
            Tool response message for API
        """
        return {"role": "tool", "content": result, "tool_call_id": tool_call_id}


# Example usage:
#
# # Initialize proper tool calling
# tool_caller = ProperToolCalling(tool_registry)
#
# # Prepare API request with tools
# payload = tool_caller.prepare_api_request(messages)
#
# # Send to model (both Ollama and OpenRouter support this)
# response = await model_client.get_response_async(payload)
#
# # Extract tool calls (no parsing needed!)
# tool_calls = tool_caller.extract_tool_calls(response)
#
# # Execute tools
# for tool_call in tool_calls:
#     result = await tool_registry.execute_tool(
#         tool_call.action,
#         **tool_call.parameters
#     )
#
#     # Add result to conversation
#     messages.append(tool_caller.format_tool_response(
#         tool_call.id,
#         result.output
#     ))

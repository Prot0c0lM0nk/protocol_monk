"""Regression tests for Ollama message normalization."""

import importlib.util
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

_OLLAMA_MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "agent"
    / "providers"
    / "ollama_model_client_sdk.py"
)
_OLLAMA_SPEC = importlib.util.spec_from_file_location(
    "ollama_model_client_sdk_for_test", _OLLAMA_MODULE_PATH
)
assert _OLLAMA_SPEC and _OLLAMA_SPEC.loader
_OLLAMA_MODULE = importlib.util.module_from_spec(_OLLAMA_SPEC)
_OLLAMA_SPEC.loader.exec_module(_OLLAMA_MODULE)
OllamaModelClientSDK = _OLLAMA_MODULE.OllamaModelClientSDK


def test_normalize_messages_parses_json_tool_arguments():
    messages = [
        {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {
                        "name": "execute_command",
                        "arguments": '{"command":"ls -la","description":"list files"}',
                    },
                }
            ],
        }
    ]

    normalized = OllamaModelClientSDK._normalize_messages_for_ollama(messages)
    args = normalized[0]["tool_calls"][0]["function"]["arguments"]

    assert isinstance(args, dict)
    assert args["command"] == "ls -la"


def test_normalize_messages_coerces_invalid_tool_arguments_to_dict():
    messages = [
        {
            "role": "assistant",
            "tool_calls": [
                {
                    "type": "function",
                    "function": {
                        "name": "execute_command",
                        "arguments": "{not-json}",
                    },
                }
            ],
        }
    ]

    normalized = OllamaModelClientSDK._normalize_messages_for_ollama(messages)
    args = normalized[0]["tool_calls"][0]["function"]["arguments"]

    assert isinstance(args, dict)
    assert args == {}

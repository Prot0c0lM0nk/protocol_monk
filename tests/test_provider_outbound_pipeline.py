"""Tests for provider-fresh outbound formatting and FG persistence behavior."""

from __future__ import annotations

import copy
import json

import pytest

try:
    from protocol_monk.agent.providers.mlx_lm_model_client import MLXLMModelClient
    from protocol_monk.agent.providers.openrouter_model_client_sdk import (
        OpenRouterModelClient,
    )
    from protocol_monk.agent.providers.ollama_model_client_sdk import (
        OllamaModelClientSDK,
    )
    from protocol_monk.agent.tool_pipeline.manager import ToolPipelineManager
    from protocol_monk.agent.tool_pipeline.functiongemma_converter import (
        FunctionGemmaConverter,
    )
    from protocol_monk.agent.logic.parsers import ModelResponseParser
    from protocol_monk.agent.tool_pipeline.token_protocol import (
        TOOL_CALL_END,
        TOOL_CALL_START,
    )
    from protocol_monk.agent.tool_pipeline.types import PipelineParseResult
    from protocol_monk.agent.service import AgentService
    from protocol_monk.agent.events import EventBus
except ImportError:  # pragma: no cover - local source tree fallback
    from agent.providers.mlx_lm_model_client import MLXLMModelClient
    from agent.providers.openrouter_model_client_sdk import OpenRouterModelClient
    from agent.providers.ollama_model_client_sdk import OllamaModelClientSDK
    from agent.tool_pipeline.manager import ToolPipelineManager
    from agent.tool_pipeline.functiongemma_converter import FunctionGemmaConverter
    from agent.logic.parsers import ModelResponseParser
    from agent.tool_pipeline.token_protocol import TOOL_CALL_END, TOOL_CALL_START
    from agent.tool_pipeline.types import PipelineParseResult
    from agent.service import AgentService
    from agent.events import EventBus


def test_mlx_outbound_builder_keeps_openai_compatible_tool_fields():
    context = [
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "execute_command", "arguments": {"command": "pwd"}},
                }
            ],
            "metadata": {"internal": True},
        },
        {
            "role": "tool",
            "content": "ok",
            "tool_call_id": "call_1",
            "extra": "ignored",
        },
    ]

    outbound, diag = MLXLMModelClient._build_outbound_messages(context)
    assert outbound[0]["role"] == "assistant"
    assert outbound[0]["content"] == ""
    assert isinstance(outbound[0]["tool_calls"], list)
    assert outbound[0]["tool_calls"][0]["function"]["name"] == "execute_command"
    assert outbound[0]["tool_calls"][0]["function"]["arguments"] == '{"command":"pwd"}'
    assert "metadata" not in outbound[0]

    assert outbound[1] == {"role": "tool", "content": "ok", "tool_call_id": "call_1"}
    assert diag["dropped_keys"] >= 2
    assert diag["defaulted_empty_content"] == 1


def test_mlx_outbound_builder_sanitizes_invalid_tool_arguments():
    context = [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {
                        "name": "execute_command",
                        "arguments": '{"command":"python -c \\"bad\\escape\\""}',
                    },
                }
            ],
        }
    ]

    outbound, _ = MLXLMModelClient._build_outbound_messages(context)
    assert outbound[0]["tool_calls"][0]["function"]["arguments"] == "{}"


def test_openrouter_outbound_builder_keeps_openai_compatible_fields():
    context = [
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {
                        "name": "execute_command",
                        "arguments": {"command": "pwd"},
                    },
                }
            ],
            "metadata": {"ignored": True},
        },
        {
            "role": "tool",
            "content": "ok",
            "tool_call_id": "call_1",
            "name": "execute_command",
            "extra": "ignored",
        },
    ]

    outbound, diag = OpenRouterModelClient._build_outbound_messages(context)

    assert outbound[0]["role"] == "assistant"
    assert outbound[0]["content"] == ""
    assert isinstance(outbound[0]["tool_calls"], list)
    assert outbound[0]["tool_calls"][0]["function"]["arguments"] == '{"command":"pwd"}'
    assert "metadata" not in outbound[0]

    assert outbound[1] == {
        "role": "tool",
        "content": "ok",
        "tool_call_id": "call_1",
    }
    assert diag["defaulted_empty_content"] == 1
    assert diag["dropped_keys"] >= 2


def test_ollama_outbound_builder_does_not_mutate_input():
    context = [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "type": "function",
                    "function": {"name": "execute_command", "arguments": '{"command":"pwd"}'},
                }
            ],
        }
    ]
    original = copy.deepcopy(context)

    built, _ = OllamaModelClientSDK._build_outbound_messages(context)
    normalized = OllamaModelClientSDK._normalize_messages_for_ollama(built)

    assert context == original
    assert isinstance(normalized[0]["tool_calls"][0]["function"]["arguments"], dict)
    assert normalized[0]["tool_calls"][0]["function"]["arguments"]["command"] == "pwd"


def test_cross_provider_builders_do_not_mutate_source():
    context = [
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_1",
                    "function": {"name": "execute_command", "arguments": {"command": "pwd"}},
                }
            ],
            "metadata": {"x": 1},
        }
    ]
    original = copy.deepcopy(context)

    _ = MLXLMModelClient._build_outbound_messages(context)
    _ = OpenRouterModelClient._build_outbound_messages(context)

    assert context == original


class _ToolRegistryStub:
    def __init__(self):
        self._tools = {"execute_command": object()}


@pytest.mark.asyncio
async def test_functiongemma_parse_disables_tool_call_message_persistence():
    manager = ToolPipelineManager(tool_registry=_ToolRegistryStub(), proper_tool_caller=None)
    manager.set_mode("functiongemma")

    async def _fake_convert_calls(*args, **kwargs):
        return [{"action": "execute_command", "parameters": {"command": "pwd"}}]

    manager._converter.convert_calls = _fake_convert_calls  # type: ignore[attr-defined]
    response = f'{TOOL_CALL_START}execute_command(command="pwd"){TOOL_CALL_END}'

    parsed = await manager.parse_response(response, latest_user_text="pwd please")
    assert parsed.has_actions is True
    assert parsed.persist_tool_call_message is False


class _ContextStub:
    def __init__(self):
        self.assistant_messages = []
        self.tool_call_messages = []

    async def add_assistant_message(self, content):
        self.assistant_messages.append(content)

    async def add_tool_call_message(self, payload):
        self.tool_call_messages.append(payload)


class _LoggerStub:
    def __init__(self):
        self.debug_lines = []

    def debug(self, message, *args):
        self.debug_lines.append(message % args if args else message)


@pytest.mark.asyncio
async def test_service_skips_tool_call_message_when_disabled():
    fake_service = type("FakeService", (), {})()
    fake_service.context_manager = _ContextStub()
    fake_service.logger = _LoggerStub()
    fake_service._tool_pipeline_mode = "functiongemma"

    parsed = PipelineParseResult(
        assistant_text="I will run a tool.",
        actions=[{"action": "execute_command", "parameters": {"command": "pwd"}}],
        tool_calls_payload=[{"id": "fg_call_1"}],
        persist_tool_call_message=False,
    )

    await AgentService._record_assistant_output(fake_service, parsed, actions_count=1)

    assert fake_service.context_manager.assistant_messages == ["I will run a tool."]
    assert fake_service.context_manager.tool_call_messages == []
    assert any("PIPELINE_DIAG skip_tool_call_persist" in line for line in fake_service.logger.debug_lines)


def test_mlx_stream_chunk_to_output_text_only():
    payload = {"choices": [{"delta": {"content": "hello"}}]}
    text, tools = MLXLMModelClient._stream_chunk_to_output(payload)
    assert text == "hello"
    assert tools is None


def test_mlx_stream_chunk_to_output_tool_calls():
    payload = {
        "choices": [
            {
                "delta": {
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {
                                "name": "execute_command",
                                "arguments": '{"command":"pwd"}',
                            },
                        }
                    ]
                }
            }
        ]
    }

    text, tools = MLXLMModelClient._stream_chunk_to_output(payload)
    assert text is None
    assert isinstance(tools, dict)
    assert tools["tool_calls"][0]["id"] == "call_1"
    assert tools["tool_calls"][0]["function"]["name"] == "execute_command"


def test_mlx_completion_to_output_content_and_tools():
    payload = {
        "choices": [
            {
                "message": {
                    "content": "done",
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "function": {
                                "name": "read_file",
                                "arguments": '{"filepath":"README.md"}',
                            },
                        }
                    ],
                }
            }
        ]
    }
    text, tools = MLXLMModelClient._completion_to_output(payload)
    assert text == "done"
    assert tools["tool_calls"][0]["function"]["name"] == "read_file"


def test_mlx_provider_reports_tools_supported():
    client = MLXLMModelClient("mlx-community/LFM2-8B-A1B-4bit")
    assert client.supports_tools() is True


def test_merge_tool_call_chunks_handles_repeated_full_arguments():
    acc = None
    chunk_1 = {
        "tool_calls": [
            {
                "id": "call_1",
                "type": "function",
                "function": {
                    "name": "execute_command",
                    "arguments": '{"command":"pwd"}',
                },
            }
        ]
    }
    chunk_2 = {
        "tool_calls": [
            {
                "id": "call_1",
                "type": "function",
                "function": {
                    "name": "execute_command",
                    "arguments": '{"command":"pwd"}',
                },
            }
        ]
    }

    acc = ModelResponseParser.merge_tool_call_chunks(acc, chunk_1)
    acc = ModelResponseParser.merge_tool_call_chunks(acc, chunk_2)

    args = acc["tool_calls"][0]["function"]["arguments"]
    assert args == '{"command":"pwd"}'
    parsed = json.loads(args)
    assert parsed["command"] == "pwd"


def test_merge_tool_call_chunks_handles_cumulative_arguments():
    acc = None
    chunk_1 = {
        "tool_calls": [
            {
                "id": "call_1",
                "type": "function",
                "function": {"name": "execute_command", "arguments": '{"command":"pw'},
            }
        ]
    }
    chunk_2 = {
        "tool_calls": [
            {
                "id": "call_1",
                "type": "function",
                "function": {
                    "name": "execute_command",
                    "arguments": '{"command":"pwd"}',
                },
            }
        ]
    }

    acc = ModelResponseParser.merge_tool_call_chunks(acc, chunk_1)
    acc = ModelResponseParser.merge_tool_call_chunks(acc, chunk_2)

    args = acc["tool_calls"][0]["function"]["arguments"]
    assert args == '{"command":"pwd"}'


@pytest.mark.asyncio
async def test_service_rejects_functiongemma_mode_for_mlx_provider():
    event_bus = EventBus()
    fake_service = type("FakeService", (), {})()
    fake_service.pipeline_manager = ToolPipelineManager()
    fake_service.current_provider = "mlx_lm"
    fake_service.event_bus = event_bus
    fake_service._tool_pipeline_mode = "native"

    result = await AgentService.request_tool_pipeline_mode(
        fake_service,
        "functiongemma",
        source="test",
    )

    assert result["success"] is False
    assert result["active_mode"] == "native"
    assert "disabled while provider is 'mlx_lm'" in result["message"]


def test_converter_mlx_availability_check_success(monkeypatch):
    converter = FunctionGemmaConverter()

    from config.static import settings

    settings.tool_pipeline.function_provider = "mlx_lm"
    settings.tool_pipeline.function_model = "functiongemma:270m-it-fp16"
    settings.api.providers["mlx_lm"]["url"] = "http://127.0.0.1:8080"

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps(
                {"data": [{"id": "functiongemma:270m-it-fp16"}]}
            ).encode("utf-8")

    monkeypatch.setattr(
        "agent.tool_pipeline.functiongemma_converter.urlopen",
        lambda *_args, **_kwargs: _Resp(),
    )

    ok, reason = converter._check_model_availability()
    assert ok is True
    assert reason == "ok"


def test_converter_mlx_availability_check_missing_model(monkeypatch):
    converter = FunctionGemmaConverter()

    from config.static import settings

    settings.tool_pipeline.function_provider = "mlx_lm"
    settings.tool_pipeline.function_model = "functiongemma:270m-it-fp16"
    settings.api.providers["mlx_lm"]["url"] = "http://127.0.0.1:8080"

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps({"data": [{"id": "different-model"}]}).encode("utf-8")

    monkeypatch.setattr(
        "agent.tool_pipeline.functiongemma_converter.urlopen",
        lambda *_args, **_kwargs: _Resp(),
    )

    ok, reason = converter._check_model_availability()
    assert ok is False
    assert "not listed by MLX server" in reason

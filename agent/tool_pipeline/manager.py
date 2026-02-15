"""Runtime tool pipeline mode manager."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Set

from config.static import settings
from agent.logic.parsers import ToolCallExtractor

from .functiongemma_converter import (
    FunctionGemmaConverter,
    FunctionGemmaConversionError,
)
from .token_protocol import (
    build_tool_list_block,
    build_tool_response_block,
    extract_tool_call_blocks,
)
from .types import PipelineParseResult, ToolPipelineMode, normalize_mode


class ToolPipelineManager:
    """Coordinates native and FunctionGemma tool call paths."""

    def __init__(self, tool_registry=None, proper_tool_caller=None):
        self.tool_registry = tool_registry
        self.proper_tool_caller = proper_tool_caller
        self._mode = normalize_mode(settings.tool_pipeline.mode)
        self._converter = FunctionGemmaConverter()

    @property
    def mode(self) -> ToolPipelineMode:
        return self._mode

    def mode_value(self) -> str:
        return self._mode.value

    def set_mode(self, mode: str) -> ToolPipelineMode:
        self._mode = normalize_mode(mode)
        return self._mode

    def normalize(self, mode: str) -> ToolPipelineMode:
        return normalize_mode(mode)

    def get_prompt_file_for_mode(self, mode: str) -> Path:
        normalized = normalize_mode(mode)
        if normalized == ToolPipelineMode.FUNCTIONGEMMA:
            return settings.tool_pipeline.function_system_prompt_file
        return settings.filesystem.system_prompt_file

    def validate_mode_preconditions(self, mode: str) -> tuple[bool, str]:
        normalized = normalize_mode(mode)
        prompt_file = self.get_prompt_file_for_mode(normalized.value)
        if not prompt_file.exists():
            return False, f"System prompt file missing: {prompt_file}"
        try:
            _ = prompt_file.read_text(encoding="utf-8")
        except Exception as exc:  # pylint: disable=broad-exception-caught
            return False, f"Failed to read system prompt file: {exc}"

        if normalized == ToolPipelineMode.FUNCTIONGEMMA:
            ok, reason = self._converter.validate_preconditions()
            if not ok:
                return False, reason

        return True, "ok"

    def get_main_model_tools_schema(self) -> List[Dict[str, Any]] | None:
        if self._mode == ToolPipelineMode.FUNCTIONGEMMA:
            return None
        if self.proper_tool_caller:
            return self.proper_tool_caller.get_tools_schema()
        return None

    def build_tool_list_prompt(self) -> str:
        schemas = []
        if self.proper_tool_caller:
            schemas = self.proper_tool_caller.get_tools_schema()
        return build_tool_list_block(schemas)

    def wrap_tool_result(
        self,
        tool_name: str,
        success: bool,
        tool_call_id: str | None,
        output: str,
    ) -> str:
        return build_tool_response_block(tool_name, success, tool_call_id, output)

    async def parse_response(
        self,
        response_obj: Any,
        latest_user_text: str,
    ) -> PipelineParseResult:
        if self._mode == ToolPipelineMode.NATIVE:
            actions, has_actions = ToolCallExtractor.extract(response_obj)
            assistant_text = response_obj if isinstance(response_obj, str) else ""
            payload = self._native_tool_calls_payload(response_obj, actions)
            if not has_actions:
                payload = []
            return PipelineParseResult(
                assistant_text=assistant_text,
                actions=actions,
                tool_calls_payload=payload,
            )

        # FunctionGemma mode
        raw_text = self._coerce_response_text(response_obj)
        token_parse = extract_tool_call_blocks(raw_text)
        if token_parse.error:
            return PipelineParseResult(error=token_parse.error)

        if not token_parse.blocks:
            return PipelineParseResult(assistant_text=token_parse.cleaned_text)

        allowed_tools = self._allowed_tool_names()
        tool_list_prompt = self.build_tool_list_prompt()

        try:
            actions = await self._converter.convert_calls(
                tool_list_prompt,
                token_parse.blocks,
                latest_user_text=latest_user_text,
                allowed_tools=allowed_tools,
            )
        except FunctionGemmaConversionError as exc:
            return PipelineParseResult(error=str(exc))

        # Ensure each converted action has a stable tool_call_id for downstream
        # approval/execution and wrapped tool response correlation.
        enriched_actions: List[Dict[str, Any]] = []
        for idx, action in enumerate(actions, start=1):
            item = dict(action)
            item_id = str(item.get("id") or "").strip()
            if not item_id:
                item["id"] = f"fg_call_{idx}"
            enriched_actions.append(item)

        return PipelineParseResult(
            assistant_text=token_parse.cleaned_text,
            actions=enriched_actions,
            tool_calls_payload=enriched_actions,
            persist_tool_call_message=False,
        )

    def _allowed_tool_names(self) -> Set[str]:
        if not self.tool_registry:
            return set()
        return set(self.tool_registry._tools.keys())

    @staticmethod
    def _coerce_response_text(response_obj: Any) -> str:
        if isinstance(response_obj, str):
            return response_obj
        if isinstance(response_obj, dict):
            msg = response_obj.get("message")
            if isinstance(msg, dict):
                return str(msg.get("content", "") or "")
            return str(response_obj.get("content", "") or "")
        return str(response_obj or "")

    @staticmethod
    def _native_tool_calls_payload(response_obj: Any, actions: List[Dict]) -> List[Dict]:
        """Preserve existing native payload extraction behavior."""
        if isinstance(response_obj, dict) and "message" in response_obj:
            message = response_obj.get("message", {})
            if isinstance(message, dict):
                payload = message.get("tool_calls", [])
                if isinstance(payload, list):
                    return payload

        if hasattr(response_obj, "tool_calls"):
            payload = getattr(response_obj, "tool_calls")
            if isinstance(payload, list):
                return payload

        if isinstance(response_obj, dict) and "tool_calls" in response_obj:
            payload = response_obj.get("tool_calls", [])
            if isinstance(payload, list):
                return payload

        return actions if isinstance(actions, list) else []

    @staticmethod
    def _native_input_signature(response_obj: Any) -> str:
        """Lightweight diagnostic signature used by tests and debug logging."""
        if isinstance(response_obj, str):
            return f"str:len={len(response_obj)}"

        if isinstance(response_obj, dict):
            message = response_obj.get("message")
            msg_tool_calls = 0
            if isinstance(message, dict):
                tool_calls = message.get("tool_calls")
                if isinstance(tool_calls, list):
                    msg_tool_calls = len(tool_calls)

            top_tool_calls = 0
            payload = response_obj.get("tool_calls")
            if isinstance(payload, list):
                top_tool_calls = len(payload)

            return (
                "dict:"
                f"msg_tool_calls={msg_tool_calls},"
                f"top_tool_calls={top_tool_calls}"
            )

        return f"{type(response_obj).__name__}"

    @staticmethod
    def response_signature(response_obj: Any) -> str:
        return ToolPipelineManager._native_input_signature(response_obj)

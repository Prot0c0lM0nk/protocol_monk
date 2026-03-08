import asyncio
import json
import logging
from typing import Any, AsyncIterator, Dict, List, Optional, Set

from protocol_monk.agent.structs import Message, ProviderSignal, ToolRequest
from protocol_monk.config.settings import Settings
from protocol_monk.exceptions.provider import ProviderError
from protocol_monk.providers.base import BaseProvider

try:
    from openai import AsyncOpenAI
except Exception:  # pragma: no cover - handled at runtime in __init__
    AsyncOpenAI = None

logger = logging.getLogger("OpenRouterProvider")


class OpenRouterProvider(BaseProvider):
    """
    Adapter for OpenRouter using OpenAI-compatible chat-completions streaming.
    """

    def __init__(self, settings: Settings):
        self.base_url = settings.openrouter_base_url.rstrip("/")
        self.api_key = settings.openrouter_api_key

        if not self.api_key:
            raise ProviderError(
                "OPENROUTER_API_KEY is required when using OpenRouterProvider."
            )
        if AsyncOpenAI is None:
            raise ProviderError(
                "openai dependency is missing. Install requirements to use OpenRouter."
            )

        self.client = AsyncOpenAI(api_key=self.api_key, base_url=self.base_url)

    async def validate_connection(self) -> bool:
        try:
            await self.client.models.list()
            return True
        except Exception as exc:
            logger.error("OpenRouter connection failed: %s", exc)
            return False

    def build_request_payload(
        self,
        messages: List[Message],
        model_name: str,
        tools: Optional[List[Dict[str, Any]]] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        payload_messages = self._serialize_messages(messages)
        request_options = self._sanitize_options(options or {})

        request_payload: Dict[str, Any] = {
            "model": model_name,
            "messages": payload_messages,
            "tools": tools or [],
            "stream": True,
            # Requests usage on streamed responses when provider supports it.
            "stream_options": {"include_usage": True},
        }
        request_payload.update(request_options)
        return request_payload

    async def stream_chat(
        self,
        messages: List[Message],
        model_name: str,
        tools: Optional[List[Dict[str, Any]]] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> AsyncIterator[ProviderSignal]:
        request_payload = self.build_request_payload(
            messages,
            model_name,
            tools=tools,
            options=options,
        )

        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                "OpenRouter request headers: %s",
                {"Authorization": "Bearer ***REDACTED***"},
            )
            logger.debug(
                "OpenRouter request payload: %s",
                json.dumps(request_payload, ensure_ascii=False, default=str),
            )

        pending_tool_calls: Dict[int, Dict[str, Any]] = {}
        seen_tool_call_ids: Dict[str, int] = {}
        generated_tool_call_count = 0
        telemetry: Dict[str, Any] = {
            "provider": "openrouter",
            "request_model": model_name,
            "base_url": self.base_url,
            "chunk_count": 0,
            "usage": {},
            "finish_reasons": [],
            "tool_call_diagnostics": {
                "missing_id_generated": 0,
                "duplicate_id_normalized": 0,
                "invalid_arguments_dropped": 0,
                "malformed_fragments": 0,
            },
        }
        last_chunk: Dict[str, Any] = {}

        try:
            stream = await self.client.chat.completions.create(**request_payload)

            async for chunk in stream:
                chunk_data = self._to_dict(chunk)
                telemetry["chunk_count"] += 1
                last_chunk = chunk_data

                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug(
                        "OpenRouter chunk payload: %s",
                        json.dumps(chunk_data, ensure_ascii=False, default=str),
                    )

                if chunk_data.get("id"):
                    telemetry["id"] = chunk_data["id"]
                if chunk_data.get("model"):
                    telemetry["model"] = chunk_data["model"]
                if chunk_data.get("created"):
                    telemetry["created"] = chunk_data["created"]

                usage = chunk_data.get("usage")
                if isinstance(usage, dict) and usage:
                    telemetry["usage"] = usage

                choices = chunk_data.get("choices") or []
                for choice in choices:
                    if not isinstance(choice, dict):
                        continue

                    finish_reason = choice.get("finish_reason")
                    if finish_reason:
                        telemetry["finish_reasons"].append(str(finish_reason))

                    delta = choice.get("delta") or {}
                    content = delta.get("content")
                    content_text = ""
                    if isinstance(content, str) and content:
                        content_text = content
                        yield ProviderSignal(type="content", data=content)
                    elif isinstance(content, list):
                        extracted = self._extract_content_parts(content)
                        if extracted:
                            content_text = extracted
                            yield ProviderSignal(type="content", data=extracted)

                    reasoning_text = self._extract_reasoning_from_chunk(choice)
                    # Skip reasoning if it duplicates content (some providers send both)
                    if reasoning_text and reasoning_text != content_text:
                        telemetry["reasoning_emitted"] = True
                        yield ProviderSignal(type="thinking", data=reasoning_text)

                    self._merge_tool_call_chunks(
                        pending_tool_calls, delta.get("tool_calls") or []
                    )

                    if finish_reason == "tool_calls":
                        ready, generated_tool_call_count = self._flush_ready_tool_calls(
                            pending_tool_calls,
                            seen_tool_call_ids=seen_tool_call_ids,
                            generated_tool_call_count=generated_tool_call_count,
                            diagnostics=telemetry["tool_call_diagnostics"],
                        )
                        for req in ready:
                            yield ProviderSignal(type="tool_call", data=req)
                        pending_tool_calls.clear()

            # Flush remaining calls at stream end (if provider omitted finish_reason).
            ready, generated_tool_call_count = self._flush_ready_tool_calls(
                pending_tool_calls,
                seen_tool_call_ids=seen_tool_call_ids,
                generated_tool_call_count=generated_tool_call_count,
                diagnostics=telemetry["tool_call_diagnostics"],
            )
            for req in ready:
                yield ProviderSignal(type="tool_call", data=req)

            telemetry["final_chunk"] = last_chunk
            yield ProviderSignal(type="metrics", data=telemetry)

        except asyncio.CancelledError:
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug("OpenRouter stream cancelled by caller.", exc_info=True)
            else:
                logger.info("OpenRouter stream cancelled by caller.")
            raise
        except Exception as exc:
            msg = self._format_provider_error(exc)
            logger.error("OpenRouter stream failed: %s", msg, exc_info=True)
            yield ProviderSignal(type="error", data=msg)
            raise ProviderError(msg)

    @staticmethod
    def _to_dict(value: Any) -> Dict[str, Any]:
        if isinstance(value, dict):
            return value
        model_dump = getattr(value, "model_dump", None)
        if callable(model_dump):
            dumped = model_dump()
            if isinstance(dumped, dict):
                return dumped
        to_dict = getattr(value, "to_dict", None)
        if callable(to_dict):
            dumped = to_dict()
            if isinstance(dumped, dict):
                return dumped
        return {}

    @staticmethod
    def _extract_content_parts(parts: List[Any]) -> str:
        content_chunks: List[str] = []
        for part in parts:
            if not isinstance(part, dict):
                continue
            if part.get("type") == "text" and part.get("text"):
                content_chunks.append(str(part["text"]))
        return "".join(content_chunks)

    @classmethod
    def _extract_reasoning_from_chunk(cls, choice: Dict[str, Any]) -> str:
        parts: List[str] = []
        seen: set = set()

        delta = choice.get("delta")
        if isinstance(delta, dict):
            for part in cls._extract_reasoning_from_payload(delta):
                if part not in seen:
                    parts.append(part)
                    seen.add(part)

        message = choice.get("message")
        if isinstance(message, dict):
            for part in cls._extract_reasoning_from_payload(message):
                if part not in seen:
                    parts.append(part)
                    seen.add(part)

        return "".join(parts)

    @staticmethod
    def _extract_reasoning_from_payload(payload: Dict[str, Any]) -> List[str]:
        parts: List[str] = []

        # Some providers send reasoning in multiple fields that may be duplicates
        # Prioritize 'reasoning' field, then check 'reasoning_content' only if different
        direct = payload.get("reasoning")
        if isinstance(direct, str) and direct:
            parts.append(direct)

        alias = payload.get("reasoning_content")
        # Only add if it's different from 'reasoning' (some providers alias these)
        if isinstance(alias, str) and alias and alias != direct:
            parts.append(alias)

        details = payload.get("reasoning_details")
        if isinstance(details, list):
            for detail in details:
                if not isinstance(detail, dict):
                    continue
                text = detail.get("text")
                if isinstance(text, str) and text and text not in parts:
                    parts.append(text)

                summary = detail.get("summary")
                if isinstance(summary, str) and summary and summary not in parts:
                    parts.append(summary)
                elif isinstance(summary, list):
                    for item in summary:
                        if isinstance(item, str) and item and item not in parts:
                            parts.append(item)
                        elif isinstance(item, dict):
                            item_text = item.get("text")
                            if isinstance(item_text, str) and item_text and item_text not in parts:
                                parts.append(item_text)

        return parts

    def _merge_tool_call_chunks(
        self, pending: Dict[int, Dict[str, Any]], tool_calls: List[Any]
    ) -> None:
        for item in tool_calls:
            if not isinstance(item, dict):
                logger.warning(
                    "OpenRouter emitted malformed tool-call fragment: expected object, got %s",
                    type(item).__name__,
                )
                continue
            index = int(item.get("index", 0) or 0)
            slot = pending.setdefault(
                index, {"id": None, "name": None, "arguments_parts": []}
            )
            if item.get("id"):
                slot["id"] = str(item["id"])
            function = item.get("function") or {}
            if isinstance(function, dict):
                if function.get("name"):
                    slot["name"] = str(function["name"])
                arguments = function.get("arguments")
                if arguments:
                    slot["arguments_parts"].append(str(arguments))
            else:
                logger.warning(
                    "OpenRouter tool-call fragment at index %s has malformed function payload.",
                    index,
                )

    def _flush_ready_tool_calls(
        self,
        pending: Dict[int, Dict[str, Any]],
        *,
        seen_tool_call_ids: Dict[str, int],
        generated_tool_call_count: int,
        diagnostics: Dict[str, int],
    ) -> tuple[List[ToolRequest], int]:
        ready: List[ToolRequest] = []
        for index in sorted(pending.keys()):
            entry = pending[index]
            name = entry.get("name")
            if not name:
                diagnostics["malformed_fragments"] = diagnostics.get(
                    "malformed_fragments", 0
                ) + 1
                logger.warning(
                    "Skipping OpenRouter tool-call fragment at index %s because function name is missing.",
                    index,
                )
                continue

            arguments_text = "".join(entry.get("arguments_parts", [])).strip()
            parsed_args = self._parse_tool_arguments(arguments_text)
            if parsed_args is None:
                diagnostics["invalid_arguments_dropped"] = diagnostics.get(
                    "invalid_arguments_dropped", 0
                ) + 1
                logger.warning(
                    "Skipping OpenRouter tool call '%s' due to invalid JSON arguments. raw=%s",
                    name,
                    arguments_text[:200],
                )
                continue

            base_call_id = str(entry.get("id") or "").strip()
            if not base_call_id:
                generated_tool_call_count += 1
                base_call_id = f"call_generated_{generated_tool_call_count}_{index}"
                diagnostics["missing_id_generated"] = diagnostics.get(
                    "missing_id_generated", 0
                ) + 1
                logger.warning(
                    "OpenRouter tool call '%s' was missing an id. Generated %s.",
                    name,
                    base_call_id,
                )

            call_id, was_duplicate = self._normalize_tool_call_id(
                base_call_id, seen_tool_call_ids
            )
            if was_duplicate:
                diagnostics["duplicate_id_normalized"] = diagnostics.get(
                    "duplicate_id_normalized", 0
                ) + 1
                logger.warning(
                    "OpenRouter emitted duplicate tool call id '%s'. Normalized to '%s'.",
                    base_call_id,
                    call_id,
                )

            ready.append(
                ToolRequest(
                    name=name,
                    parameters=parsed_args,
                    call_id=call_id,
                    requires_confirmation=False,
                )
            )
        return ready, generated_tool_call_count

    @staticmethod
    def _normalize_tool_call_id(
        base_call_id: str, seen_tool_call_ids: Dict[str, int]
    ) -> tuple[str, bool]:
        seen_count = seen_tool_call_ids.get(base_call_id, 0)
        seen_tool_call_ids[base_call_id] = seen_count + 1
        if seen_count == 0:
            return base_call_id, False
        return f"{base_call_id}__dup{seen_count}", True

    @staticmethod
    def _parse_tool_arguments(arguments_text: str) -> Optional[Dict[str, Any]]:
        if not arguments_text:
            return {}
        try:
            parsed = json.loads(arguments_text)
        except json.JSONDecodeError:
            return None
        if isinstance(parsed, dict):
            return parsed
        # Tool schema expects object arguments.
        return {"value": parsed}

    @staticmethod
    def _sanitize_options(options: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(options, dict):
            return {}

        allowed = {
            "temperature",
            "top_p",
            "max_tokens",
            "presence_penalty",
            "frequency_penalty",
            "seed",
            "stop",
            "n",
            "tool_choice",
            "parallel_tool_calls",
            "response_format",
        }
        cleaned: Dict[str, Any] = {k: v for k, v in options.items() if k in allowed}
        if "max_tokens" not in cleaned and "num_predict" in options:
            cleaned["max_tokens"] = options["num_predict"]
        return cleaned

    @staticmethod
    def _normalize_assistant_tool_calls(tool_calls: List[Any]) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []
        for raw in tool_calls:
            if not isinstance(raw, dict):
                continue
            function = raw.get("function")
            if not isinstance(function, dict):
                continue
            name = function.get("name")
            if not name:
                continue
            arguments = function.get("arguments", {})
            if isinstance(arguments, str):
                arguments_text = arguments
            else:
                arguments_text = json.dumps(arguments, ensure_ascii=False, default=str)
            item: Dict[str, Any] = {
                "type": "function",
                "function": {"name": str(name), "arguments": arguments_text},
            }
            if raw.get("id"):
                item["id"] = str(raw["id"])
            normalized.append(item)
        return normalized

    def _serialize_messages(self, messages: List[Message]) -> List[Dict[str, Any]]:
        """
        Convert internal message objects into OpenAI-compatible payload format.

        Important:
        - Preserve assistant tool_calls metadata.
        - Send tool-role messages only when they can be matched to known call ids.
        - Fallback unmatched tool-role messages to assistant text to avoid
          tool-call-id validation errors.
        - Use first-class tool fields (tool_calls, tool_call_id, name) before
          falling back to metadata for backward compatibility.
        """
        serialized: List[Dict[str, Any]] = []
        known_tool_call_ids: Set[str] = set()

        for message in messages:
            metadata = message.metadata or {}
            role = message.role
            content = message.content or ""

            if role == "assistant":
                payload: Dict[str, Any] = {"role": "assistant", "content": content}
                # Use first-class field first, then fall back to metadata
                tool_calls = self._normalize_assistant_tool_calls(
                    message.tool_calls or metadata.get("tool_calls") or []
                )
                if tool_calls:
                    payload["tool_calls"] = tool_calls
                    for tool_call in tool_calls:
                        if tool_call.get("id"):
                            known_tool_call_ids.add(str(tool_call["id"]))
                serialized.append(payload)
                continue

            if role == "tool":
                # Use first-class fields first, then fall back to metadata
                tool_call_id = message.tool_call_id or metadata.get("tool_call_id")
                tool_name = message.name or metadata.get("tool_name")

                if tool_call_id and str(tool_call_id) in known_tool_call_ids:
                    serialized.append(
                        {
                            "role": "tool",
                            "content": content,
                            "tool_call_id": str(tool_call_id),
                        }
                    )
                    continue

                fallback_text = (
                    f"[Tool Result: {tool_name or 'unknown'} | "
                    f"tool_call_id={tool_call_id or 'unmatched'}]\n{content}"
                )
                serialized.append({"role": "assistant", "content": fallback_text})
                continue

            serialized.append({"role": role, "content": content})

        return serialized

    @staticmethod
    def _format_provider_error(exc: Exception) -> str:
        status_code = getattr(exc, "status_code", None)
        body = getattr(exc, "body", None)
        if body is None:
            response = getattr(exc, "response", None)
            body = getattr(response, "text", None) if response is not None else None
            if callable(body):
                try:
                    body = body()
                except Exception:
                    body = None

        snippet = ""
        if body is not None:
            snippet = str(body)[:600]

        if status_code is None:
            return f"OpenRouter request failed: {exc}"

        status_code = int(status_code)
        reason = {
            401: "unauthorized",
            403: "forbidden",
            404: "not_found",
            429: "rate_limited",
        }.get(status_code, "api_error")
        if snippet:
            return (
                f"OpenRouter API error ({status_code} {reason}). "
                f"Response snippet: {snippet}"
            )
        return f"OpenRouter API error ({status_code} {reason})."

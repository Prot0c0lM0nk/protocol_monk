#!/usr/bin/env python3
"""
MLX LM Model Client
===================

Provider implementation for MLX LM server (OpenAI-compatible HTTP API).
"""

from __future__ import annotations

import asyncio
import copy
import json
import logging
from typing import Any, AsyncGenerator, Dict, List, Optional, Union

import aiohttp

from agent.base_model_client import BaseModelClient
from config.static import settings
from exceptions import EmptyResponseError, ModelError, ModelTimeoutError


class MLXLMModelClient(BaseModelClient):
    """
    Provider implementation for MLX LM server.

    This provider uses upstream `mlx_lm.server` OpenAI-compatible endpoints and
    preserves the BaseModelClient contract used by the agent.
    """

    def __init__(
        self, model_name: str, provider_config: Optional[Dict[str, Any]] = None
    ):
        super().__init__(model_name, provider_config)
        self.logger = logging.getLogger(__name__)
        self._session: Optional[aiohttp.ClientSession] = None

        mlx_config = settings.api.providers.get("mlx_lm", {})

        self.base_url = self._normalize_base_url(
            str(
                (provider_config or {}).get("url")
                or mlx_config.get("url")
                or "http://127.0.0.1:8080"
            )
        )

        self.system_prompt = (
            (provider_config or {}).get("system_prompt") if provider_config else None
        )
        self.max_tokens = int(
            (provider_config or {}).get("max_tokens", mlx_config.get("max_tokens", 512))
        )
        self.temperature = float(
            (provider_config or {}).get(
                "temperature", mlx_config.get("temperature", 0.1)
            )
        )
        self.top_p = float(
            (provider_config or {}).get("top_p", mlx_config.get("top_p", 0.9))
        )

    @staticmethod
    def _normalize_base_url(base_url: str) -> str:
        normalized = (base_url or "").strip().rstrip("/")
        if normalized.endswith("/v1/chat/completions"):
            normalized = normalized[: -len("/v1/chat/completions")]
        elif normalized.endswith("/v1"):
            normalized = normalized[: -len("/v1")]
        return normalized or "http://127.0.0.1:8080"

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session and not self._session.closed:
            return self._session

        timeout = aiohttp.ClientTimeout(total=self.timeout)
        self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    @staticmethod
    def _normalize_outbound_tool_arguments(raw_args: Any) -> str:
        """
        MLX server expects function.arguments to be JSON text.
        Coerce unknown/invalid values to '{}' to avoid server-side parse crashes.
        """
        if isinstance(raw_args, dict):
            return json.dumps(raw_args, separators=(",", ":"))
        if raw_args is None:
            return "{}"
        if isinstance(raw_args, str):
            try:
                parsed = json.loads(raw_args)
                if isinstance(parsed, dict):
                    return json.dumps(parsed, separators=(",", ":"))
                return "{}"
            except json.JSONDecodeError:
                return "{}"
        return "{}"

    @staticmethod
    def _build_outbound_messages(
        conversation_context: List[Dict[str, Any]],
    ) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Build OpenAI-compatible outbound messages for MLX server.
        """
        outbound: List[Dict[str, Any]] = []
        dropped_keys = 0
        defaulted_content = 0
        role_counts: Dict[str, int] = {}

        for raw_msg in conversation_context or []:
            if not isinstance(raw_msg, dict):
                continue

            msg = copy.deepcopy(raw_msg)
            role = str(msg.get("role") or "user")
            content = msg.get("content")
            if content is None:
                content = ""
                defaulted_content += 1
            elif not isinstance(content, str):
                content = str(content)

            built: Dict[str, Any] = {"role": role, "content": content}
            consumed_keys = {"role", "content"}

            if role == "assistant":
                raw_tool_calls = msg.get("tool_calls")
                if isinstance(raw_tool_calls, list):
                    normalized_calls: List[Dict[str, Any]] = []
                    for raw_call in raw_tool_calls:
                        if not isinstance(raw_call, dict):
                            continue

                        fn = raw_call.get("function")
                        if not isinstance(fn, dict):
                            continue

                        fn_name = str(fn.get("name") or "").strip()
                        if not fn_name:
                            continue

                        args = MLXLMModelClient._normalize_outbound_tool_arguments(
                            fn.get("arguments")
                        )

                        call: Dict[str, Any] = {
                            "type": "function",
                            "function": {"name": fn_name, "arguments": args},
                        }

                        call_id = raw_call.get("id")
                        if call_id:
                            call["id"] = str(call_id)

                        normalized_calls.append(call)

                    if normalized_calls:
                        built["tool_calls"] = normalized_calls
                        consumed_keys.add("tool_calls")

            if role == "tool":
                tool_call_id = msg.get("tool_call_id")
                if tool_call_id:
                    built["tool_call_id"] = str(tool_call_id)
                    consumed_keys.add("tool_call_id")

            dropped_keys += len([k for k in msg.keys() if k not in consumed_keys])
            outbound.append(built)
            role_counts[role] = role_counts.get(role, 0) + 1

        diagnostics = {
            "message_count": len(outbound),
            "role_counts": role_counts,
            "dropped_keys": dropped_keys,
            "defaulted_empty_content": defaulted_content,
        }
        return outbound, diagnostics

    @staticmethod
    def _normalize_tool_calls(
        tool_calls: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []
        for idx, raw_call in enumerate(tool_calls or []):
            if not isinstance(raw_call, dict):
                continue

            function = raw_call.get("function")
            if not isinstance(function, dict):
                continue

            fn_name = str(function.get("name") or "").strip()
            if not fn_name:
                continue

            raw_args = function.get("arguments")
            if isinstance(raw_args, dict):
                args = json.dumps(raw_args, separators=(",", ":"))
            elif raw_args is None:
                args = ""
            else:
                args = str(raw_args)

            call_id = str(raw_call.get("id") or "").strip() or f"mlx_call_{idx + 1}"

            normalized.append(
                {
                    "id": call_id,
                    "type": str(raw_call.get("type") or "function"),
                    "function": {"name": fn_name, "arguments": args},
                }
            )
        return normalized

    @classmethod
    def _stream_chunk_to_output(
        cls, payload: Dict[str, Any]
    ) -> tuple[Optional[str], Optional[Dict[str, Any]]]:
        """
        Convert an OpenAI-compatible streaming chunk into model output parts.
        """
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            return None, None

        delta = choices[0].get("delta")
        if not isinstance(delta, dict):
            return None, None

        text = delta.get("content")
        text_out = text if isinstance(text, str) and text else None

        raw_tool_calls = delta.get("tool_calls")
        if isinstance(raw_tool_calls, list) and raw_tool_calls:
            tool_calls = cls._normalize_tool_calls(raw_tool_calls)
            if tool_calls:
                return text_out, {"tool_calls": tool_calls}

        return text_out, None

    @classmethod
    def _completion_to_output(
        cls, payload: Dict[str, Any]
    ) -> tuple[Optional[str], Optional[Dict[str, Any]]]:
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            return None, None

        message = choices[0].get("message")
        if not isinstance(message, dict):
            return None, None

        content = message.get("content")
        text_out = content if isinstance(content, str) and content else None

        raw_tool_calls = message.get("tool_calls")
        if isinstance(raw_tool_calls, list) and raw_tool_calls:
            tool_calls = cls._normalize_tool_calls(raw_tool_calls)
            if tool_calls:
                return text_out, {"tool_calls": tool_calls}

        return text_out, None

    async def get_response_async(
        self,
        conversation_context: List[Dict[str, str]],
        stream: bool = True,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> AsyncGenerator[Union[str, Dict], None]:
        messages, diag = self._build_outbound_messages(conversation_context)

        if self.system_prompt:
            messages = [{"role": "system", "content": self.system_prompt}] + messages
            diag["message_count"] = len(messages)
            role_counts = dict(diag["role_counts"])
            role_counts["system"] = role_counts.get("system", 0) + 1
            diag["role_counts"] = role_counts

        self.logger.debug(
            "OUTBOUND_DIAG provider=mlx_lm messages=%d roles=%s dropped_keys=%d defaulted_empty_content=%d",
            diag["message_count"],
            diag["role_counts"],
            diag["dropped_keys"],
            diag["defaulted_empty_content"],
        )

        payload = {
            "model": self.model_name,
            "messages": messages,
            "stream": stream,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "top_p": self.top_p,
        }
        if tools:
            payload["tools"] = tools

        url = f"{self.base_url}/v1/chat/completions"
        session = await self._get_session()

        try:
            async with session.post(url, json=payload) as response:
                if response.status >= 400:
                    body = await response.text()
                    raise ModelError(
                        message=(
                            f"MLX server request failed ({response.status}) at {url}: "
                            f"{body[:300]}"
                        ),
                        details={"provider": "mlx_lm", "model": self.model_name},
                    )

                if stream:
                    while True:
                        raw_line = await response.content.readline()
                        if not raw_line:
                            break
                        line = raw_line.decode("utf-8", errors="ignore").strip()
                        if not line.startswith("data:"):
                            continue

                        data = line[len("data:") :].strip()
                        if not data:
                            continue
                        if data == "[DONE]":
                            break

                        try:
                            chunk_payload = json.loads(data)
                        except json.JSONDecodeError:
                            self.logger.debug(
                                "Skipping non-JSON SSE payload from MLX server: %r",
                                data[:120],
                            )
                            continue

                        text_out, tool_out = self._stream_chunk_to_output(chunk_payload)
                        if text_out:
                            yield text_out
                        if tool_out:
                            yield tool_out
                    return

                response_payload = await response.json(content_type=None)
                text_out, tool_out = self._completion_to_output(response_payload)

                if text_out:
                    yield text_out
                if tool_out:
                    yield tool_out

                if not text_out and not tool_out:
                    raise EmptyResponseError(
                        message="MLX server returned an empty response",
                        details={"provider": "mlx_lm", "model": self.model_name},
                    )

        except asyncio.TimeoutError as exc:
            raise ModelTimeoutError(
                message=(
                    f"Request to MLX server timed out at {url}. "
                    f"Check PROTOCOL_MLX_LM_URL (current: {self.base_url})."
                ),
                timeout_seconds=self.timeout,
                details={"provider": "mlx_lm", "model": self.model_name},
            ) from exc
        except aiohttp.ClientError as exc:
            raise ModelError(
                message=(
                    f"Cannot connect to MLX server at {self.base_url}. "
                    "Ensure mlx_lm.server is running."
                ),
                details={"provider": "mlx_lm", "model": self.model_name},
            ) from exc
        except ModelError:
            raise
        except EmptyResponseError:
            raise
        except Exception as exc:
            raise ModelError(
                message=f"MLX server error: {exc}",
                details={"provider": "mlx_lm", "model": self.model_name},
            ) from exc

    def _prepare_payload(
        self,
        conversation_context: List[Dict[str, str]],
        stream: bool,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        messages, _ = self._build_outbound_messages(conversation_context)
        payload: Dict[str, Any] = {
            "model": self.model_name,
            "messages": messages,
            "stream": stream,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "top_p": self.top_p,
        }
        if tools:
            payload["tools"] = tools
        return payload

    def _extract_content(self, response_data: Dict[str, Any]) -> Optional[str]:
        text, _ = self._completion_to_output(response_data)
        return text

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
        self._session = None

    def supports_tools(self) -> bool:
        return True

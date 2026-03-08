from __future__ import annotations

import json
import logging
from collections import deque
from typing import Any, Deque, Dict, List, Mapping, Optional

from protocol_monk.utils.token_estimation import BetterTokenizerManager

logger = logging.getLogger("UsageLedger")

DEFAULT_RESERVED_COMPLETION_TOKENS = 256
RECENT_USAGE_RECORD_LIMIT = 20


def normalize_jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): normalize_jsonable(val) for key, val in value.items()}
    if isinstance(value, (list, tuple)):
        return [normalize_jsonable(item) for item in value]

    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return normalize_jsonable(model_dump())

    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        return normalize_jsonable(to_dict())

    as_dict = getattr(value, "__dict__", None)
    if isinstance(as_dict, dict):
        return {
            str(key): normalize_jsonable(val)
            for key, val in as_dict.items()
            if not str(key).startswith("_")
        }
    return str(value)


def build_fallback_request_payload(
    messages: List[Any],
    model_name: str,
    tools: Optional[List[Dict[str, Any]]] = None,
    options: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    normalized_messages: List[Dict[str, Any]] = []
    for message in messages:
        role = str(getattr(message, "role", "") or "")
        content = getattr(message, "content", "") or ""
        payload: Dict[str, Any] = {"role": role, "content": content}

        tool_calls = getattr(message, "tool_calls", None)
        if tool_calls:
            payload["tool_calls"] = normalize_jsonable(tool_calls)

        tool_call_id = getattr(message, "tool_call_id", None)
        if tool_call_id:
            payload["tool_call_id"] = str(tool_call_id)

        tool_name = getattr(message, "name", None)
        if tool_name:
            payload["tool_name"] = str(tool_name)

        normalized_messages.append(payload)

    return {
        "model": model_name,
        "messages": normalized_messages,
        "tools": normalize_jsonable(tools or []),
        "options": normalize_jsonable(options or {}),
    }


def build_request_payload_for_provider(
    provider: Any,
    messages: List[Any],
    model_name: str,
    tools: Optional[List[Dict[str, Any]]] = None,
    options: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    builder = getattr(provider, "build_request_payload", None)
    if callable(builder):
        payload = builder(messages, model_name, tools=tools, options=options)
        if isinstance(payload, dict):
            return normalize_jsonable(payload)
    return build_fallback_request_payload(
        messages,
        model_name,
        tools=tools,
        options=options,
    )


def reserved_completion_tokens(
    request_payload: Mapping[str, Any],
    *,
    context_limit: int,
) -> int:
    if context_limit <= 0:
        return 0

    for key in ("max_tokens", "num_predict"):
        value = request_payload.get(key)
        if isinstance(value, int) and value > 0:
            return min(value, context_limit)

    options = request_payload.get("options")
    if isinstance(options, Mapping):
        value = options.get("num_predict")
        if isinstance(value, int) and value > 0:
            return min(value, context_limit)

    return min(DEFAULT_RESERVED_COMPLETION_TOKENS, context_limit)


def normalize_provider_usage(
    raw_metrics: Mapping[str, Any] | None,
) -> Dict[str, Optional[int]]:
    payload = dict(raw_metrics or {})
    provider = str(payload.get("provider", "") or "").strip().lower()

    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None

    usage = payload.get("usage")
    if isinstance(usage, Mapping):
        prompt = usage.get("prompt_tokens")
        if isinstance(prompt, int) and prompt >= 0:
            prompt_tokens = prompt
        completion = usage.get("completion_tokens")
        if isinstance(completion, int) and completion >= 0:
            completion_tokens = completion
        total = usage.get("total_tokens")
        if isinstance(total, int) and total >= 0:
            total_tokens = total

    if provider == "ollama" or "eval_count" in payload or "prompt_eval_count" in payload:
        prompt = payload.get("prompt_eval_count")
        if isinstance(prompt, int) and prompt >= 0:
            prompt_tokens = prompt

        completion = payload.get("eval_count")
        if isinstance(completion, int) and completion >= 0:
            completion_tokens = completion

        if prompt_tokens is not None or completion_tokens is not None:
            total_tokens = int(prompt_tokens or 0) + int(completion_tokens or 0)

    if total_tokens is None and (
        prompt_tokens is not None or completion_tokens is not None
    ):
        total_tokens = int(prompt_tokens or 0) + int(completion_tokens or 0)

    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
    }


class UsageLedger:
    def __init__(self, *, model_name: str):
        self._model_name = str(model_name or "")
        self._tokenizers = BetterTokenizerManager()
        self._recent_records: Deque[Dict[str, Any]] = deque(
            maxlen=RECENT_USAGE_RECORD_LIMIT
        )
        self._last_estimate: Dict[str, Any] | None = None
        self._last_record: Dict[str, Any] | None = None

    async def estimate_request(
        self,
        *,
        request_payload: Mapping[str, Any],
        context_limit: int,
    ) -> Dict[str, Any]:
        self._model_name = str(request_payload.get("model", self._model_name) or self._model_name)
        message_tokens, message_mode = await self._count_json_tokens(
            request_payload.get("messages")
        )
        tool_tokens, tool_mode = await self._count_json_tokens(
            request_payload.get("tools") or []
        )

        prompt_tokens = message_tokens + tool_tokens
        reserve = reserved_completion_tokens(
            request_payload,
            context_limit=context_limit,
        )
        estimate = {
            "provider": str(request_payload.get("provider", "") or ""),
            "model": str(request_payload.get("model", self._model_name) or self._model_name),
            "message_count": len(request_payload.get("messages") or []),
            "tool_count": len(request_payload.get("tools") or []),
            "message_tokens": message_tokens,
            "tool_tokens": tool_tokens,
            "estimated_next_request_tokens": prompt_tokens,
            "reserved_completion_tokens": reserve,
            "context_limit": int(context_limit or 0),
            "within_limit": (
                True
                if int(context_limit or 0) <= 0
                else prompt_tokens + reserve <= int(context_limit)
            ),
            "estimator_mode": message_mode if message_mode == tool_mode else "mixed",
        }
        self._last_estimate = estimate
        return estimate

    def record_usage(
        self,
        *,
        turn_id: str,
        pass_id: str,
        round_index: int,
        raw_metrics: Mapping[str, Any] | None,
        request_estimate: Mapping[str, Any] | None,
    ) -> Dict[str, Any]:
        raw = normalize_jsonable(dict(raw_metrics or {}))
        normalized = normalize_provider_usage(raw)

        provider = str(raw.get("provider", "") or "")
        response_model = str(raw.get("response_model") or raw.get("model") or "")
        request_model = str(raw.get("request_model") or self._model_name or "")

        durations_ms = self._extract_durations_ms(provider, raw)
        total_tokens = normalized.get("total_tokens")
        completion_tokens = normalized.get("completion_tokens")
        total_duration_ms = durations_ms.get("total_duration_ms")
        eval_duration_ms = durations_ms.get("eval_duration_ms")

        ms_per_token = (
            round(total_duration_ms / total_tokens, 3)
            if total_duration_ms and total_tokens
            else None
        )
        tokens_per_second = (
            round(completion_tokens / (eval_duration_ms / 1000.0), 3)
            if eval_duration_ms and completion_tokens
            else None
        )

        estimated_prompt_tokens = None
        reserved_tokens = None
        context_limit = None
        if isinstance(request_estimate, Mapping):
            estimated_prompt_tokens = request_estimate.get("estimated_next_request_tokens")
            reserved_tokens = request_estimate.get("reserved_completion_tokens")
            context_limit = request_estimate.get("context_limit")

        record = {
            "turn_id": turn_id,
            "pass_id": pass_id,
            "round_index": round_index,
            "provider": provider,
            "request_model": request_model,
            "response_model": response_model,
            "prompt_tokens": normalized.get("prompt_tokens"),
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "estimated_prompt_tokens": estimated_prompt_tokens,
            "reserved_completion_tokens": reserved_tokens,
            "context_limit": context_limit,
            "finish_reasons": self._extract_finish_reasons(raw),
            "chunk_count": raw.get("chunk_count"),
            "durations_ms": durations_ms,
            "tool_call_diagnostics": normalize_jsonable(
                raw.get("tool_call_diagnostics") or {}
            ),
            "ms_per_token": ms_per_token,
            "tokens_per_second": tokens_per_second,
            "prompt_token_delta": (
                None
                if estimated_prompt_tokens is None or normalized.get("prompt_tokens") is None
                else int(normalized["prompt_tokens"]) - int(estimated_prompt_tokens)
            ),
            "raw_provider_metrics": raw,
        }
        self._recent_records.append(record)
        self._last_record = record
        return record

    def build_snapshot(
        self,
        *,
        stored_history_tokens: int,
        message_count: int,
        loaded_files_count: int,
        context_limit: int,
        provider_name: str,
        model_name: str,
        working_directory: str,
        state: str,
        auto_confirm: bool,
        request_estimate: Mapping[str, Any] | None = None,
    ) -> Dict[str, Any]:
        estimate = dict(request_estimate or self._last_estimate or {})
        last_record = dict(self._last_record or {})
        recent_records = list(reversed(self._recent_records))

        snapshot = {
            "provider": provider_name,
            "model": model_name,
            "working_directory": working_directory,
            "state": state,
            "stored_history_tokens": int(stored_history_tokens or 0),
            "estimated_next_request_tokens": int(
                estimate.get("estimated_next_request_tokens", 0) or 0
            ),
            "reserved_completion_tokens": int(
                estimate.get("reserved_completion_tokens", 0) or 0
            ),
            "last_prompt_tokens": last_record.get("prompt_tokens"),
            "last_completion_tokens": last_record.get("completion_tokens"),
            "last_total_tokens": last_record.get("total_tokens"),
            "context_limit": int(context_limit or 0),
            "message_count": int(message_count or 0),
            "loaded_files_count": int(loaded_files_count or 0),
            "auto_confirm": bool(auto_confirm),
            "total_tokens": int(stored_history_tokens or 0),
            "latest_record": last_record or None,
            "recent_records": recent_records,
        }
        snapshot["metrics_prompt_summary"] = self.build_model_summary(snapshot)
        return snapshot

    @staticmethod
    def build_model_summary(snapshot: Mapping[str, Any]) -> str:
        return (
            "Runtime metrics summary:\n"
            f"- Stored history tokens: {int(snapshot.get('stored_history_tokens', 0) or 0)}\n"
            f"- Estimated next request tokens: {int(snapshot.get('estimated_next_request_tokens', 0) or 0)}\n"
            f"- Reserved completion tokens: {int(snapshot.get('reserved_completion_tokens', 0) or 0)}\n"
            f"- Last observed prompt tokens: {snapshot.get('last_prompt_tokens')}\n"
            f"- Last observed completion tokens: {snapshot.get('last_completion_tokens')}\n"
            f"- Last observed total tokens: {snapshot.get('last_total_tokens')}"
        )

    async def _count_json_tokens(self, value: Any) -> tuple[int, str]:
        payload = normalize_jsonable(value)
        if payload in (None, [], {}):
            return 0, "empty"

        text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        if not text:
            return 0, "empty"

        try:
            tokenizer = await self._tokenizers.get_tokenizer(self._model_name)
            encoded = tokenizer.encode(text)
            mode = "smart_estimator" if hasattr(tokenizer, "estimator") else "tokenizer"
            return len(encoded), mode
        except Exception as exc:  # pragma: no cover - defensive fallback
            logger.warning("Falling back to character estimate for token count: %s", exc)
            return max(1, len(text) // 4), "chars_div_4"

    @staticmethod
    def _extract_finish_reasons(raw: Mapping[str, Any]) -> List[str]:
        reasons = raw.get("finish_reasons")
        if isinstance(reasons, list):
            return [str(item) for item in reasons if str(item).strip()]

        done_reason = raw.get("done_reason")
        if done_reason:
            return [str(done_reason)]
        return []

    @staticmethod
    def _extract_durations_ms(
        provider: str,
        raw: Mapping[str, Any],
    ) -> Dict[str, float]:
        durations_ms: Dict[str, float] = {}

        if provider == "ollama":
            for source_key, target_key in (
                ("total_duration", "total_duration_ms"),
                ("load_duration", "load_duration_ms"),
                ("prompt_eval_duration", "prompt_eval_duration_ms"),
                ("eval_duration", "eval_duration_ms"),
            ):
                value = raw.get(source_key)
                if isinstance(value, (int, float)) and value >= 0:
                    durations_ms[target_key] = round(float(value) / 1_000_000.0, 3)
            return durations_ms

        for source_key, target_key in (
            ("total_duration_ms", "total_duration_ms"),
            ("eval_duration_ms", "eval_duration_ms"),
        ):
            value = raw.get(source_key)
            if isinstance(value, (int, float)) and value >= 0:
                durations_ms[target_key] = round(float(value), 3)
        return durations_ms

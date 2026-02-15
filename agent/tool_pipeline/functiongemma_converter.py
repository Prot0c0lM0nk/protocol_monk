"""FunctionGemma conversion client for compact token-wrapped tool calls."""

from __future__ import annotations

import ast
import json
import logging
import re
from pathlib import Path
from typing import Dict, Iterable, List, Set
from urllib.error import URLError
from urllib.request import urlopen

from config.static import settings
from .token_protocol import TOOL_CALL_END, TOOL_CALL_START


logger = logging.getLogger(__name__)


class FunctionGemmaConversionError(Exception):
    """Raised when FunctionGemma conversion fails."""


class FunctionGemmaConverter:
    """Converts token-wrapped pythonic calls into canonical action JSON."""

    _PLACEHOLDER_ACTIONS = {"tool_name", "function_name", "tool", "function"}

    def __init__(self):
        self._client = None

    @property
    def converter_prompt_file(self) -> Path:
        return settings.tool_pipeline.function_converter_prompt_file

    def validate_preconditions(self) -> tuple[bool, str]:
        """Check local config/prompt preconditions before enabling mode."""
        if not settings.tool_pipeline.function_model.strip():
            return False, "FunctionGemma model name is empty."
        if not settings.tool_pipeline.function_provider.strip():
            return False, "FunctionGemma provider is empty."
        if not self.converter_prompt_file.exists():
            return (
                False,
                f"Converter prompt file missing: {self.converter_prompt_file}",
            )
        try:
            _ = self.converter_prompt_file.read_text(encoding="utf-8")
        except Exception as exc:  # pylint: disable=broad-exception-caught
            return False, f"Failed to read converter prompt file: {exc}"

        try:
            self._ensure_client()
        except Exception as exc:  # pylint: disable=broad-exception-caught
            return False, f"Failed to initialize FunctionGemma client: {exc}"

        ok, reason = self._check_model_availability()
        if not ok:
            return False, reason

        return True, "ok"

    def _ensure_client(self):
        if self._client is None:
            from agent.model_client import ModelClient

            self._client = ModelClient(
                model_name=settings.tool_pipeline.function_model,
                provider=settings.tool_pipeline.function_provider,
            )
            # Conversion should be deterministic; use tool options profile where possible.
            tool_opts = settings.model_options.tool_options.copy()
            provider_client = getattr(self._client, "_client", None)
            model_options = getattr(provider_client, "model_options", None)
            if isinstance(model_options, dict):
                model_options.update(tool_opts)
        return self._client

    def _check_model_availability(self) -> tuple[bool, str]:
        """
        Best-effort provider-level availability check used at toggle time.
        """
        provider = settings.tool_pipeline.function_provider.strip().lower()
        model_name = settings.tool_pipeline.function_model.strip()
        if provider == "mlx_lm":
            base = (
                str(settings.api.providers.get("mlx_lm", {}).get("url", ""))
                .strip()
                .rstrip("/")
            )
            if base.endswith("/v1/chat/completions"):
                base = base[: -len("/v1/chat/completions")]
            elif base.endswith("/v1"):
                base = base[: -len("/v1")]
            models_url = f"{base or 'http://127.0.0.1:8080'}/v1/models"

            try:
                with urlopen(models_url, timeout=3) as response:  # nosec B310 - local URL
                    payload = response.read().decode("utf-8")
                result = json.loads(payload)
                data = result.get("data", []) if isinstance(result, dict) else []
                available_names = []
                for item in data:
                    if isinstance(item, dict):
                        name = str(item.get("id") or "").strip()
                        if name:
                            available_names.append(name)

                expected = model_name.lower()
                if any(name.lower() == expected for name in available_names):
                    return True, "ok"

                return (
                    False,
                    (
                        "FunctionGemma model is not listed by MLX server /v1/models: "
                        f"{model_name}"
                    ),
                )
            except URLError as exc:
                return False, f"Failed to query MLX server models for FunctionGemma model: {exc}"
            except Exception as exc:  # pylint: disable=broad-exception-caught
                return False, f"Failed to verify MLX server model availability: {exc}"

        if provider != "ollama":
            # Other providers can fail later at request time if unavailable.
            return True, "ok"

        base = settings.api.ollama_url.strip().rstrip("/")
        if base.endswith("/api/chat"):
            base = base[: -len("/api/chat")]
        elif base.endswith("/api/generate"):
            base = base[: -len("/api/generate")]
        elif base.endswith("/api"):
            base = base[: -len("/api")]
        tags_url = f"{base}/api/tags"

        try:
            with urlopen(tags_url, timeout=3) as response:  # nosec B310 - local URL
                payload = response.read().decode("utf-8")
            result = json.loads(payload)
            models = result.get("models", []) if isinstance(result, dict) else []
            available_names = []
            for item in models:
                if isinstance(item, dict):
                    name = str(item.get("name") or item.get("model") or "").strip()
                    if name:
                        available_names.append(name)

            expected = model_name.lower()
            if any(name.lower() == expected for name in available_names):
                return True, "ok"
            if any(name.lower().startswith(f"{expected}:") for name in available_names):
                return True, "ok"
            if any(expected.startswith(f"{name.lower()}:") for name in available_names):
                return True, "ok"

            return (
                False,
                (
                    "FunctionGemma model is not available in local Ollama tags: "
                    f"{model_name}"
                ),
            )
        except URLError as exc:
            return False, f"Failed to query Ollama tags for FunctionGemma model: {exc}"
        except Exception as exc:  # pylint: disable=broad-exception-caught
            return False, f"Failed to verify FunctionGemma model availability: {exc}"

    async def convert_calls(
        self,
        tool_list_block: str,
        tool_call_blocks: Iterable[str],
        latest_user_text: str,
        allowed_tools: Set[str],
    ) -> List[Dict]:
        """Convert wrapped compact tool calls to canonical action dictionaries."""
        calls = [str(block).strip() for block in tool_call_blocks if str(block).strip()]
        if not calls:
            return []

        prompt = self.converter_prompt_file.read_text(encoding="utf-8")
        wrapped_calls = "\n".join(
            f"{TOOL_CALL_START}{call}{TOOL_CALL_END}" for call in calls
        )

        user_payload = (
            f"{tool_list_block}\n"
            f"Latest user message:\n{latest_user_text}\n\n"
            f"Tool call blocks to convert:\n{wrapped_calls}\n"
        )

        client = self._ensure_client()
        chunks: List[str] = []
        try:
            async for chunk in client.get_response_async(
                [
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": user_payload},
                ],
                stream=False,
                tools=None,
            ):
                if isinstance(chunk, dict):
                    raise FunctionGemmaConversionError(
                        "Converter model returned structured tool output; expected strict JSON text."
                    )
                chunks.append(str(chunk or ""))
        except FunctionGemmaConversionError:
            raise
        except Exception as exc:  # pylint: disable=broad-exception-caught
            raise FunctionGemmaConversionError(
                f"Converter model request failed: {exc}"
            ) from exc

        raw = "".join(chunks).strip()
        logger.debug("FunctionGemma raw output preview: %r", raw[:400])
        if not raw:
            raise FunctionGemmaConversionError("Converter model returned empty output.")
        if "```" in raw:
            raise FunctionGemmaConversionError(
                "Converter model returned markdown/code fences; strict JSON required."
            )
        json_candidate = self._extract_first_json_value(raw)
        if json_candidate:
            try:
                parsed = json.loads(json_candidate)
            except json.JSONDecodeError as exc:
                # Some outputs begin with "[" but are actually token-wrapped
                # pythonic calls (e.g. "[|tool_call_start|>...").
                # Try pythonic fallback before hard-failing on JSON parsing.
                parsed = self._parse_pythonic_calls(raw)
                if parsed is None:
                    raise FunctionGemmaConversionError(
                        f"Converter output is not valid JSON: {exc}"
                    ) from exc
        else:
            # Compatibility fallback:
            # Some small converter models emit pythonic function calls instead
            # of JSON (e.g., execute_command(command="pwd")).
            parsed = self._parse_pythonic_calls(raw)
            if parsed is None:
                raise FunctionGemmaConversionError(
                    "Converter output does not contain a valid JSON object/array."
                )

        if isinstance(parsed, dict):
            parsed = [parsed]
        if not isinstance(parsed, list):
            raise FunctionGemmaConversionError(
                "Converter output must be a JSON object or array of objects."
            )

        inferred_from_source = self._infer_actions_from_source_calls(calls)
        actions: List[Dict] = []
        for idx, item in enumerate(parsed):
            if not isinstance(item, dict):
                raise FunctionGemmaConversionError(
                    "Each converter output item must be an object."
                )
            if "error" in item and "action" not in item:
                raise FunctionGemmaConversionError(
                    f"Converter reported error: {item.get('error')}"
                )
            action = str(item.get("action", "")).strip()
            parameters = item.get("parameters", {})

            if not action:
                raise FunctionGemmaConversionError(
                    "Converter output item is missing 'action'."
                )
            if not isinstance(parameters, dict):
                raise FunctionGemmaConversionError(
                    f"Converter output for action '{action}' has non-object parameters."
                )
            if action not in allowed_tools:
                inferred = (
                    inferred_from_source[idx]
                    if idx < len(inferred_from_source)
                    else None
                )
                inferred_action = (
                    str((inferred or {}).get("action", "")).strip()
                    if isinstance(inferred, dict)
                    else ""
                )
                if (
                    action.lower() in self._PLACEHOLDER_ACTIONS
                    and inferred_action in allowed_tools
                ):
                    action = inferred_action
                else:
                    raise FunctionGemmaConversionError(
                        f"Converter output references unknown tool '{action}'."
                    )

            if not parameters and idx < len(inferred_from_source):
                inferred_params = inferred_from_source[idx].get("parameters", {})
                if isinstance(inferred_params, dict):
                    parameters = inferred_params

            if action not in allowed_tools:
                raise FunctionGemmaConversionError(
                    f"Converter output references unknown tool '{action}'."
                )

            actions.append({"action": action, "parameters": parameters})

        logger.debug("FunctionGemma converted %d tool call(s).", len(actions))
        return actions

    @staticmethod
    def _extract_first_json_value(raw: str) -> str:
        """
        Extract first top-level JSON object or array from a possibly noisy text output.
        Keeps strict JSON parsing while tolerating extra wrapper text from small models.
        """
        text = str(raw or "").strip()
        if not text:
            return ""
        if text[0] in "[{":
            return text

        start = -1
        for i, ch in enumerate(text):
            if ch in "[{":
                start = i
                break
        if start < 0:
            return ""

        opener = text[start]
        closer = "]" if opener == "[" else "}"
        depth = 0
        in_str = False
        escape = False

        for j in range(start, len(text)):
            ch = text[j]
            if in_str:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_str = False
                continue

            if ch == '"':
                in_str = True
                continue
            if ch == opener:
                depth += 1
            elif ch == closer:
                depth -= 1
                if depth == 0:
                    return text[start : j + 1]

        return ""

    @classmethod
    def _infer_actions_from_source_calls(cls, calls: List[str]) -> List[Dict]:
        inferred: List[Dict] = []
        for call in calls:
            parsed = cls._parse_pythonic_calls(call)
            if parsed and isinstance(parsed, list):
                inferred.append(parsed[0])
            else:
                inferred.append({})
        return inferred

    @classmethod
    def _parse_pythonic_calls(cls, raw: str) -> List[Dict] | None:
        """
        Parse pythonic function-call output and map to canonical action objects.
        Returns None when no parseable calls are present.
        """
        expressions = cls._extract_call_expressions(raw)
        if not expressions:
            return None

        parsed_calls: List[Dict] = []
        for expression in expressions:
            normalized_expr = re.sub(r"\btrue\b", "True", expression)
            normalized_expr = re.sub(r"\bfalse\b", "False", normalized_expr)
            normalized_expr = re.sub(r"\bnull\b", "None", normalized_expr)

            try:
                node = ast.parse(normalized_expr, mode="eval").body
            except SyntaxError:
                continue
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
                continue
            if node.args:
                raise FunctionGemmaConversionError(
                    "Converter pythonic output must use keyword arguments only."
                )

            parameters: Dict[str, object] = {}
            for kwarg in node.keywords:
                if kwarg.arg is None:
                    raise FunctionGemmaConversionError(
                        "Converter pythonic output contains unsupported **kwargs."
                    )
                parameters[kwarg.arg] = cls._ast_to_value(kwarg.value)

            parsed_calls.append({"action": node.func.id, "parameters": parameters})

        return parsed_calls or None

    @staticmethod
    def _extract_call_expressions(raw: str) -> List[str]:
        text = str(raw or "")
        for token in (
            TOOL_CALL_START,
            TOOL_CALL_END,
            "[|tool_call_start|>",
            "[|tool_call_end|>",
            "|tool_call_start|>",
            "|tool_call_end|>",
            "<start_function_call>",
            "<end_function_call>",
            "<function_calls>",
            "</function_calls>",
        ):
            text = text.replace(token, " ")

        expressions: List[str] = []
        i = 0
        n = len(text)
        while i < n:
            ch = text[i]
            if not (ch.isalpha() or ch == "_"):
                i += 1
                continue

            start = i
            i += 1
            while i < n and (text[i].isalnum() or text[i] == "_"):
                i += 1

            j = i
            while j < n and text[j].isspace():
                j += 1
            if j >= n or text[j] != "(":
                i = j
                continue

            depth = 0
            in_str = False
            quote = ""
            escape = False
            k = j
            while k < n:
                c = text[k]
                if in_str:
                    if escape:
                        escape = False
                    elif c == "\\":
                        escape = True
                    elif c == quote:
                        in_str = False
                    k += 1
                    continue

                if c in ("'", '"'):
                    in_str = True
                    quote = c
                    k += 1
                    continue
                if c == "(":
                    depth += 1
                elif c == ")":
                    depth -= 1
                    if depth == 0:
                        expressions.append(text[start : k + 1].strip())
                        k += 1
                        break
                k += 1

            i = k

        return expressions

    @staticmethod
    def _ast_to_value(node: ast.AST):
        try:
            return ast.literal_eval(node)
        except Exception:  # pylint: disable=broad-exception-caught
            if isinstance(node, ast.Name):
                if node.id == "true":
                    return True
                if node.id == "false":
                    return False
                if node.id == "null":
                    return None
            raise FunctionGemmaConversionError(
                "Converter pythonic output contains unsupported non-literal parameter."
            )

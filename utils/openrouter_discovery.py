"""OpenRouter model-map discovery for user-selected models."""

from __future__ import annotations

import json
import logging
import os
import re
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List
from urllib import error as urllib_error
from urllib import request as urllib_request

from protocol_monk.exceptions.config import ConfigError

logger = logging.getLogger("OpenRouterDiscovery")


class OpenRouterModelDiscovery:
    """Fetch OpenRouter catalog data and update selected model entries."""

    def __init__(
        self,
        models_json_path: Path,
        *,
        base_url: str = "https://openrouter.ai/api/v1",
        api_key: str | None = None,
        timeout_seconds: int = 20,
    ):
        self._models_path = Path(models_json_path)
        self._base_url = str(base_url or "https://openrouter.ai/api/v1").rstrip("/")
        self._api_key = (api_key or os.getenv("OPENROUTER_API_KEY") or "").strip()
        self._timeout_seconds = max(1, int(timeout_seconds))

    def build_updated_config(
        self,
        model_ids: Iterable[str],
        *,
        write_mode: str = "merge",
        default_model: str | None = None,
        force_supports_tools: bool = False,
    ) -> Dict[str, Any]:
        """Build an updated OpenRouter model map for requested model IDs."""
        selected_ids = self._normalize_model_ids(model_ids)
        if not selected_ids:
            raise ConfigError("At least one --model value is required.")

        if write_mode not in {"merge", "replace"}:
            raise ConfigError("write_mode must be 'merge' or 'replace'.")

        existing = self._load_existing_config()
        existing_models = existing.get("models", {})
        if not isinstance(existing_models, dict):
            existing_models = {}

        catalog = self._fetch_catalog()
        catalog_map = self._catalog_by_id(catalog)

        missing = [model_id for model_id in selected_ids if model_id not in catalog_map]
        if missing:
            raise ConfigError(
                "OpenRouter catalog did not contain requested model(s): "
                + ", ".join(missing)
            )

        if write_mode == "merge":
            updated_models = deepcopy(existing_models)
        else:
            updated_models = {}

        timestamp = datetime.now().isoformat()
        for model_id in selected_ids:
            existing_entry = (
                existing_models.get(model_id, {})
                if isinstance(existing_models.get(model_id, {}), dict)
                else {}
            )
            updated_models[model_id] = self._build_model_entry(
                catalog_map[model_id],
                existing_entry=existing_entry,
                discovered_at=timestamp,
                force_supports_tools=force_supports_tools,
            )

        if not updated_models:
            raise ConfigError("Model map cannot be empty after update.")

        resolved_default = self._resolve_default_model(
            default_model=default_model,
            existing_default=existing.get("default_model"),
            selected_ids=selected_ids,
            updated_models=updated_models,
        )

        return {
            "version": "1.0",
            "last_updated": timestamp,
            "default_model": resolved_default,
            "models": updated_models,
            "source": "openrouter",
        }

    def discover_and_update(
        self,
        model_ids: Iterable[str],
        *,
        write_mode: str = "merge",
        default_model: str | None = None,
        force_supports_tools: bool = False,
    ) -> Dict[str, Any]:
        """Build and save an updated OpenRouter model map."""
        config = self.build_updated_config(
            model_ids,
            write_mode=write_mode,
            default_model=default_model,
            force_supports_tools=force_supports_tools,
        )
        self._save_config(config)
        return config

    @staticmethod
    def _normalize_model_ids(model_ids: Iterable[str]) -> List[str]:
        seen = set()
        normalized: List[str] = []
        for raw in model_ids:
            model_id = str(raw or "").strip()
            if not model_id or model_id in seen:
                continue
            normalized.append(model_id)
            seen.add(model_id)
        return normalized

    def _load_existing_config(self) -> Dict[str, Any]:
        if not self._models_path.exists():
            return {"version": "1.0", "models": {}}
        try:
            return json.loads(self._models_path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise ConfigError(
                f"Failed to read existing OpenRouter model map {self._models_path}: {exc}"
            ) from exc

    def _save_config(self, config: Dict[str, Any]) -> None:
        self._models_path.parent.mkdir(parents=True, exist_ok=True)
        self._models_path.write_text(
            json.dumps(config, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        logger.info("Saved OpenRouter model map to %s", self._models_path)

    def _fetch_catalog(self) -> List[Dict[str, Any]]:
        url = f"{self._base_url}/models"
        headers = {"Accept": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        req = urllib_request.Request(url, headers=headers, method="GET")
        try:
            with urllib_request.urlopen(req, timeout=self._timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib_error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise ConfigError(
                f"OpenRouter models request failed ({exc.code}): {body}"
            ) from exc
        except urllib_error.URLError as exc:
            raise ConfigError(
                f"OpenRouter models request failed: {exc.reason}"
            ) from exc
        except json.JSONDecodeError as exc:
            raise ConfigError(
                f"OpenRouter models response is not valid JSON: {exc}"
            ) from exc

        data = payload.get("data")
        if not isinstance(data, list):
            raise ConfigError("OpenRouter models response missing 'data' array.")
        return [item for item in data if isinstance(item, dict)]

    @staticmethod
    def _catalog_by_id(catalog: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        indexed: Dict[str, Dict[str, Any]] = {}
        for item in catalog:
            model_id = str(item.get("id", "") or "").strip()
            if not model_id:
                continue
            indexed[model_id] = item
        return indexed

    @staticmethod
    def _coerce_positive_int(value: Any) -> int | None:
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            return value if value > 0 else None
        if isinstance(value, float):
            coerced = int(value)
            return coerced if coerced > 0 else None
        if isinstance(value, str):
            cleaned = value.strip().replace(",", "")
            if cleaned.isdigit():
                parsed = int(cleaned)
                return parsed if parsed > 0 else None
            match = re.search(r"(\d+)", cleaned)
            if match:
                parsed = int(match.group(1))
                return parsed if parsed > 0 else None
        return None

    @staticmethod
    def _coerce_non_negative_float(value: Any) -> float | None:
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            parsed = float(value)
            return parsed if parsed >= 0 else None
        if isinstance(value, str):
            text = value.strip()
            try:
                parsed = float(text)
                return parsed if parsed >= 0 else None
            except ValueError:
                return None
        return None

    @staticmethod
    def _normalize_labels(raw: Any) -> List[str]:
        if raw is None:
            return []
        if isinstance(raw, str):
            values = [raw]
        elif isinstance(raw, (list, tuple, set)):
            values = list(raw)
        else:
            values = [raw]
        seen = set()
        labels: List[str] = []
        for value in values:
            label = str(value).strip().lower()
            if not label or label in seen:
                continue
            seen.add(label)
            labels.append(label)
        return labels

    @classmethod
    def _extract_context_window(
        cls, catalog_entry: Dict[str, Any], existing_entry: Dict[str, Any]
    ) -> int:
        top_provider = (
            catalog_entry.get("top_provider")
            if isinstance(catalog_entry.get("top_provider"), dict)
            else {}
        )
        candidates = [
            catalog_entry.get("context_length"),
            top_provider.get("context_length"),
            existing_entry.get("context_window"),
        ]
        for candidate in candidates:
            parsed = cls._coerce_positive_int(candidate)
            if parsed is not None:
                return parsed
        return 8192

    @staticmethod
    def _infer_family(catalog_entry: Dict[str, Any], existing_entry: Dict[str, Any]) -> str:
        existing_family = str(existing_entry.get("family", "") or "").strip().lower()
        if existing_family:
            return existing_family

        model_id = str(catalog_entry.get("id", "") or "").strip().lower()
        tail = model_id.split("/", 1)[-1]
        token = re.split(r"[:@]", tail, maxsplit=1)[0]
        token = re.split(r"[-_]", token, maxsplit=1)[0]
        token = token.strip()
        if token:
            return token

        architecture = (
            catalog_entry.get("architecture")
            if isinstance(catalog_entry.get("architecture"), dict)
            else {}
        )
        tokenizer = str(architecture.get("tokenizer", "") or "").strip().lower()
        if tokenizer and tokenizer != "other":
            return tokenizer
        return "unknown"

    @classmethod
    def _infer_support_flags(
        cls,
        catalog_entry: Dict[str, Any],
        existing_entry: Dict[str, Any],
        *,
        force_supports_tools: bool = False,
    ) -> tuple[bool, bool]:
        supported_parameters = cls._normalize_labels(
            catalog_entry.get("supported_parameters")
        )
        params_set = set(supported_parameters)

        text_blob = " ".join(
            [
                str(catalog_entry.get("id", "") or ""),
                str(catalog_entry.get("name", "") or ""),
                str(catalog_entry.get("description", "") or ""),
                str(catalog_entry.get("canonical_slug", "") or ""),
            ]
        ).lower()

        tools_signal = bool(params_set & {"tools", "tool_choice", "parallel_tool_calls"})
        thinking_signal = bool(
            params_set & {"reasoning", "include_reasoning", "reasoning_effort"}
        ) or ("thinking" in text_blob or "reasoning" in text_blob)

        supports_tools = (
            force_supports_tools
            or tools_signal
            or bool(existing_entry.get("supports_tools", False))
        )
        supports_thinking = thinking_signal or bool(
            existing_entry.get("supports_thinking", False)
        )
        return supports_tools, supports_thinking

    @classmethod
    def _infer_capabilities(
        cls, catalog_entry: Dict[str, Any], supports_tools: bool, supports_thinking: bool
    ) -> List[str]:
        architecture = (
            catalog_entry.get("architecture")
            if isinstance(catalog_entry.get("architecture"), dict)
            else {}
        )
        modality = str(architecture.get("modality", "") or "").lower()
        input_modalities = cls._normalize_labels(architecture.get("input_modalities"))
        output_modalities = cls._normalize_labels(architecture.get("output_modalities"))

        has_image = (
            "image" in input_modalities
            or "image" in output_modalities
            or "image" in modality
        )
        has_video = (
            "video" in input_modalities
            or "video" in output_modalities
            or "video" in modality
        )

        capabilities: List[str] = ["completion"]
        if supports_tools:
            capabilities.append("tools")
        if supports_thinking:
            capabilities.append("thinking")
        if has_image:
            capabilities.append("vision")
        if has_video:
            capabilities.append("video")
        return capabilities

    @classmethod
    def _normalize_pricing(cls, catalog_entry: Dict[str, Any]) -> Dict[str, Any]:
        raw_pricing = (
            catalog_entry.get("pricing")
            if isinstance(catalog_entry.get("pricing"), dict)
            else {}
        )
        if not raw_pricing:
            return {}

        raw: Dict[str, str] = {}
        usd_per_token: Dict[str, float] = {}
        usd_per_million_tokens: Dict[str, float] = {}
        for key, value in raw_pricing.items():
            label = str(key or "").strip()
            if not label:
                continue
            raw[label] = str(value)
            parsed = cls._coerce_non_negative_float(value)
            if parsed is None:
                continue
            usd_per_token[label] = parsed
            usd_per_million_tokens[label] = round(parsed * 1_000_000, 6)

        pricing = {"raw": raw}
        if usd_per_token:
            pricing["usd_per_token"] = usd_per_token
            pricing["usd_per_million_tokens"] = usd_per_million_tokens
        return pricing

    @classmethod
    def _build_model_entry(
        cls,
        catalog_entry: Dict[str, Any],
        *,
        existing_entry: Dict[str, Any],
        discovered_at: str,
        force_supports_tools: bool = False,
    ) -> Dict[str, Any]:
        model_id = str(catalog_entry.get("id", "") or "").strip()
        context_window = cls._extract_context_window(catalog_entry, existing_entry)
        family = cls._infer_family(catalog_entry, existing_entry)
        supports_tools, supports_thinking = cls._infer_support_flags(
            catalog_entry,
            existing_entry,
            force_supports_tools=force_supports_tools,
        )
        capabilities = cls._infer_capabilities(
            catalog_entry, supports_tools, supports_thinking
        )
        pricing = cls._normalize_pricing(catalog_entry)

        user_overrides = existing_entry.get("user_overrides", {})
        if not isinstance(user_overrides, dict):
            user_overrides = {}

        model_entry: Dict[str, Any] = {
            "name": model_id,
            "family": family,
            "is_cloud": True,
            "context_window": context_window,
            "supports_thinking": supports_thinking,
            "supports_tools": supports_tools,
            "capabilities": capabilities,
            "parameters": user_overrides.copy(),
            "user_overrides": user_overrides,
            "discovered_at": discovered_at,
            "openrouter_name": str(catalog_entry.get("name", "") or ""),
            "supported_parameters": cls._normalize_labels(
                catalog_entry.get("supported_parameters")
            ),
        }
        if pricing:
            model_entry["pricing"] = pricing
        return model_entry

    @staticmethod
    def _resolve_default_model(
        *,
        default_model: str | None,
        existing_default: Any,
        selected_ids: List[str],
        updated_models: Dict[str, Dict[str, Any]],
    ) -> str:
        if default_model:
            target = str(default_model).strip()
            if target not in updated_models:
                raise ConfigError(
                    f"Requested default model is not present after update: {target}"
                )
            return target

        existing = str(existing_default or "").strip()
        if existing and existing in updated_models:
            return existing

        for model_id in selected_ids:
            if model_id in updated_models:
                return model_id

        return next(iter(updated_models.keys()))

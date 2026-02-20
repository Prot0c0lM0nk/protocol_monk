#!/usr/bin/env python3
"""
Minimal Model Discovery for Ollama Models

Queries Ollama directly using `list` and `show`, extracts actual model metadata,
and persists it with support for user overrides.
"""

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List

from ollama import AsyncClient

logger = logging.getLogger("ModelDiscovery")


class ModelDiscovery:
    def __init__(
        self, models_json_path: Path, ollama_host: str = "http://localhost:11434"
    ):
        self._models_path = models_json_path
        self._client = AsyncClient(host=ollama_host)

    async def discover_and_update(self, force_refresh: bool = False) -> Dict[str, Any]:
        """
        Discover models via Ollama and update local cache.
        Preserves user overrides between runs.
        """
        existing = self._load_existing_config()

        if not force_refresh and self._is_config_fresh(existing):
            logger.info("Using cached model configuration.")
            return existing

        logger.info("Refreshing model configuration from Ollama...")
        model_names = await self._query_ollama_models()
        config = await self._build_config(model_names, existing)
        self._save_config(config)

        logger.info(f"Discovered {len(config['models'])} models.")
        return config

    def _load_existing_config(self) -> Dict[str, Any]:
        """Load existing models.json if present."""
        if self._models_path.exists():
            try:
                with open(self._models_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load config: {e}")
        return {"last_updated": None, "models": {}}

    def _is_config_fresh(self, config: Dict[str, Any], max_age_hours: int = 24) -> bool:
        """Check whether the stored config is still fresh."""
        last_updated_str = config.get("last_updated")
        if not last_updated_str:
            return False
        try:
            last_updated = datetime.fromisoformat(last_updated_str)
            age_hours = (datetime.now() - last_updated).total_seconds() / 3600
            return age_hours < max_age_hours
        except Exception:
            return False

    async def _query_ollama_models(self) -> List[str]:
        """Get list of available model names from Ollama."""
        try:
            response = await self._client.list()
            return [model.model for model in response.models]
        except Exception as e:
            logger.error(f"Ollama query failed: {e}")
            raise

    async def _get_model_details(self, model_name: str) -> Dict[str, Any]:
        """Fetch detailed model info using `show`."""
        try:
            raw = await self._client.show(model_name)
            if hasattr(raw, "model_dump"):
                return raw.model_dump()
            if isinstance(raw, dict):
                return raw
            # Defensive fallback for unexpected client return types.
            return dict(raw)
        except Exception as e:
            logger.warning(f"Could not fetch details for '{model_name}': {e}")
            return {}

    @staticmethod
    def _coerce_positive_int(value: Any) -> int | None:
        """Convert int-like values to positive integers."""
        if value is None:
            return None
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            return value if value > 0 else None
        if isinstance(value, float):
            coerced = int(value)
            return coerced if coerced > 0 else None
        if isinstance(value, str):
            cleaned = value.replace(",", "").strip()
            if not cleaned:
                return None
            if cleaned.isdigit():
                coerced = int(cleaned)
                return coerced if coerced > 0 else None
            match = re.search(r"(\d+)", cleaned)
            if match:
                coerced = int(match.group(1))
                return coerced if coerced > 0 else None
        return None

    @staticmethod
    def _normalize_capabilities(raw: Any) -> List[str]:
        """Normalize capabilities into lowercase unique labels."""
        if raw is None:
            return []

        values: List[Any]
        if isinstance(raw, dict):
            values = [k for k, v in raw.items() if v]
        elif isinstance(raw, (list, tuple, set)):
            values = list(raw)
        elif isinstance(raw, str):
            values = [part.strip() for part in re.split(r"[,\n]+", raw)]
        else:
            values = [str(raw)]

        normalized: List[str] = []
        seen = set()
        for value in values:
            label = str(value).strip().lower()
            if not label or label in seen:
                continue
            normalized.append(label)
            seen.add(label)
        return normalized

    def _extract_capabilities(self, details: Dict[str, Any]) -> List[str]:
        """Extract capability flags from multiple known show() shapes."""
        top_level = self._normalize_capabilities(details.get("capabilities"))
        if top_level:
            return top_level

        nested_details = details.get("details") or {}
        nested = self._normalize_capabilities(nested_details.get("capabilities"))
        if nested:
            return nested

        model_info = details.get("model_info") or {}
        info_caps = self._normalize_capabilities(model_info.get("capabilities"))
        if info_caps:
            return info_caps

        return []

    def _extract_context_length(
        self, details: Dict[str, Any], existing_model: Dict[str, Any]
    ) -> int:
        """Extract context window from known show() payload variants."""
        nested_details = details.get("details") or {}
        model_info = details.get("model_info") or {}

        candidates = [
            details.get("context_length"),
            nested_details.get("context_length"),
            model_info.get("context_length"),
        ]

        for key, value in model_info.items():
            lowered = str(key).lower()
            if lowered.endswith(".context_length") or lowered == "context_length":
                candidates.append(value)

        for candidate in candidates:
            coerced = self._coerce_positive_int(candidate)
            if coerced is not None:
                return coerced

        existing_ctx = self._coerce_positive_int(existing_model.get("context_window"))
        if existing_ctx is not None:
            return existing_ctx

        # Conservative fallback when model metadata is incomplete.
        return 8192

    @staticmethod
    def _extract_family(model_name: str, details: Dict[str, Any]) -> str:
        """Infer family/architecture for grouping and token estimation."""
        nested_details = details.get("details") or {}
        model_info = details.get("model_info") or {}

        direct_candidates = [
            nested_details.get("family"),
            details.get("family"),
            nested_details.get("architecture"),
            details.get("architecture"),
            model_info.get("general.architecture"),
            model_info.get("architecture"),
        ]
        for candidate in direct_candidates:
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip().lower()

        families = nested_details.get("families")
        if isinstance(families, (list, tuple)) and families:
            first = str(families[0]).strip().lower()
            if first:
                return first

        for key in model_info.keys():
            key_text = str(key).strip().lower()
            if key_text.endswith(".context_length"):
                return key_text.split(".")[0]

        base = model_name.split(":", 1)[0]
        return base.split("-", 1)[0].strip().lower() or "unknown"

    @staticmethod
    def _infer_is_cloud(model_name: str, details: Dict[str, Any]) -> bool:
        """Infer whether a model is remote/cloud-hosted."""
        lowered_name = model_name.lower()
        if lowered_name.endswith(":cloud") or "-cloud" in lowered_name:
            return True

        remote_markers = [
            details.get("remote_url"),
            details.get("remote_model"),
            (details.get("details") or {}).get("remote_url"),
            (details.get("details") or {}).get("remote_model"),
        ]
        return any(bool(marker) for marker in remote_markers)

    async def _build_config(
        self, model_names: List[str], existing: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Construct updated model configuration from live data."""
        config = {
            "version": "1.0",
            "last_updated": datetime.now().isoformat(),
            "default_model": "",
            "models": {},
        }

        for name in model_names:
            details = await self._get_model_details(name)
            existing_model = existing.get("models", {}).get(name, {})

            capabilities = self._extract_capabilities(details)
            supports_tools = (
                "tools" in capabilities
                if capabilities
                else bool(existing_model.get("supports_tools", False))
            )
            supports_thinking = (
                "thinking" in capabilities
                if capabilities
                else (
                    bool(existing_model.get("supports_thinking", False))
                    or "thinking" in name.lower()
                )
            )
            context_len = self._extract_context_length(details, existing_model)
            family = self._extract_family(name, details)
            is_cloud = self._infer_is_cloud(name, details)

            # Pull any existing user overrides
            user_overrides = existing_model.get("user_overrides", {})
            if not isinstance(user_overrides, dict):
                user_overrides = {}

            # Assemble final model entry
            model_entry = {
                "name": name,
                "family": family,
                "is_cloud": is_cloud,
                "context_window": context_len,
                "supports_thinking": supports_thinking,
                "supports_tools": supports_tools,
                "capabilities": capabilities,
                "parameters": user_overrides.copy(),
                "user_overrides": user_overrides,
                "discovered_at": datetime.now().isoformat(),
            }

            config["models"][name] = model_entry

        existing_default = existing.get("default_model")
        if existing_default in config["models"]:
            config["default_model"] = existing_default
        elif model_names:
            config["default_model"] = model_names[0]

        return config

    def _save_config(self, config: Dict[str, Any]) -> None:
        """Write updated config to disk."""
        self._models_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._models_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        logger.info(f"Saved model configuration to {self._models_path}")

    def get_model_config(self, model_name: str) -> Dict[str, Any]:
        """Retrieve config for a specific model."""
        config = self._load_existing_config()
        return config.get("models", {}).get(model_name, {})

    def list_available_models(self) -> List[str]:
        """Return list of known model names."""
        config = self._load_existing_config()
        return list(config.get("models", {}).keys())


# Convenience wrapper function
async def discover_models(
    models_json_path: Path,
    ollama_host: str = "http://localhost:11434",
    force_refresh: bool = False,
) -> Dict[str, Any]:
    """
    Main public interface to trigger discovery process.
    """
    discovery = ModelDiscovery(models_json_path, ollama_host)
    return await discovery.discover_and_update(force_refresh)

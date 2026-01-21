#!/usr/bin/env python3
"""
Minimal Model Discovery for Ollama Models

Queries Ollama directly using `list` and `show`, extracts actual model metadata,
and persists it with support for user overrides.
"""

import json
import logging
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
            return await self._client.show(model_name)
        except Exception as e:
            logger.warning(f"Could not fetch details for '{model_name}': {e}")
            return {}

    async def _build_config(
        self, model_names: List[str], existing: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Construct updated model configuration from live data."""
        config = {
            "last_updated": datetime.now().isoformat(),
            "models": {},
        }

        for name in model_names:
            details = await self._get_model_details(name)
            existing_model = existing.get("models", {}).get(name, {})

            # Extract core properties from 'show'
            context_len = (
                details.get("details", {}).get("context_length")
                or existing_model.get("context_window")
                or 2048
            )
            supports_tools = "tools" in details.get("details", {}).get(
                "capabilities", []
            )
            supports_thinking = "thinking" in details.get("details", {}).get(
                "capabilities", []
            )

            # Pull any existing user overrides
            user_overrides = existing_model.get("user_overrides", {})

            # Assemble final model entry
            model_entry = {
                "name": name,
                "context_window": context_len,
                "supports_thinking": supports_thinking,
                "supports_tools": supports_tools,
                "parameters": user_overrides.copy(),  # Start with overrides
                "user_overrides": user_overrides,
            }

            config["models"][name] = model_entry

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

#!/usr/bin/env python3
"""
Model Discovery System for Protocol Monk

Queries Ollama for available models, parses Modelfiles,
and maintains models.json with user override preservation.
"""

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List

from ollama import AsyncClient

logger = logging.getLogger("ModelDiscovery")


class ModelDiscovery:
    """
    Discovers and maintains model configuration from Ollama.

    Design Principles:
    1. Query Ollama for available models
    2. Parse Modelfiles for capabilities
    3. Merge with existing JSON (preserve user overrides)
    4. Persist to disk for fast startup
    """

    # Family detection patterns
    FAMILY_PATTERNS = {
        "qwen": re.compile(r"qwen", re.IGNORECASE),
        "mistral": re.compile(r"mistral|ministral|devstral", re.IGNORECASE),
        "llama": re.compile(r"llama", re.IGNORECASE),
        "gemma": re.compile(r"gemma|rnj", re.IGNORECASE),  # rnj-1 is gemma3
        "deepseek": re.compile(r"deepseek|kimi|cogito", re.IGNORECASE),  # kimi/cogito are deepseek2
        "phi": re.compile(r"phi", re.IGNORECASE),
        "glm": re.compile(r"glm", re.IGNORECASE),
        "gptoss": re.compile(r"gpt-oss", re.IGNORECASE),
        "minimax": re.compile(r"minimax", re.IGNORECASE),
        "gemini": re.compile(r"gemini", re.IGNORECASE),
        "nemotron": re.compile(r"nemotron", re.IGNORECASE),
    }
    # Capability detection from Modelfile
    PARAMETER_PATTERNS = {
        "context_window": re.compile(r"num_ctx\s+(\d+)"),
        "temperature": re.compile(r"temperature\s+([\d.]+)"),
        "top_p": re.compile(r"top_p\s+([\d.]+)"),
        "num_predict": re.compile(r"num_predict\s+(\d+)"),
    }

    # Family defaults (fallback if Modelfile doesn't specify)
    FAMILY_DEFAULTS = {
        "qwen": {
            "supports_thinking": True,
            "supports_tools": True,
            "avg_chars_per_token": 3.8,
            "default_params": {
                "temperature": 0.7,
                "top_p": 0.9,
                "num_predict": 4096,
            },
        },
        "mistral": {
            "supports_thinking": False,
            "supports_tools": True,
            "avg_chars_per_token": 4.0,
            "default_params": {
                "temperature": 0.7,
                "top_p": 0.95,
                "num_predict": 8192,
            },
        },
        "llama": {
            "supports_thinking": False,
            "supports_tools": True,
            "avg_chars_per_token": 4.2,
            "default_params": {
                "temperature": 0.8,
                "top_p": 0.9,
                "num_predict": 2048,
            },
        },
        "deepseek": {
            "supports_thinking": True,
            "supports_tools": True,
            "avg_chars_per_token": 3.8,
            "default_params": {
                "temperature": 0.6,
                "top_p": 0.9,
                "num_predict": 4096,
            },
        },
        "gemma": {
            "supports_thinking": False,
            "supports_tools": True,
            "avg_chars_per_token": 4.0,
            "default_params": {
                "temperature": 0.7,
                "top_p": 0.9,
                "num_predict": 2048,
            },
        },
        "phi": {
            "supports_thinking": False,
            "supports_tools": True,
            "avg_chars_per_token": 4.0,
            "default_params": {
                "temperature": 0.7,
                "top_p": 0.9,
                "num_predict": 2048,
            },
        },
        "glm": {
            "supports_thinking": False,
            "supports_tools": True,
            "avg_chars_per_token": 4.0,
            "default_params": {
                "temperature": 0.7,
                "top_p": 0.9,
                "num_predict": 8192,
            },
        },
        "gptoss": {
            "supports_thinking": False,
            "supports_tools": True,
            "avg_chars_per_token": 4.0,
            "default_params": {
                "temperature": 0.7,
                "top_p": 0.9,
                "num_predict": 4096,
            },
        },
        "minimax": {
            "supports_thinking": False,
            "supports_tools": True,
            "avg_chars_per_token": 4.0,
            "default_params": {
                "temperature": 0.7,
                "top_p": 0.9,
                "num_predict": 4096,
            },
        },
        "gemini": {
            "supports_thinking": False,
            "supports_tools": True,
            "avg_chars_per_token": 4.0,
            "default_params": {
                "temperature": 0.7,
                "top_p": 0.9,
                "num_predict": 8192,
            },
        },
        "nemotron": {
            "supports_thinking": False,
            "supports_tools": True,
            "avg_chars_per_token": 4.0,
            "default_params": {
                "temperature": 0.7,
                "top_p": 0.9,
                "num_predict": 4096,
            },
        },
    }

    def __init__(
        self, models_json_path: Path, ollama_host: str = "http://localhost:11434"
    ):
        self._models_path = models_json_path
        self._ollama_host = ollama_host
        self._client = AsyncClient(host=ollama_host)

    async def discover_and_update(self, force_refresh: bool = False) -> Dict[str, Any]:
        """
        Main entry point: Discover models and update JSON file.

        Args:
            force_refresh: If True, query Ollama even if JSON exists and is recent

        Returns:
            The complete model configuration dictionary
        """
        # 1. Load existing config (if any)
        existing_config = self._load_existing_config()

        # 2. Check if we need to refresh
        if not force_refresh and self._is_config_fresh(existing_config):
            logger.info("Using existing model configuration (fresh)")
            return existing_config

        # 3. Query Ollama for available models
        logger.info("Discovering models from Ollama...")
        ollama_models = await self._query_ollama_models()

        # 4. Build new config
        new_config = await self._build_config(ollama_models, existing_config)

        # 5. Persist to disk
        self._save_config(new_config)

        logger.info(f"Model discovery complete: {len(new_config['models'])} models")
        return new_config

    def _load_existing_config(self) -> Dict[str, Any]:
        """Load existing models.json if it exists."""
        if not self._models_path.exists():
            return self._create_empty_config()

        try:
            with open(self._models_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load existing config: {e}")
            return self._create_empty_config()

    def _create_empty_config(self) -> Dict[str, Any]:
        """Create an empty config structure."""
        return {
            "version": "1.0",
            "last_updated": None,
            "default_model": None,
            "families": self.FAMILY_DEFAULTS.copy(),
            "models": {},
        }

    def _is_config_fresh(self, config: Dict[str, Any], max_age_hours: int = 24) -> bool:
        """Check if existing config is recent enough."""
        if not config.get("last_updated"):
            return False

        try:
            last_updated = datetime.fromisoformat(config["last_updated"])
            age_hours = (datetime.now() - last_updated).total_seconds() / 3600
            return age_hours < max_age_hours
        except Exception:
            return False

    async def _query_ollama_models(self) -> List[Any]:
        """Query Ollama for list of available models."""
        try:
            response = await self._client.list()
            # SDK returns ListResponse object with .models attribute (Pydantic model)
            return response.models
        except Exception as e:
            logger.error(f"Failed to query Ollama: {e}")
            raise

    async def _build_config(
        self, ollama_models: List[Dict[str, Any]], existing_config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Build new config from Ollama data, preserving user overrides."""
        new_config = self._create_empty_config()

        # Preserve families from existing (user may have customized)
        if existing_config.get("families"):
            new_config["families"].update(existing_config["families"])

        # Process each model
        for ollama_model in ollama_models:
            # SDK returns Pydantic model objects, not dicts
            model_name = ollama_model.model
            logger.debug(f"Processing model: {model_name}")

            # Get detailed info from Ollama
            model_info = await self._get_model_info(model_name)

            # Build model config
            model_config = self._build_model_config(
                model_name, model_info, existing_config
            )

            # Add to models dict
            new_config["models"][model_name] = model_config

        # Preserve default_model if set
        if existing_config.get("default_model"):
            new_config["default_model"] = existing_config["default_model"]
        elif new_config["models"]:
            # Set first model as default
            new_config["default_model"] = list(new_config["models"].keys())[0]

        # Update timestamp
        new_config["last_updated"] = datetime.now().isoformat()

        return new_config

    async def _get_model_info(self, model_name: str) -> Dict[str, Any]:
        """Get detailed model info from Ollama (including Modelfile)."""
        try:
            info = await self._client.show(model_name)
            return info
        except Exception as e:
            logger.warning(f"Failed to get details for {model_name}: {e}")
            return {}

    def _build_model_config(
        self,
        model_name: str,
        model_info: Dict[str, Any],
        existing_config: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Build config for a single model, preserving user overrides."""
        # 1. Detect family
        family = self._detect_family(model_name)

        # 2. Get family defaults
        family_config = self.FAMILY_DEFAULTS.get(family, self.FAMILY_DEFAULTS["llama"])

        # 3. Parse Modelfile for capabilities
        modelfile = model_info.get("modelfile", "")
        parsed_params = self._parse_modelfile(modelfile)

        # 4. Build parameters (merge family defaults with Modelfile)
        parameters = {**family_config["default_params"], **parsed_params}

        # 5. Preserve user overrides from existing config
        existing_model = existing_config.get("models", {}).get(model_name, {})
        user_overrides = existing_model.get("user_overrides", {})

        # Apply user overrides (they win)
        final_parameters = {**parameters, **user_overrides}

        # 6. Build final config
        return {
            "name": model_name,
            "family": family,
            "context_window": parsed_params.get("context_window", 8192),
            "supports_thinking": family_config["supports_thinking"],
            "supports_tools": family_config["supports_tools"],
            "parameters": final_parameters,
            "discovered_at": datetime.now().isoformat(),
            "user_overrides": user_overrides,
        }

    def _detect_family(self, model_name: str) -> str:
        """Detect model family from name."""
        for family, pattern in self.FAMILY_PATTERNS.items():
            if pattern.search(model_name):
                return family
        return "llama"  # Default fallback

    def _parse_modelfile(self, modelfile: str) -> Dict[str, Any]:
        """Parse Modelfile for parameters."""
        params = {}

        for param_name, pattern in self.PARAMETER_PATTERNS.items():
            match = pattern.search(modelfile)
            if match:
                value = match.group(1)
                # Convert to appropriate type
                if param_name in ["temperature", "top_p"]:
                    params[param_name] = float(value)
                else:
                    params[param_name] = int(value)

        return params

    def _save_config(self, config: Dict[str, Any]) -> None:
        """Save config to JSON file."""
        self._models_path.parent.mkdir(parents=True, exist_ok=True)

        with open(self._models_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)

        logger.info(f"Saved model configuration to {self._models_path}")

    def get_model_config(self, model_name: str) -> Optional[Dict[str, Any]]:
        """Get configuration for a specific model."""
        config = self._load_existing_config()
        return config.get("models", {}).get(model_name)

    def get_family_config(self, family: str) -> Optional[Dict[str, Any]]:
        """Get configuration for a model family."""
        config = self._load_existing_config()
        return config.get("families", {}).get(family)

    def list_available_models(self) -> List[str]:
        """List all discovered model names."""
        config = self._load_existing_config()
        return list(config.get("models", {}).keys())


# Convenience function for quick access
async def discover_models(
    models_json_path: Path,
    ollama_host: str = "http://localhost:11434",
    force_refresh: bool = False,
) -> Dict[str, Any]:
    """
    Discover models and return configuration.

    This is the main entry point for external usage.
    """
    discovery = ModelDiscovery(models_json_path, ollama_host)
    return await discovery.discover_and_update(force_refresh)

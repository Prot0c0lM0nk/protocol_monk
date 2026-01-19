# protocol_monk/config/settings.py
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, model_validator
from pathlib import Path
import logging
from typing import Optional, Dict, Any
from datetime import datetime
from protocol_monk.exceptions.config import ConfigError
from protocol_monk.utils.model_discovery import discover_models

logger = logging.getLogger("Settings")


class Settings(BaseSettings):
    # === Environment Variables (CLEAN NAMES) ===
    workspace: Path
    system_prompt_path: Path
    log_level: str
    ollama_host: str = "http://localhost:11434"
    ollama_api_key: Optional[str] = None
    tool_timeout: int = 60
    pruning_threshold: float = 0.8

    # Note: model_family, context_window_limit, and active_model_config
    # are now computed from model discovery, not hardcoded
    # === Computed Fields ===
    system_prompt: Optional[str] = None
    active_model_config: Optional[Dict[str, Any]] = None

    # === Pydantic V2 Configuration ===
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        # NO prefix - clean names match exactly
        extra="ignore",
        case_sensitive=False,
    )

    # Model discovery fields
    models_json_path: Path = Field(default=Path("protocol_monk/config/models.json"))
    force_model_discovery: bool = Field(default=False, env="FORCE_MODEL_DISCOVERY")
    active_model_alias: str = Field(default="", env="ACTIVE_MODEL_ALIAS")

    # Computed fields
    models_config: Optional[Dict[str, Any]] = None  # Will be loaded from models.json
    # === Model Validator ===

    @model_validator(mode="after")
    def validate_and_compute(self) -> "Settings":
        """Validate and compute derived fields."""

        # 1. Validate workspace exists
        if not self.workspace.exists():
            raise ConfigError(f"Workspace directory does not exist: {self.workspace}")

        # 2. Load system prompt
        if not self.system_prompt_path.exists():
            raise ConfigError(
                f"System prompt file not found: {self.system_prompt_path}"
            )

        try:
            self.system_prompt = self.system_prompt_path.read_text(
                encoding="utf-8"
            ).strip()
            if not self.system_prompt:
                raise ConfigError(
                    f"System prompt file is empty: {self.system_prompt_path}"
                )
        except Exception as e:
            raise ConfigError(f"Failed to read system prompt: {e}")

        # 3. Validate log level
        if self.log_level.upper() not in logging._nameToLevel:
            raise ConfigError(f"Invalid log level: {self.log_level}")
        self.log_level = self.log_level.upper()

        # Note: Model discovery is now async and called separately via initialize()
        # We set minimal defaults here that will be overridden by discovery
        self._active_model_name = "llama2"
        self._active_model_config_dict = {}

        return self

    async def initialize(self) -> None:
        """
        Async initialization for model discovery.
        Call this after creating Settings instance.
        """
        await self._discover_models()

    async def _discover_models(self) -> None:
        """Discover models from Ollama and load configuration."""
        try:
            logger.info("Discovering models from Ollama...")

            # Run discovery
            model_config = await discover_models(
                models_json_path=self.models_json_path,
                ollama_host=self.ollama_host,
                force_refresh=self.force_model_discovery,
            )

            self.models_config = model_config

            # Set active model from alias
            if self.active_model_alias:
                self._set_active_model(self.active_model_alias)
            elif model_config.get("default_model"):
                self._set_active_model(model_config["default_model"])

            logger.info(
                f"Model discovery complete. Active model: {self.active_model_name}"
            )

        except Exception as e:
            logger.error(f"Model discovery failed: {e}")
            # Fall back to minimal config
            self.models_config = self._create_fallback_model_config()
            
    def _set_active_model(self, model_alias: str) -> None:
        """Set the active model from alias or name."""
        if not self.models_config:
            return

        models = self.models_config.get("models", {})

        # Direct match
        if model_alias in models:
            self._active_model_config = models[model_alias]
            self.active_model_name = model_alias
            return

        # Try to find by partial match
        for name, config in models.items():
            if model_alias in name:
                self._active_model_config = config
                self.active_model_name = name
                return
            
        logger.warning(f"Model '{model_alias}' not found. Using default.")
        default = self.models_config.get("default_model")
        if default and default in models:
            self._active_model_config = models[default]
            self.active_model_name = default
            
    def _create_fallback_model_config(self) -> Dict[str, Any]:
        """Create minimal fallback config if discovery fails."""
        return {
            "version": "1.0",
            "last_updated": datetime.now().isoformat(),
            "default_model": "llama2",
            "families": {
                "llama": {
                    "supports_thinking": False,
                    "supports_tools": True,
                    "avg_chars_per_token": 4.0,
                    "default_params": {
                        "temperature": 0.7,
                        "top_p": 0.9,
                        "num_predict": 2048,
                    },
                }
            },
            "models": {
                "llama2": {
                    "name": "llama2",
                    "family": "llama",
                    "context_window": 4096,
                    "supports_thinking": False,
                    "supports_tools": True,
                    "parameters": {
                        "temperature": 0.7,
                        "top_p": 0.9,
                        "num_predict": 2048,
                    },
                    "discovered_at": datetime.now().isoformat(),
                    "user_overrides": {},
                }
            },
        }

    # === Convenience Properties (for code that expects specific names) ===

    @property
    def workspace_root(self) -> Path:
        """Alias for workspace - matches existing code."""
        return self.workspace

    @property
    def tool_timeout_seconds(self) -> int:
        """Alias for tool_timeout - matches existing code."""
        return self.tool_timeout

    @property
    def active_model_name(self) -> str:
        """Get the active model name."""
        return getattr(self, "_active_model_name", "llama2")

    @active_model_name.setter
    def active_model_name(self, value: str) -> None:
        self._active_model_name = value

    @property
    def _active_model_config(self) -> Dict[str, Any]:
        """Get the active model configuration."""
        return getattr(self, "_active_model_config_dict", {})

    @_active_model_config.setter
    def _active_model_config(self, value: Dict[str, Any]) -> None:
        self._active_model_config_dict = value

    @property
    def model_family(self) -> str:
        """Get the active model family."""
        return self._active_model_config.get("family", "llama")

    @property
    def context_window_limit(self) -> int:
        """Get the active model's context window."""
        return self._active_model_config.get("context_window", 8000)

    @property
    def model_parameters(self) -> Dict[str, Any]:
        """Get the active model's default parameters."""
        return self._active_model_config.get("parameters", {})


# === Backward compatibility ===
def load_settings(base_path: Optional[Path] = None) -> Settings:
    """Legacy function - just creates Settings."""
    import os
    from pathlib import Path

    if base_path is not None:
        # Handle relative paths
        prompt_path = os.getenv("SYSTEM_PROMPT_PATH")
        if prompt_path and not Path(prompt_path).is_absolute():
            resolved = (base_path / prompt_path).resolve()
            os.environ["SYSTEM_PROMPT_PATH"] = str(resolved)

    return Settings()

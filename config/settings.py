# protocol_monk/config/settings.py
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, model_validator
from pathlib import Path
import logging
from typing import Optional, Dict, Any, ClassVar
from protocol_monk.exceptions.config import ConfigError


class Settings(BaseSettings):
    # === Environment Variables (CLEAN NAMES) ===
    workspace: Path
    system_prompt_path: Path
    log_level: str
    model_family: str = "qwen"
    ollama_host: str = "http://localhost:11434"
    ollama_api_key: Optional[str] = None
    context_window_limit: int = 8000
    pruning_threshold: float = 0.8
    tool_timeout: int = 60

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

        # 4. Validate context window
        if self.context_window_limit < 1000:
            raise ConfigError(f"Context window too small: {self.context_window_limit}")

        # 5. Compute model config
        model_configs = {
            "qwen": {"avg_chars_per_token": 3.8, "pruning_strategy": "aggressive"},
            "gpt": {"avg_chars_per_token": 4.0, "pruning_strategy": "conservative"},
            "claude": {"avg_chars_per_token": 4.2, "pruning_strategy": "balanced"},
        }

        base = model_configs.get(self.model_family, model_configs["qwen"])
        self.active_model_config = {
            **base,
            "context_window": self.context_window_limit,
            "family": self.model_family,
            "pruning_target": int(self.context_window_limit * self.pruning_threshold),
        }

        return self

    # === Convenience Properties (for code that expects specific names) ===

    @property
    def workspace_root(self) -> Path:
        """Alias for workspace - matches existing code."""
        return self.workspace

    @property
    def tool_timeout_seconds(self) -> int:
        """Alias for tool_timeout - matches existing code."""
        return self.tool_timeout


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

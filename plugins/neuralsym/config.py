"""NeuralSym settings and loader."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .workspace import resolve_state_dir, resolve_workspace_id, resolve_workspace_root


class _NeuralSymEnvSettings(BaseSettings):
    """Environment-driven NeuralSym overrides."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    enabled: bool = Field(default=False, validation_alias="NEURALSYM_ENABLED")
    provider: str | None = Field(default=None, validation_alias="NEURALSYM_PROVIDER")
    model: str | None = Field(default=None, validation_alias="NEURALSYM_MODEL")
    prefer_local_provider: bool = Field(
        default=True,
        validation_alias="NEURALSYM_PREFER_LOCAL_PROVIDER",
    )
    allow_openrouter_fallback: bool = Field(
        default=False,
        validation_alias="NEURALSYM_ALLOW_OPENROUTER_FALLBACK",
    )
    fallback_model: str | None = Field(
        default=None,
        validation_alias="NEURALSYM_FALLBACK_MODEL",
    )
    batch_window_seconds: float = Field(
        default=0.25,
        validation_alias="NEURALSYM_BATCH_WINDOW_SECONDS",
    )
    advice_token_budget: int = Field(
        default=256,
        validation_alias="NEURALSYM_ADVICE_TOKEN_BUDGET",
    )
    workspace_state_dirname: str = Field(
        default=".protocol_monk/neuralsym",
        validation_alias="NEURALSYM_WORKSPACE_STATE_DIRNAME",
    )
    max_pending_observations: int = Field(
        default=256,
        validation_alias="NEURALSYM_MAX_PENDING_OBSERVATIONS",
    )
    log_level: str = Field(default="INFO", validation_alias="NEURALSYM_LOG_LEVEL")


class NeuralSymSettings(BaseModel):
    """Resolved NeuralSym runtime settings."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    provider: str | None = None
    model: str | None = None
    prefer_local_provider: bool = True
    allow_openrouter_fallback: bool = False
    fallback_model: str | None = None
    batch_window_seconds: float = 0.25
    advice_token_budget: int = 256
    workspace_state_dirname: str = ".protocol_monk/neuralsym"
    max_pending_observations: int = 256
    log_level: str = "INFO"
    workspace_root: Path
    workspace_id: str
    state_dir: Path
    ollama_host: str = "http://localhost:11434"
    ollama_api_key: str | None = None
    openrouter_api_key: str | None = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    @model_validator(mode="after")
    def validate_runtime_settings(self) -> "NeuralSymSettings":
        if self.provider is not None:
            self.provider = self.provider.strip().lower() or None
        if self.provider not in {None, "ollama", "openrouter"}:
            raise ValueError("NeuralSym provider must be 'ollama', 'openrouter', or unset.")
        if self.batch_window_seconds < 0:
            raise ValueError("NeuralSym batch_window_seconds must be >= 0.")
        if self.advice_token_budget < 1:
            raise ValueError("NeuralSym advice_token_budget must be >= 1.")
        if self.max_pending_observations < 1:
            raise ValueError("NeuralSym max_pending_observations must be >= 1.")
        return self


def load_neuralsym_settings(host_settings: Any) -> NeuralSymSettings:
    """Resolve NeuralSym settings from environment plus host settings."""

    env = _NeuralSymEnvSettings()
    workspace_root = resolve_workspace_root(
        getattr(host_settings, "workspace_root", getattr(host_settings, "workspace", "."))
    )
    workspace_id = resolve_workspace_id(workspace_root)
    state_dir = resolve_state_dir(workspace_root, env.workspace_state_dirname)

    return NeuralSymSettings(
        enabled=env.enabled,
        provider=env.provider,
        model=env.model,
        prefer_local_provider=env.prefer_local_provider,
        allow_openrouter_fallback=env.allow_openrouter_fallback,
        fallback_model=env.fallback_model,
        batch_window_seconds=env.batch_window_seconds,
        advice_token_budget=env.advice_token_budget,
        workspace_state_dirname=env.workspace_state_dirname,
        max_pending_observations=env.max_pending_observations,
        log_level=env.log_level,
        workspace_root=workspace_root,
        workspace_id=workspace_id,
        state_dir=state_dir,
        ollama_host=str(getattr(host_settings, "ollama_host", "http://localhost:11434")),
        ollama_api_key=getattr(host_settings, "ollama_api_key", None),
        openrouter_api_key=getattr(host_settings, "openrouter_api_key", None),
        openrouter_base_url=str(
            getattr(host_settings, "openrouter_base_url", "https://openrouter.ai/api/v1")
        ),
    )

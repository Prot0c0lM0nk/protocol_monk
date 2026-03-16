# protocol_monk/config/settings.py
from __future__ import annotations

import logging
import os
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from pydantic import Field, PrivateAttr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from protocol_monk.exceptions.config import ConfigError
from protocol_monk.utils.model_discovery import discover_models
from protocol_monk.utils.openrouter_model_map import (
    load_or_initialize_openrouter_model_map,
)

logger = logging.getLogger("Settings")


@dataclass
class ResolvedPaths:
    project_root: Path
    env_file: Path
    workspace_root: Path
    system_prompt_path: Path
    state_home: Path
    ollama_models_json: Path
    openrouter_models_json: Path
    openrouter_example_json: Path
    skills_root: Path
    scratch_root: Path


def _resolve_path(value: Path | str, project_root: Path) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = project_root / path
    return path.resolve(strict=False)


def _parse_env_file_keys(path: Path) -> set[str]:
    if not path.exists():
        return set()

    keys: set[str] = set()
    try:
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _value = line.split("=", 1)
            key = key.strip()
            if key:
                keys.add(key)
    except OSError:
        return set()
    return keys


class Settings(BaseSettings):
    # === Environment Variables (CLEAN NAMES) ===
    workspace: Path = Field(default=Path("."))
    system_prompt_path: Path = Field(default=Path("protocol_monk/system_prompt.txt"))
    log_level: str = "INFO"
    llm_provider: str = "ollama"
    ollama_host: str = "http://localhost:11434"
    ollama_api_key: Optional[str] = None
    openrouter_api_key: Optional[str] = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    tool_timeout: int = 60
    document_vision_enabled: bool = Field(
        default=True, validation_alias="DOCUMENT_VISION_ENABLED"
    )
    document_vision_model: str = Field(
        default="", validation_alias="DOCUMENT_VISION_MODEL"
    )
    pruning_threshold: float = 0.8
    trace_max_sessions: int = 200
    trace_max_total_mb: int = 250

    # === Computed Fields ===
    system_prompt: Optional[str] = None
    active_model_config: Optional[Dict[str, Any]] = None
    project_root: Path = Field(default_factory=Path.cwd, exclude=True)
    env_file_path: Path = Field(default=Path(".env"), exclude=True)
    resolved_paths: Optional[ResolvedPaths] = Field(default=None, exclude=True)
    last_model_load_error: Optional[str] = Field(default=None, exclude=True)

    # === Pydantic V2 Configuration ===
    model_config = SettingsConfigDict(
        env_file=None,
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Model discovery fields
    models_json_path: Path = Field(
        default=Path("~/.protocol_monk/providers/ollama/models.json"),
        validation_alias="MODELS_JSON_PATH",
    )
    openrouter_models_json_path: Path = Field(
        default=Path("protocol_monk/config/openrouter_models.json"),
        validation_alias="OPENROUTER_MODELS_JSON_PATH",
    )
    force_model_discovery: bool = Field(
        default=False, validation_alias="FORCE_MODEL_DISCOVERY"
    )
    active_model_alias: str = Field(default="", validation_alias="ACTIVE_MODEL_ALIAS")

    # Computed fields
    models_config: Optional[Dict[str, Any]] = None

    _models_json_path_overridden: bool = PrivateAttr(default=False)
    _openrouter_models_json_path_overridden: bool = PrivateAttr(default=False)

    @model_validator(mode="after")
    def validate_and_compute(self) -> "Settings":
        """Normalize bootstrap values and resolve deterministic paths."""
        self.project_root = Path(self.project_root).expanduser().resolve(strict=False)
        self.env_file_path = _resolve_path(self.env_file_path, self.project_root)

        self.workspace = _resolve_path(self.workspace, self.project_root)
        self.system_prompt_path = _resolve_path(
            self.system_prompt_path, self.project_root
        )
        self.models_json_path = _resolve_path(self.models_json_path, self.project_root)
        self.openrouter_models_json_path = _resolve_path(
            self.openrouter_models_json_path, self.project_root
        )

        if self.log_level.upper() not in logging._nameToLevel:
            raise ConfigError(f"Invalid log level: {self.log_level}")
        self.log_level = self.log_level.upper()

        normalized_provider = (self.llm_provider or "ollama").strip().lower()
        if normalized_provider not in {"ollama", "openrouter"}:
            raise ConfigError(
                "Invalid llm_provider value. Expected 'ollama' or 'openrouter'. "
                f"Got: {self.llm_provider}"
            )
        self.llm_provider = normalized_provider

        if self.trace_max_sessions < 1:
            raise ConfigError("TRACE_MAX_SESSIONS must be >= 1.")
        if self.trace_max_total_mb < 1:
            raise ConfigError("TRACE_MAX_TOTAL_MB must be >= 1.")

        state_home = Path.home().expanduser().resolve(strict=False) / ".protocol_monk"
        self.resolved_paths = ResolvedPaths(
            project_root=self.project_root,
            env_file=self.env_file_path,
            workspace_root=self.workspace,
            system_prompt_path=self.system_prompt_path,
            state_home=state_home,
            ollama_models_json=self.models_json_path,
            openrouter_models_json=self.openrouter_models_json_path,
            openrouter_example_json=(
                self.project_root / "protocol_monk" / "config" / "openrouter_models.example.json"
            ).resolve(strict=False),
            skills_root=(self.project_root / "skills").resolve(strict=False),
            scratch_root=self.workspace,
        )

        if self.llm_provider == "openrouter":
            self._active_model_name = "mistralai/ministral-14b-2512"
        else:
            self._active_model_name = "llama2"
        self._active_model_config_dict = {}

        return self

    def mark_path_overrides(self, env_keys: set[str]) -> None:
        self._models_json_path_overridden = "MODELS_JSON_PATH" in env_keys
        self._openrouter_models_json_path_overridden = (
            "OPENROUTER_MODELS_JSON_PATH" in env_keys
        )

    def apply_session_choices(
        self,
        *,
        provider: str | None = None,
        model: str | None = None,
        workspace: str | Path | None = None,
    ) -> None:
        """Apply session-scoped overrides after setup choices are made."""
        if provider is not None:
            self.llm_provider = provider.strip().lower()
        if workspace is not None:
            self.workspace = _resolve_path(workspace, self.project_root)
        if model is not None:
            self.active_model_alias = model

        if self.resolved_paths is not None:
            self.resolved_paths.workspace_root = self.workspace
            self.resolved_paths.scratch_root = self.workspace

    def validate_runtime_ready(self) -> None:
        """Validate runtime-only requirements after setup choices are applied."""
        if not self.workspace.exists():
            raise ConfigError(f"Workspace directory does not exist: {self.workspace}")

        if not self.system_prompt_path.exists():
            raise ConfigError(
                f"System prompt file not found: {self.system_prompt_path}"
            )

        try:
            self.system_prompt = self.system_prompt_path.read_text(
                encoding="utf-8"
            ).strip()
        except OSError as exc:
            raise ConfigError(f"Failed to read system prompt: {exc}") from exc

        if not self.system_prompt:
            raise ConfigError(f"System prompt file is empty: {self.system_prompt_path}")

        if self.llm_provider == "openrouter":
            if not self.openrouter_api_key:
                raise ConfigError(
                    "OPENROUTER_API_KEY is required when LLM_PROVIDER=openrouter."
                )
            self._prepare_openrouter_models_path()
        else:
            self._prepare_ollama_models_path()

    def _legacy_ollama_models_path(self) -> Path:
        return (
            self.project_root / "protocol_monk" / "config" / "models.json"
        ).resolve(strict=False)

    def _copy_legacy_map(self, source: Path, target: Path, *, provider_name: str) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        logger.info(
            "Migrated legacy %s model map from %s to %s",
            provider_name,
            source,
            target,
        )

    def _prepare_ollama_models_path(self) -> None:
        target = self.models_json_path
        legacy = self._legacy_ollama_models_path()

        if self._models_json_path_overridden:
            return

        if target.exists():
            if legacy.exists() and legacy != target:
                logger.info(
                    "Ignoring legacy Ollama model map at %s; authoritative path is %s",
                    legacy,
                    target,
                )
            return

        if legacy.exists() and legacy != target:
            self._copy_legacy_map(legacy, target, provider_name="Ollama")

    def _prepare_openrouter_models_path(self) -> None:
        target = self.openrouter_models_json_path

        if self._openrouter_models_json_path_overridden:
            if not target.exists():
                raise ConfigError(
                    f"OpenRouter model map not found: {target}. "
                    "Create the file or remove OPENROUTER_MODELS_JSON_PATH to use the "
                    "default repo-local curated map."
                )
            return

        if target.exists():
            return

        example = self.resolved_paths.openrouter_example_json
        if not example.exists():
            raise ConfigError(
                f"OpenRouter example model map not found: {example}"
            )

        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(example, target)
        logger.info("Seeded OpenRouter model map from %s to %s", example, target)

    async def initialize(self) -> None:
        """
        Post-choice runtime initialization for provider/model state.
        """
        self.validate_runtime_ready()
        await self._discover_models()

    async def _discover_models(self) -> None:
        """Load model config for the selected provider."""
        self.last_model_load_error = None
        try:
            if self.llm_provider == "openrouter":
                logger.info("Loading OpenRouter model map...")
                model_config = load_or_initialize_openrouter_model_map(
                    self.openrouter_models_json_path
                )
            else:
                logger.info("Discovering models from Ollama...")
                model_config = await discover_models(
                    models_json_path=self.models_json_path,
                    ollama_host=self.ollama_host,
                    force_refresh=self.force_model_discovery,
                )

            self.models_config = model_config

            if self.active_model_alias:
                self._set_active_model(self.active_model_alias)
            elif model_config.get("default_model"):
                self._set_active_model(model_config["default_model"])

            logger.info(
                "Model configuration loaded for provider '%s'. Active model: %s",
                self.llm_provider,
                self.active_model_name,
            )

        except ConfigError as exc:
            self.last_model_load_error = str(exc)
            self.models_config = None
            raise
        except Exception as exc:
            self.last_model_load_error = str(exc)
            logger.error("Model configuration loading failed: %s", exc)
            if self.llm_provider == "openrouter":
                self.models_config = None
                raise ConfigError(f"Failed to load OpenRouter model map: {exc}") from exc
            self.models_config = self._create_fallback_model_config()
            self._set_active_model(self.models_config.get("default_model", ""))

    async def reload_models_for_provider(self, provider: str) -> None:
        """Reload model config for a specific provider."""
        original_provider = self.llm_provider
        original_models = self.models_config
        original_active_model = self.active_model_name
        original_active_config = self._active_model_config
        self.llm_provider = provider.lower()

        try:
            await self.initialize()
        except Exception:
            self.llm_provider = original_provider
            self.models_config = original_models
            self.active_model_name = original_active_model
            self._active_model_config = original_active_config
            raise

    def _set_active_model(self, model_alias: str) -> None:
        """Set the active model from alias or name."""
        if not self.models_config:
            return

        models = self.models_config.get("models", {})

        if model_alias in models:
            self._active_model_config = models[model_alias]
            self.active_model_name = model_alias
            return

        for name, config in models.items():
            if model_alias in name:
                self._active_model_config = config
                self.active_model_name = name
                return

        logger.warning("Model '%s' not found. Using default.", model_alias)
        default = self.models_config.get("default_model")
        if default and default in models:
            self._active_model_config = models[default]
            self.active_model_name = default

    def _create_fallback_model_config(self) -> Dict[str, Any]:
        """Create minimal fallback config if model loading fails."""
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
        """Get the active model's parameters, forcing context limit."""
        params = self._active_model_config.get("parameters", {}).copy()

        if self.llm_provider == "ollama":
            params["num_ctx"] = self.context_window_limit

        return params

    @property
    def trace_max_total_bytes(self) -> int:
        return int(self.trace_max_total_mb) * 1024 * 1024


def load_settings(base_path: Optional[Path] = None) -> Settings:
    """Deterministic bootstrap entrypoint for settings loading."""
    app_root = (
        Path(base_path).expanduser().resolve(strict=False)
        if base_path is not None
        else Path(__file__).resolve().parent
    )
    project_root = app_root.parent
    env_file = (project_root / ".env").resolve(strict=False)
    env_keys = _parse_env_file_keys(env_file) | {
        key
        for key in (
            "MODELS_JSON_PATH",
            "OPENROUTER_MODELS_JSON_PATH",
        )
        if key in os.environ
    }

    settings = Settings(
        _env_file=str(env_file) if env_file.exists() else None,
        project_root=project_root,
        env_file_path=env_file,
    )
    settings.mark_path_overrides(env_keys)
    return settings

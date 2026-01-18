import os
from pathlib import Path
from dataclasses import dataclass

from protocol_monk.exceptions.config import ConfigError


@dataclass(frozen=True)
class Settings:
    """
    Immutable application configuration.
    All fields must be populated at startup. No defaults allowed.
    """

    system_prompt: str
    workspace_root: Path
    log_level: str

    # We can add model/provider settings here later as the spec evolves


def load_settings(base_path: Path) -> Settings:
    """
    Loads configuration from environment and disk.

    Args:
        base_path: The root directory of the application (where main.py lives).

    Raises:
        ConfigError: If any required setting or file is missing.
    """

    # 1. Load Workspace Path (Must be explicit)
    workspace_env = os.getenv("MONK_WORKSPACE")
    if not workspace_env:
        raise ConfigError("Missing required environment variable: MONK_WORKSPACE")
    workspace_root = Path(workspace_env).resolve()

    if not workspace_root.exists():
        raise ConfigError(f"Workspace directory does not exist: {workspace_root}")

    # 2. Load System Prompt (Must exist on disk)
    # We expect system_prompt.txt to be in the root or a specific config location provided by env
    prompt_path_env = os.getenv("MONK_SYSTEM_PROMPT_PATH")
    if not prompt_path_env:
        raise ConfigError(
            "Missing required environment variable: MONK_SYSTEM_PROMPT_PATH"
        )

    prompt_path = base_path / prompt_path_env
    if not prompt_path.exists():
        raise ConfigError(f"System prompt file not found at: {prompt_path}")

    try:
        system_prompt_content = prompt_path.read_text(encoding="utf-8").strip()
        if not system_prompt_content:
            raise ConfigError(f"System prompt file is empty: {prompt_path}")
    except OSError as e:
        raise ConfigError(f"Failed to read system prompt: {e}")

    # 3. Load Log Level
    log_level = os.getenv("MONK_LOG_LEVEL")
    if not log_level:
        raise ConfigError("Missing required environment variable: MONK_LOG_LEVEL")

    return Settings(
        system_prompt=system_prompt_content,
        workspace_root=workspace_root,
        log_level=log_level.upper(),
    )

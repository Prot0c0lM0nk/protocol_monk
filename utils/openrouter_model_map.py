"""Strict OpenRouter model map loader for user-managed JSON config."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from protocol_monk.exceptions.config import ConfigError


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ConfigError(message)


def _validate_model_entry(model_key: str, entry: Any) -> None:
    _require(
        isinstance(entry, dict),
        f"OpenRouter model '{model_key}' must be an object.",
    )

    required_keys = {
        "name",
        "family",
        "context_window",
        "supports_tools",
        "supports_thinking",
        "parameters",
        "user_overrides",
    }
    missing = sorted(required_keys - set(entry.keys()))
    _require(
        not missing,
        (
            f"OpenRouter model '{model_key}' is missing required keys: "
            + ", ".join(missing)
        ),
    )

    _require(
        isinstance(entry["name"], str) and bool(entry["name"].strip()),
        f"OpenRouter model '{model_key}' field 'name' must be a non-empty string.",
    )
    _require(
        isinstance(entry["family"], str) and bool(entry["family"].strip()),
        f"OpenRouter model '{model_key}' field 'family' must be a non-empty string.",
    )
    _require(
        isinstance(entry["context_window"], int)
        and not isinstance(entry["context_window"], bool)
        and entry["context_window"] > 0,
        f"OpenRouter model '{model_key}' field 'context_window' must be a positive integer.",
    )
    _require(
        isinstance(entry["supports_tools"], bool),
        f"OpenRouter model '{model_key}' field 'supports_tools' must be a boolean.",
    )
    _require(
        isinstance(entry["supports_thinking"], bool),
        f"OpenRouter model '{model_key}' field 'supports_thinking' must be a boolean.",
    )
    _require(
        isinstance(entry["parameters"], dict),
        f"OpenRouter model '{model_key}' field 'parameters' must be an object.",
    )
    _require(
        isinstance(entry["user_overrides"], dict),
        f"OpenRouter model '{model_key}' field 'user_overrides' must be an object.",
    )


def _validate_model_map(path: Path, loaded: Any) -> Dict[str, Any]:
    _require(
        isinstance(loaded, dict),
        f"OpenRouter model map must be a top-level JSON object: {path}",
    )

    models = loaded.get("models")
    _require(
        isinstance(models, dict),
        f"OpenRouter model map field 'models' must be an object: {path}",
    )
    _require(bool(models), f"OpenRouter model map field 'models' cannot be empty: {path}")

    default_model = loaded.get("default_model")
    _require(
        isinstance(default_model, str) and bool(default_model.strip()),
        f"OpenRouter model map field 'default_model' must be a non-empty string: {path}",
    )
    _require(
        default_model in models,
        (
            "OpenRouter model map 'default_model' must reference an existing key in "
            f"'models': {default_model}"
        ),
    )

    for model_key, model_entry in models.items():
        _require(
            isinstance(model_key, str) and bool(model_key.strip()),
            "OpenRouter model map has an invalid empty model key.",
        )
        _validate_model_entry(model_key, model_entry)

    return loaded


def load_or_initialize_openrouter_model_map(path: Path) -> Dict[str, Any]:
    """Load and validate the OpenRouter model map from disk (no auto-initialization)."""
    path = Path(path)
    if not path.exists():
        raise ConfigError(
            f"OpenRouter model map not found: {path}. "
            "Create the file or set OPENROUTER_MODELS_JSON_PATH to a valid path."
        )

    try:
        with path.open("r", encoding="utf-8") as handle:
            loaded = json.load(handle)
    except json.JSONDecodeError as exc:
        raise ConfigError(
            "OpenRouter model map is not valid JSON "
            f"({path}:{exc.lineno}:{exc.colno}): {exc.msg}"
        ) from exc
    except OSError as exc:
        raise ConfigError(f"Failed to read OpenRouter model map {path}: {exc}") from exc

    return _validate_model_map(path, loaded)

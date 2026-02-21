"""Persistent OpenRouter model map bootstrap and loading helpers."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

DEFAULT_CONTEXT_WINDOW = 2000
DEFAULT_MODEL = "mistralai/ministral-14b-2512"

_MODEL_FAMILIES = {
    "qwen/qwen3.5-397b-a17b": "qwen",
    "z-ai/glm-5": "glm",
    "z-ai/glm-4.7-flash": "glm",
    "mistralai/ministral-14b-2512": "mistral",
    "liquid/lfm2-8b-a1b": "liquid",
}


def _now_iso() -> str:
    return datetime.now().isoformat()


def _default_model_entry(name: str, context_window: int, timestamp: str) -> Dict[str, Any]:
    return {
        "name": name,
        "family": _MODEL_FAMILIES[name],
        "is_cloud": True,
        "context_window": context_window,
        "supports_thinking": False,
        "supports_tools": True,
        "capabilities": ["completion", "tools"],
        "parameters": {},
        "user_overrides": {},
        "discovered_at": timestamp,
    }


def build_default_openrouter_model_map(
    context_window: int = DEFAULT_CONTEXT_WINDOW,
) -> Dict[str, Any]:
    """
    Build a deterministic model map for the OpenRouter-backed models.
    """
    timestamp = _now_iso()
    models = {
        name: _default_model_entry(name, context_window=context_window, timestamp=timestamp)
        for name in _MODEL_FAMILIES
    }
    return {
        "version": "1.0",
        "last_updated": timestamp,
        "default_model": DEFAULT_MODEL,
        "models": models,
    }


def _is_valid_model_map(config: Dict[str, Any]) -> bool:
    if not isinstance(config, dict):
        return False
    if not isinstance(config.get("models"), dict):
        return False
    if not config["models"]:
        return False
    return True


def _save(path: Path, config: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(config, handle, indent=2, ensure_ascii=False)


def _normalize_existing_model_map(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Ensure expected top-level keys and required model entries exist.
    Preserve existing user overrides where present.
    """
    normalized = dict(config)
    models = normalized.get("models")
    if not isinstance(models, dict):
        models = {}

    timestamp = _now_iso()
    changed = False
    for name in _MODEL_FAMILIES:
        if name in models and isinstance(models[name], dict):
            model_entry = models[name]
            if "family" not in model_entry:
                model_entry["family"] = _MODEL_FAMILIES[name]
                changed = True
            if "supports_tools" not in model_entry:
                model_entry["supports_tools"] = True
                changed = True
            if "is_cloud" not in model_entry:
                model_entry["is_cloud"] = True
                changed = True
            if "context_window" not in model_entry:
                model_entry["context_window"] = DEFAULT_CONTEXT_WINDOW
                changed = True
            if "parameters" not in model_entry or not isinstance(
                model_entry.get("parameters"), dict
            ):
                model_entry["parameters"] = {}
                changed = True
            if "user_overrides" not in model_entry or not isinstance(
                model_entry.get("user_overrides"), dict
            ):
                model_entry["user_overrides"] = {}
                changed = True
            if "capabilities" not in model_entry:
                model_entry["capabilities"] = ["completion", "tools"]
                changed = True
            if "name" not in model_entry:
                model_entry["name"] = name
                changed = True
            if "discovered_at" not in model_entry:
                model_entry["discovered_at"] = timestamp
                changed = True
        else:
            models[name] = _default_model_entry(
                name=name,
                context_window=DEFAULT_CONTEXT_WINDOW,
                timestamp=timestamp,
            )
            changed = True

    if normalized.get("default_model") not in models:
        normalized["default_model"] = DEFAULT_MODEL
        changed = True
    if "version" not in normalized:
        normalized["version"] = "1.0"
        changed = True
    normalized["models"] = models
    if changed:
        normalized["last_updated"] = timestamp

    return normalized


def load_or_initialize_openrouter_model_map(path: Path) -> Dict[str, Any]:
    """
    Load an existing OpenRouter model map from disk, creating one if missing.
    """
    path = Path(path)
    if not path.exists():
        config = build_default_openrouter_model_map()
        _save(path, config)
        return config

    try:
        with path.open("r", encoding="utf-8") as handle:
            loaded = json.load(handle)
    except Exception:
        config = build_default_openrouter_model_map()
        _save(path, config)
        return config

    if not _is_valid_model_map(loaded):
        config = build_default_openrouter_model_map()
        _save(path, config)
        return config

    normalized = _normalize_existing_model_map(loaded)
    if normalized != loaded:
        _save(path, normalized)
    return normalized

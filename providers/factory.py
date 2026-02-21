"""Provider factory helpers."""

from __future__ import annotations

from typing import Any

from protocol_monk.config.settings import Settings


def create_provider(settings: Settings) -> Any:
    """Instantiate the configured provider implementation."""
    provider_name = (getattr(settings, "llm_provider", "ollama") or "ollama").lower()
    if provider_name == "openrouter":
        from protocol_monk.providers.openrouter import OpenRouterProvider

        return OpenRouterProvider(settings)

    from protocol_monk.providers.ollama import OllamaProvider

    return OllamaProvider(settings)

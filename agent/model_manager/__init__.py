from typing import Dict, List
import logging

from agent.model_manager.loader import ModelConfigLoader
from agent.model_manager.scanner import ModelScanner
from agent.model_manager.selector import ModelSelector
from agent.model_manager.structs import ModelInfo, SwitchReport


class RuntimeModelManager:
    """Facade for the model manager package."""

    def __init__(self, provider: str = "ollama"):
        """
        Initialize the model manager with provider-specific configuration.

        Args:
            provider: The provider name ("ollama", "openrouter", etc.)
        """
        self.provider = provider
        self.logger = logging.getLogger(__name__)
        self.loader = self._create_loader_for_provider(provider)
        self.scanner = ModelScanner()
        self.model_map = self.loader.load_model_map()
        self.selector = ModelSelector(self.model_map)

    def _create_loader_for_provider(self, provider: str) -> ModelConfigLoader:
        """
        Create a ModelConfigLoader with the appropriate model map file for the provider.

        Args:
            provider: The provider name

        Returns:
            ModelConfigLoader: Configured loader for the provider
        """
        # Map providers to their model map files
        provider_map_files = {
            "ollama": "ollama_map.json",
            "openrouter": "openrouter_map.json",
            "default": "ollama_map.json",  # Fallback to original
        }

        # Use provider-specific map if available, otherwise fall back to default
        model_map_file = provider_map_files.get(provider, provider_map_files["default"])

        # Check if the provider-specific file exists, fall back to default if not
        from pathlib import Path

        if not Path(model_map_file).exists():
            self.logger.warning(
                f"Model map file '{model_map_file}' not found for provider '{provider}', using default"
            )
            model_map_file = provider_map_files["default"]

        return ModelConfigLoader(model_map_file=model_map_file)

    def get_available_models(self) -> Dict[str, ModelInfo]:
        """
        Get all available models from the model map.

        Returns:
            Dict[str, ModelInfo]: Dictionary of available models with their info
        """
        return self.model_map

    async def scan_local_models(self) -> List[str]:
        """
        Scan for locally available models via Ollama.

        Returns:
            List[str]: List of available model names
        """
        return await self.scanner.scan_local_models()

    def assess_switch(self, current_usage: int, target_model_name: str) -> SwitchReport:
        """
        Assess if it's safe to switch to the target model.

        Args:
            current_usage: Current token usage
            target_model_name: Name of target model to switch to

        Returns:
            SwitchReport: Assessment report with safety status and limits
        """
        return self.selector.assess_switch(current_usage, target_model_name)

    def get_models_by_provider(self) -> Dict[str, List[str]]:
        """
        Get models grouped by provider.

        Returns:
            Dict[str, List[str]]: Dictionary mapping provider names to model lists
        """
        provider_models = {
            "ollama": [],
            "openrouter": [],
            "generic": [],  # For models without specific provider
        }

        for model_name, model_info in self.model_map.items():
            provider = getattr(model_info, "provider", "generic")
            if provider not in provider_models:
                provider_models[provider] = []
            provider_models[provider].append(model_name)

        return provider_models

    def get_provider_for_model(self, model_name: str) -> str:
        """
        Get the provider for a specific model.

        Args:
            model_name: Name of the model

        Returns:
            str: Provider name ("ollama", "openrouter", or "generic")
        """
        model_info = self.model_map.get(model_name)
        if model_info:
            return getattr(model_info, "provider", "generic")

        # Heuristic: determine provider based on model name pattern
        if "/" in model_name or any(
            x in model_name.lower() for x in ["gpt", "claude", "gemini"]
        ):
            return "openrouter"
        else:
            return "ollama"

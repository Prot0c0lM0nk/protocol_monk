#!/usr/bin/env python3
"""
Provider Registry
================

Manages provider selection, instantiation, and failover logic.
Central point for all provider operations with automatic switching.
"""

import logging
from typing import Dict, List, Optional, Type

from agent.base_model_client import BaseModelClient
from exceptions import ProviderError, ProviderNotAvailableError


class ProviderRegistry:
    """
    Singleton that manages provider lifecycle, selection, and failover.
    
    Maintains provider priority chains and handles automatic switching
    when providers become unavailable.
    """
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
            
        self._providers: Dict[str, Type[BaseModelClient]] = {}
        self._provider_instances: Dict[str, BaseModelClient] = {}
        self._provider_chain: List[str] = []
        self._current_provider_index: int = 0
        self.logger = logging.getLogger(__name__)
        self._initialized = True
    
    def register_provider(self, name: str, provider_class: Type[BaseModelClient]) -> None:
        """
        Register a new provider class with the registry.
        
        Args:
            name: Provider name (e.g., "ollama", "openrouter")
            provider_class: Provider class that inherits from BaseModelClient
        """
        if not issubclass(provider_class, BaseModelClient):
            raise ProviderError(
                f"Provider class {provider_class} must inherit from BaseModelClient",
                details={"provider_name": name, "provider_class": str(provider_class)}
            )
        
        self._providers[name] = provider_class
        self.logger.info(f"Registered provider: {name}")
    
    def set_provider_chain(self, provider_names: List[str]) -> None:
        """
        Set the priority order for provider selection and failover.
        
        Args:
            provider_names: List of provider names in priority order
        """
        # Validate all providers are registered
        for name in provider_names:
            if name not in self._providers:
                raise ProviderError(
                    f"Provider '{name}' is not registered. Available providers: {list(self._providers.keys())}",
                    details={"requested_provider": name, "available_providers": list(self._providers.keys())}
                )
        
        self._provider_chain = provider_names.copy()
        self._current_provider_index = 0
        self.logger.info(f"Set provider chain: {' -> '.join(provider_names)}")
    
    async def get_model_client(self, model_name: str) -> BaseModelClient:
        """
        Return appropriate model client for model, trying providers in chain order.
        
        Args:
            model_name: Name of the model to get client for
            
        Returns:
            BaseModelClient: Model client instance
            
        Raises:
            ProviderNotAvailableError: If no provider can handle the model
        """
        if not self._provider_chain:
            raise ProviderNotAvailableError(
                "No provider chain configured. Call set_provider_chain() first.",
                details={"model_name": model_name}
            )
        
        # Try providers in chain order
        for i, provider_name in enumerate(self._provider_chain):
            try:
                client = await self._create_client_for_provider(provider_name, model_name)
                self._current_provider_index = i
                self.logger.info(f"Using provider '{provider_name}' for model '{model_name}'")
                return client
            except Exception as e:
                self.logger.warning(
                    f"Provider '{provider_name}' failed for model '{model_name}': {e}"
                )
                if i == len(self._provider_chain) - 1:
                    # Last provider failed
                    raise ProviderNotAvailableError(
                        f"No provider available for model '{model_name}'. "
                        f"Tried providers: {self._provider_chain}",
                        details={
                            "model_name": model_name,
                            "attempted_providers": self._provider_chain,
                            "last_error": str(e)
                        }
                    ) from e
        
        # Should not reach here
        raise ProviderNotAvailableError(
            f"Unexpected error getting client for model '{model_name}'",
            details={"model_name": model_name}
        )
    
    async def _create_client_for_provider(self, provider_name: str, model_name: str) -> BaseModelClient:
        """
        Create a client instance for a specific provider.
        
        Args:
            provider_name: Name of the provider
            model_name: Model name to create client for
            
        Returns:
            BaseModelClient: Provider client instance
        """
        if provider_name not in self._providers:
            raise ProviderError(
                f"Provider '{provider_name}' is not registered",
                details={"provider_name": provider_name}
            )
        
        provider_class = self._providers[provider_name]
        
        # Get provider-specific configuration
        # This will be enhanced when we add provider config to settings
        provider_config = {}
        
        try:
            client = provider_class(model_name, provider_config)
            return client
        except Exception as e:
            raise ProviderError(
                f"Failed to create client for provider '{provider_name}' and model '{model_name}': {e}",
                details={
                    "provider_name": provider_name,
                    "model_name": model_name,
                    "provider_class": str(provider_class)
                }
            ) from e
    
    async def handle_provider_error(self, error: Exception, model_name: str) -> bool:
        """
        Attempt failover to next provider in chain on error.
        
        Args:
            error: The error that occurred
            model_name: Model name that was being used
            
        Returns:
            bool: True if failover was successful, False otherwise
        """
        if self._current_provider_index >= len(self._provider_chain) - 1:
            # Already using last provider
            self.logger.error(
                f"Failover failed: already using last provider in chain for model '{model_name}'"
            )
            return False
        
        # Try next provider
        next_index = self._current_provider_index + 1
        next_provider = self._provider_chain[next_index]
        
        try:
            self.logger.info(
                f"Attempting failover from '{self._provider_chain[self._current_provider_index]}' "
                f"to '{next_provider}' for model '{model_name}'"
            )
            
            # Close current client if it exists
            current_client = self._provider_instances.get(model_name)
            if current_client:
                await current_client.close()
            
            # Create new client with next provider
            new_client = await self._create_client_for_provider(next_provider, model_name)
            self._provider_instances[model_name] = new_client
            self._current_provider_index = next_index
            
            self.logger.info(f"Failover successful: now using '{next_provider}' for model '{model_name}'")
            return True
            
        except Exception as e:
            self.logger.error(
                f"Failover to provider '{next_provider}' failed for model '{model_name}': {e}"
            )
            return False
    
    def get_available_models(self) -> Dict[str, List[str]]:
        """
        Return dict mapping providers to their available models.
        
        Note: This is a simplified implementation. In a full implementation,
        each provider would have a method to list its available models.
        
        Returns:
            Dict[str, List[str]]: Provider to models mapping
        """
        result = {}
        for provider_name in self._providers.keys():
            # For now, return empty lists - providers should implement model discovery
            result[provider_name] = []
        return result
    
    def get_registered_providers(self) -> List[str]:
        """
        Get list of registered provider names.
        
        Returns:
            List[str]: Registered provider names
        """
        return list(self._providers.keys())
    
    def get_current_provider(self) -> Optional[str]:
        """
        Get the currently active provider name.
        
        Returns:
            Optional[str]: Current provider name or None if no provider is active
        """
        if self._current_provider_index < len(self._provider_chain):
            return self._provider_chain[self._current_provider_index]
        return None
    
    async def close_all(self) -> None:
        """
        Close all provider instances and clean up resources.
        """
        for model_name, client in self._provider_instances.items():
            try:
                await client.close()
            except Exception as e:
                self.logger.warning(f"Error closing client for model '{model_name}': {e}")
        
        self._provider_instances.clear()
        self.logger.info("Closed all provider instances")

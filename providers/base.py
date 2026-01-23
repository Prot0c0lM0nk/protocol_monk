from abc import ABC, abstractmethod
from typing import AsyncIterator, List, Dict, Any, Optional

from protocol_monk.agent.structs import Message, ProviderSignal
from protocol_monk.exceptions.provider import ProviderError


class BaseProvider(ABC):
    """
    The Abstract Base Class (Contract) for all LLM Providers.
    """

    @abstractmethod
    async def stream_chat(
        self,
        messages: List[Message],
        model_name: str,
        tools: Optional[List[Dict[str, Any]]] = None,
        options: Optional[Dict[str, Any]] = None,  # [FIX] Added options to contract
    ) -> AsyncIterator[ProviderSignal]:
        """
        Stream structured signals from the provider.

        Yields:
            ProviderSignal: Structured events (content, thinking, tools).
        """
        pass

    @abstractmethod
    async def validate_connection(self) -> bool:
        """
        Ping the provider to ensure availability/authentication.
        """
        pass
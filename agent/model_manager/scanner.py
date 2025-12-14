import aiohttp
from typing import Dict, List

from agent.model_manager.structs import ModelInfo
from config.static import settings


class ModelScanner:
    """Scans for available local models via Ollama API."""

    def __init__(self):
        """
        Initialize the model scanner with Ollama URL.
        """
        self.ollama_url = settings.api.ollama_url.replace("/api/chat", "")  # Base URL

    async def scan_local_models(self) -> List[str]:
        """
        Query Ollama for available local models.

        Returns:
            List[str]: List of available model names
        """
        try:
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(f"{self.ollama_url}/api/tags") as response:
                    if response.status == 200:
                        data = await response.json()
                        models = data.get("models", [])
                        return [model["name"] for model in models]
                    else:
                        print(f"Error scanning local models: {response.status}")
                        return []
        except Exception as e:
            print(f"Error scanning local models: {e}")
            return []

    def merge_availability(
        self, map_data: Dict[str, ModelInfo], local_data: List[str]
    ) -> Dict[str, ModelInfo]:
        """
        Merge model map data with local availability information.

        Args:
            map_data: Model map data with ModelInfo objects
            local_data: List of locally available model names

        Returns:
            Dict[str, ModelInfo]: Merged model availability data
        """
        return map_data

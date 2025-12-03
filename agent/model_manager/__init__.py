from typing import Dict, List

from agent.model_manager.loader import ModelConfigLoader
from agent.model_manager.scanner import ModelScanner
from agent.model_manager.selector import ModelSelector
from agent.model_manager.structs import ModelInfo, SwitchReport


class RuntimeModelManager:
    """Facade for the model manager package."""

    def __init__(self):
        self.loader = ModelConfigLoader()
        self.scanner = ModelScanner()
        self.model_map = self.loader.load_model_map()
        self.selector = ModelSelector(self.model_map)

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

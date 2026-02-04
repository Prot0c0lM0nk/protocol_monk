import json
import logging
from pathlib import Path
from typing import Any, Dict

from agent.model_manager.structs import ModelInfo


class ModelConfigLoader:
    def __init__(
        self,
        model_map_file: str = "ollama_map.json",
        model_options_file: str = "model_options.json",
    ):
        self.model_map_file = Path(model_map_file)
        self.model_options_file = Path(model_options_file)
        self.logger = logging.getLogger(__name__)

    def load_model_map(self) -> Dict[str, ModelInfo]:
        """
        Load model map and convert to ModelInfo objects.

        Returns:
            Dict[str, ModelInfo]: Model map with ModelInfo objects
        """
        # Validate path before attempting to open
        if not self.model_map_file or not isinstance(self.model_map_file, (str, Path)):
            self.logger.warning("Invalid model_map_file path")
            return {}

        model_path = Path(self.model_map_file)
        if not model_path.exists():
            self.logger.warning(f"Model map file not found: {model_path}")
            return {}

        try:
            with open(model_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                models = data.get("models", {})

                # Convert to ModelInfo objects
                model_info_dict = {}
                for name, info in models.items():
                    model_info_dict[name] = ModelInfo(
                        name=name,
                        provider=info.get("provider", "unknown"),
                        context_window=info.get("context_window", 16384),
                        hf_path=info.get("hf_path", "unknown"),
                    )
                return model_info_dict
        except Exception as e:
            self.logger.error(f"Error loading model map: {e}")
            return {}

    def load_options(self) -> Dict[str, Any]:
        """
        Load model options configuration.

        Returns:
            Dict[str, Any]: Model options configuration
        """
        try:
            with open(self.model_options_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            self.logger.error(f"Error loading model options: {e}")
            return {}

    def get_model_limit(self, model_name: str) -> int:
        """
        Get the context window limit for a specific model.

        Args:
            model_name: Name of the model to get limit for

        Returns:
            int: Context window limit in tokens
        """
        model_map = self.load_model_map()
        model_info = model_map.get(model_name)
        if model_info:
            return model_info.context_window
        return 16384  # Default fallback

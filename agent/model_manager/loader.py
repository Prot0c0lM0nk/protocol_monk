import json
from pathlib import Path
from typing import Any, Dict

from agent.model_manager.structs import ModelInfo


class ModelConfigLoader:
    """Loads static model configuration from JSON files."""

    def __init__(
        self,
        model_map_file: str = "model_map.json",
        model_options_file: str = "model_options.json",
    ):
        """
        Initialize the model loader with file paths.

        Args:
            model_map_file: Path to model map JSON file (default: "model_map.json")
            model_options_file: Path to model options JSON file
                (default: "model_options.json")
        """
        self.model_map_file = Path(model_map_file)
        self.model_options_file = Path(model_options_file)
        self.model_map_file = Path(model_map_file)
        self.model_options_file = Path(model_options_file)

    def load_model_map(self) -> Dict[str, ModelInfo]:
        """
        Load model map and convert to ModelInfo objects.

        Returns:
            Dict[str, ModelInfo]: Model map with ModelInfo objects
        """
        try:
            with open(self.model_map_file, "r", encoding="utf-8") as f:
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
            print(f"Error loading model map: {e}")
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
            print(f"Error loading model options: {e}")
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

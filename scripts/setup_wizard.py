#!/usr/bin/env python3
"""
Setup Wizard
------------
A standalone utility script to guide users through initial configuration
when user_defaults.json is missing.

USAGE:
    python -m protocol_monk.scripts.setup_wizard

NOTE:
    This script is for SETUP only. It is not part of the Agent's
    runtime loop and is permitted to write to stdout/stderr.
"""

import json
import logging
import sys
from pathlib import Path
from typing import Dict, Any

# Add project root to sys.path to allow imports
current_file = Path(__file__).resolve()
project_root = current_file.parent.parent.parent
# Add project root to sys.path to allow imports
current_file = Path(__file__).resolve()
project_root = current_file.parent.parent.parent
sys.path.insert(0, str(project_root))

from protocol_monk.scripts.fetch_model_config import ModelConfigFetcher

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("SetupWizard")


class SetupWizard:
    def __init__(self, config_dir: Path):
        self.config_dir = config_dir
        self.models_path = config_dir / "models.json"
        self.defaults_path = config_dir / "user_defaults.json"

    def run(self):
        """
        Main execution flow: Check configs -> Discover if needed -> Prompt user -> Save.
        """
        logger.info("--- Starting Setup Wizard ---")

        # 1. Ensure models.json exists (run Phase 2 logic if needed)
        self._ensure_models_config()

        # 2. Check if user defaults already exist
        if self.defaults_path.exists():
            logger.info("Setup already complete. user_defaults.json exists.")
            return True

        # 3. Run interactive setup
        logger.info("user_defaults.json not found. Starting setup process...")
        self._run_interactive_setup()

        logger.info("--- Setup Wizard Complete ---")
        return True

    def _ensure_models_config(self):
        """Ensure models.json exists by running discovery if needed."""
        if not self.models_path.exists():
            logger.info("models.json missing. Running model discovery...")
            fetcher = ModelConfigFetcher()
            fetcher.run(self.models_path)

    def _run_interactive_setup(self):
        """Interactive setup process using stdin/stdout."""
        # Load the models configuration
        try:
            with open(self.models_path, "r") as f:
                model_config = json.load(f)
        except Exception as e:
            logger.error(f"Failed to load models.json: {e}")
            sys.exit(1)

        # Identify families that need context limits (Local models only)
        families_needing_limits = self._identify_families_needing_limits(model_config)

        if not families_needing_limits:
            logger.info("No local models requiring context limits found.")
            self._save_defaults(
                {"version": "1.0", "auto_confirm": True, "context_limits": {}}
            )
            return

        # Prompt user for context limits for each family
        context_limits = {}
        print("\n=== Protocol Monk Setup Wizard ===")
        print("Some of your local models need context window limits configured.\n")

        for family in families_needing_limits:
            limit = self._prompt_for_context_limit(family)
            context_limits[family] = limit

        # Save the configuration
        defaults = {
            "version": "1.0",
            "auto_confirm": True,
            "context_limits": context_limits,
        }

        self._save_defaults(defaults)
        print("\n✓ Setup complete! Configuration saved.")

    def _identify_families_needing_limits(self, model_config: Dict[str, Any]) -> list:
        """Identify unique model families that need context limits (local models only)."""
        families_seen = set()
        families_needing_limits = []

        for model_key, info in model_config.get("models", {}).items():
            # Skip cloud models (they manage their own context)
            if info.get("is_cloud", False):
                continue

            family = info.get("family", "unknown")
            if family not in families_seen:
                families_seen.add(family)
                families_needing_limits.append(family)

        return families_needing_limits

    def _prompt_for_context_limit(self, family: str) -> int:
        """Prompt user for context limit for a model family."""
        default_suggestion = 8192  # Safe default
        print(f"\nModel Family: {family}")
        print(f"Suggested context limit: {default_suggestion}")

        while True:
            try:
                user_input = input(
                    f"Enter context limit for {family} models (or press Enter for {default_suggestion}): "
                ).strip()
                if not user_input:
                    return default_suggestion
                return int(user_input)
            except ValueError:
                print("Please enter a valid number.")

    def _save_defaults(self, data: Dict):
        """Save user defaults to config file."""
        try:
            with open(self.defaults_path, "w") as f:
                json.dump(data, f, indent=2)
            logger.info(f"Saved user defaults to: {self.defaults_path}")
        except Exception as e:
            logger.error(f"Failed to save user defaults: {e}")
            sys.exit(1)


if __name__ == "__main__":
    # Define the config directory
    config_dir = project_root / "protocol_monk" / "config"

    wizard = SetupWizard(config_dir)
    wizard.run()

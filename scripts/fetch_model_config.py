#!/usr/bin/env python3
"""
Model Config Fetcher
--------------------
Standalone utility to run model discovery and save models.json.

USAGE:
    python -m protocol_monk.scripts.fetch_model_config
"""

import asyncio
import json
import logging
import sys
from pathlib import Path

# Add project root to sys.path
current_file = Path(__file__).resolve()
project_root = current_file.parent.parent.parent
sys.path.insert(0, str(project_root))

from protocol_monk.utils.model_discovery import discover_models

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("FetchConfig")


class ModelConfigFetcher:
    def run(self, output_path: Path):
        """Run async discovery and write result to file."""
        logger.info("--- Starting Model Discovery ---")

        async def _run_async():
            config = await discover_models(output_path, force_refresh=True)
            self._save_json(config, output_path)

        asyncio.run(_run_async())

        logger.info("--- Discovery Complete ---")
        print("Project Root:", project_root)
        print("Sys Path:", sys.path[:3])  # Just show first few entries

    def _save_json(self, data: dict, path: Path):
        """Write JSON to disk."""
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            logger.info(f"Saved configuration to: {path}")
        except Exception as e:
            logger.error(f"Failed to write models.json: {e}")


if __name__ == "__main__":
    output_file = project_root / "protocol_monk" / "config" / "models.json"
    fetcher = ModelConfigFetcher()
    fetcher.run(output_file)

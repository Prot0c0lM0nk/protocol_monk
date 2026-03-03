#!/usr/bin/env python3
"""Fetch selected OpenRouter models and update openrouter_models.json.

Usage examples:
  python -m protocol_monk.scripts.fetch_openrouter_model_config \
    --model z-ai/glm-5 --model mistralai/ministral-14b-2512

  python -m protocol_monk.scripts.fetch_openrouter_model_config \
    --model z-ai/glm-5 --write-mode replace --default-model z-ai/glm-5
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path
from typing import List

from protocol_monk.exceptions.config import ConfigError
from protocol_monk.utils.openrouter_discovery import OpenRouterModelDiscovery

logger = logging.getLogger("FetchOpenRouterConfig")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--model",
        action="append",
        default=[],
        help="OpenRouter model ID to fetch (repeatable).",
    )
    parser.add_argument(
        "--write-mode",
        choices=["merge", "replace"],
        default="merge",
        help="merge: update requested models and keep others; replace: keep only requested.",
    )
    parser.add_argument(
        "--default-model",
        default="",
        help="Optional default model ID to set after update.",
    )
    parser.add_argument(
        "--output",
        default="protocol_monk/config/openrouter_models.json",
        help="Output map path.",
    )
    parser.add_argument(
        "--base-url",
        default="https://openrouter.ai/api/v1",
        help="OpenRouter API base URL.",
    )
    parser.add_argument(
        "--api-key",
        default="",
        help="Optional API key override (defaults to OPENROUTER_API_KEY).",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=20,
        help="HTTP timeout in seconds.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Build and validate output without writing the file.",
    )
    return parser.parse_args()


def _resolve_output_path(raw_path: str) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path
    return (Path.cwd() / path).resolve()


def _print_summary(config: dict, requested_models: List[str], *, dry_run: bool) -> None:
    models = config.get("models", {})
    model_count = len(models) if isinstance(models, dict) else 0
    print("OpenRouter map update complete.")
    print(f"Requested models: {', '.join(requested_models)}")
    print(f"Map models count: {model_count}")
    print(f"Default model: {config.get('default_model', '')}")
    if dry_run:
        print("Dry run: no file was written.")


def main() -> int:
    args = _parse_args()
    logging.basicConfig(level=logging.INFO)

    model_ids = [str(item or "").strip() for item in args.model if str(item or "").strip()]
    if not model_ids:
        print("Error: at least one --model is required.")
        return 2

    output_path = _resolve_output_path(args.output)
    api_key = str(args.api_key or os.getenv("OPENROUTER_API_KEY") or "").strip()
    requested_default = str(args.default_model or "").strip() or None

    discovery = OpenRouterModelDiscovery(
        output_path,
        base_url=args.base_url,
        api_key=api_key,
        timeout_seconds=args.timeout,
    )

    try:
        config = discovery.build_updated_config(
            model_ids,
            write_mode=args.write_mode,
            default_model=requested_default,
        )
        if not args.dry_run:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(
                json.dumps(config, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            logger.info("Saved OpenRouter model map to %s", output_path)
        _print_summary(config, model_ids, dry_run=args.dry_run)
        return 0
    except ConfigError as exc:
        print(f"Configuration error: {exc}")
        return 1
    except Exception as exc:
        print(f"Unexpected error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

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
from pathlib import Path
from typing import List

from protocol_monk.config.settings import load_settings
from protocol_monk.exceptions.config import ConfigError
from protocol_monk.utils.openrouter_discovery import OpenRouterModelDiscovery

logger = logging.getLogger("FetchOpenRouterConfig")
APP_ROOT = Path(__file__).resolve().parents[1]


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
        default="",
        help="Output map path. Defaults to the resolved OpenRouter runtime map path.",
    )
    parser.add_argument(
        "--sync-example",
        action="store_true",
        help="Also update the tracked openrouter_models.example.json seed file.",
    )
    parser.add_argument(
        "--example-output",
        default="",
        help="Optional example map path when --sync-example is used.",
    )
    parser.add_argument(
        "--base-url",
        default="https://openrouter.ai/api/v1",
        help="OpenRouter API base URL.",
    )
    parser.add_argument(
        "--api-key",
        default="",
        help="Optional API key override (defaults to the repo .env / OPENROUTER_API_KEY).",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=20,
        help="HTTP timeout in seconds.",
    )
    parser.add_argument(
        "--respect-catalog-tool-support",
        action="store_true",
        help=(
            "Do not force supports_tools=true for requested models. "
            "By default, Protocol Monk treats the curated map as authoritative "
            "for tool-capable OpenRouter models."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Build and validate output without writing the file.",
    )
    return parser.parse_args()


def _resolve_output_path(raw_path: str, *, project_root: Path, default_path: Path) -> Path:
    if not str(raw_path or "").strip():
        return default_path.resolve(strict=False)

    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        path = project_root / path
    return path.resolve(strict=False)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _sync_example_map(path: Path, config: dict) -> None:
    _write_json(path, config)
    logger.info("Saved OpenRouter example model map to %s", path)


def _print_summary(
    config: dict,
    requested_models: List[str],
    *,
    dry_run: bool,
    output_path: Path,
    example_path: Path | None = None,
) -> None:
    models = config.get("models", {})
    model_count = len(models) if isinstance(models, dict) else 0
    print("OpenRouter map update complete.")
    print(f"Requested models: {', '.join(requested_models)}")
    print(f"Map models count: {model_count}")
    print(f"Default model: {config.get('default_model', '')}")
    print(f"Runtime map: {output_path}")
    if example_path is not None:
        print(f"Example map: {example_path}")
    if dry_run:
        print("Dry run: no file was written.")


def main() -> int:
    args = _parse_args()
    logging.basicConfig(level=logging.INFO)
    settings = load_settings(APP_ROOT)

    model_ids = [str(item or "").strip() for item in args.model if str(item or "").strip()]
    if not model_ids:
        print("Error: at least one --model is required.")
        return 2

    output_path = _resolve_output_path(
        args.output,
        project_root=settings.project_root,
        default_path=settings.openrouter_models_json_path,
    )
    example_path = (
        _resolve_output_path(
            args.example_output,
            project_root=settings.project_root,
            default_path=settings.resolved_paths.openrouter_example_json,
        )
        if args.sync_example
        else None
    )
    api_key = str(args.api_key or settings.openrouter_api_key or "").strip()
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
            force_supports_tools=not args.respect_catalog_tool_support,
        )
        if not args.dry_run:
            _write_json(output_path, config)
            logger.info("Saved OpenRouter model map to %s", output_path)
            if example_path is not None:
                _sync_example_map(example_path, config)
        _print_summary(
            config,
            model_ids,
            dry_run=args.dry_run,
            output_path=output_path,
            example_path=example_path,
        )
        return 0
    except ConfigError as exc:
        print(f"Configuration error: {exc}")
        return 1
    except Exception as exc:
        print(f"Unexpected error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

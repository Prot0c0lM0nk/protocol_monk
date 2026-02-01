#!/usr/bin/env python3
"""
Bootstrap Configuration for Protocol Monk
=========================================
Lightweight bootstrap that handles only the essential startup configuration.
"""

import os
import argparse
from pathlib import Path
from typing import Optional

from exceptions.config import BootstrapError


class BootstrapConfig:
    """Minimal configuration needed to start the application."""

    def __init__(self):
        self.working_dir: Optional[Path] = None
        self.ui_mode: str = "plain"
        self.config_file = Path(".protocol_config.json")
        self.disable_async_input: bool = False

    def parse_command_line_args(self) -> str:
        """
        Parse command line arguments to determine UI mode.
        Returns: "plain", "rich", or "textual"
        """
        parser = argparse.ArgumentParser(
            prog="protocol-monk",
            description="Protocol Monk - AI-powered terminal agent",
            add_help=False,
        )

        parser.add_argument(
            "--rich",
            action="store_true",
            help="Use Rich-themed UI instead of plain CLI",
        )

        parser.add_argument(
            "--tui", action="store_true", help="Use Textual TUI interface"
        )

        parser.add_argument(
            "--no-async-input",
            action="store_true",
            help="Disable async input system and use traditional blocking input",
        )

        # Parse only known args to avoid conflicts
        args, _ = parser.parse_known_args()

        # Store async input preference
        self.disable_async_input = args.no_async_input

        if args.tui:
            return "textual"
        if args.rich:
            return "rich"
        return "plain"

    def get_working_dir_from_env(self) -> Optional[Path]:
        working_dir_env = os.getenv("PROTOCOL_WORKING_DIR")
        if working_dir_env:
            path = Path(working_dir_env).expanduser().resolve()
            if path.exists() and path.is_dir():
                return path
        return None

    def get_working_dir_from_config(self) -> Optional[Path]:
        if self.config_file.exists():
            try:
                import json

                with open(self.config_file) as f:
                    config = json.load(f)
                    working_dir_str = config.get("working_dir")
                    if working_dir_str:
                        path = Path(working_dir_str).resolve()
                        if path.exists() and path.is_dir():
                            return path
            except (json.JSONDecodeError, OSError, KeyError):
                pass
        return None

    def get_default_working_dir(self) -> Path:
        project_root = Path(__file__).parent.parent.resolve()
        workspace_dir = project_root / "workspace"
        workspace_dir.mkdir(parents=True, exist_ok=True)
        return workspace_dir

    def bootstrap(self) -> tuple[Path, str, bool]:
        self.ui_mode = self.parse_command_line_args()

        self.working_dir = self.get_working_dir_from_env()
        if self.working_dir:
            return self.working_dir, self.ui_mode, self.disable_async_input

        self.working_dir = self.get_working_dir_from_config()
        if self.working_dir:
            return self.working_dir, self.ui_mode, self.disable_async_input

        self.working_dir = self.get_default_working_dir()
        return self.working_dir, self.ui_mode, self.disable_async_input


def bootstrap_application() -> tuple[Path, str, bool]:
    try:
        bootstrap = BootstrapConfig()
        working_dir, ui_mode, disable_async_input = bootstrap.bootstrap()

        test_file = working_dir / ".protocol_bootstrap_test"
        try:
            test_file.touch()
            test_file.unlink()
        except (OSError, PermissionError) as e:
            raise BootstrapError(
                f"Working directory not writable: {working_dir}"
            ) from e

        return working_dir, ui_mode, bootstrap.disable_async_input

    except Exception as e:
        if isinstance(e, BootstrapError):
            raise
        raise BootstrapError(f"Bootstrap failed: {e}") from e

#!/usr/bin/env python3
"""
Bootstrap Configuration for Protocol Monk
=========================================

Lightweight bootstrap that handles only the essential startup configuration:
- Working directory selection
- UI mode selection (--rich flag)
- Minimal environment validation
- No UI dependencies, no interactive prompts

This is the first thing that runs - it must be bulletproof and minimal.
"""

import os
import sys
import argparse
from pathlib import Path
from typing import Optional

from exceptions.config import BootstrapError


class BootstrapConfig:
    """Minimal configuration needed to start the application."""

    def __init__(self):
        self.working_dir: Optional[Path] = None
        self.ui_mode: str = "plain"  # Default to plain CLI
        self.config_file = Path(".protocol_config.json")

    def parse_command_line_args(self) -> str:
        """
        Parse command line arguments to determine UI mode.
        
        Returns:
            str: UI mode ("plain" or "rich")
        """
        parser = argparse.ArgumentParser(
            prog="protocol-monk",
            description="Protocol Monk - AI-powered terminal agent",
            add_help=False  # Don't interfere with --help from agent
        )
        
        parser.add_argument(
            "--rich",
            action="store_true",
            help="Use Rich-themed UI instead of plain CLI"
        )
        
        # Parse only known args to avoid conflicts with other arguments
        args, _ = parser.parse_known_args()
        
        return "rich" if args.rich else "plain"

    def get_working_dir_from_env(self) -> Optional[Path]:
        """Get working directory from environment variable."""
        working_dir_env = os.getenv("PROTOCOL_WORKING_DIR")
        if working_dir_env:
            path = Path(working_dir_env).expanduser().resolve()
            if path.exists() and path.is_dir():
                return path
        return None

    def get_working_dir_from_config(self) -> Optional[Path]:
        """Get working directory from saved config file."""
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
                pass  # Invalid config file, ignore
        return None

    def get_default_working_dir(self) -> Path:
        """Get default working directory (workspace subdirectory)."""
        project_root = Path(__file__).parent.parent.resolve()
        workspace_dir = project_root / "workspace"
        workspace_dir.mkdir(parents=True, exist_ok=True)
        return workspace_dir

    def bootstrap(self) -> tuple[Path, str]:
        """
        Bootstrap the working directory and UI mode.

        Priority order for working directory:
        1. Environment variable PROTOCOL_WORKING_DIR
        2. Saved config file (.protocol_config.json)
        3. Default workspace directory

        Returns:
            tuple[Path, str]: (working_directory, ui_mode)

        Raises:
            BootstrapError: If no valid working directory can be determined
        """
        # Parse command line args first
        self.ui_mode = self.parse_command_line_args()
        
        # Try environment variable first
        self.working_dir = self.get_working_dir_from_env()
        if self.working_dir:
            return self.working_dir, self.ui_mode

        # Try saved config
        self.working_dir = self.get_working_dir_from_config()
        if self.working_dir:
            return self.working_dir, self.ui_mode

        # Fall back to default
        self.working_dir = self.get_default_working_dir()
        return self.working_dir, self.ui_mode


def bootstrap_application() -> tuple[Path, str]:
    """
    Bootstrap the application and return the working directory and UI mode.

    This is the absolute minimum needed to start the application.
    No UI, no interactive prompts, no complex logic.

    Returns:
        tuple[Path, str]: (working_directory, ui_mode)

    Raises:
        BootstrapError: If bootstrap fails
    """
    try:
        bootstrap = BootstrapConfig()
        working_dir, ui_mode = bootstrap.bootstrap()

        # Validate working directory is writable
        test_file = working_dir / ".protocol_bootstrap_test"
        try:
            test_file.touch()
            test_file.unlink()
        except (OSError, PermissionError) as e:
            raise BootstrapError(
                f"Working directory not writable: {working_dir}"
            ) from e

        return working_dir, ui_mode

    except Exception as e:
        if isinstance(e, BootstrapError):
            raise
        raise BootstrapError(f"Bootstrap failed: {e}") from e

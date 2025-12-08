#!/usr/bin/env python3
"""
Session Configuration for Protocol Monk
=======================================

Handles active project directory and Python environment selection.
Updated to prevent 'Configuration Traps' by confirming saved sessions.
"""

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from exceptions import ConfigFileError, DirectorySelectionError


class ActiveSession:
    """Holds the active, runtime-specific project configuration."""

    def __init__(
        self,
        working_dir: Path,
        preferred_env: str,
        venv_path: str,
        directory_name: str,
        is_python_project: bool = False,
    ):
        self.working_dir = working_dir
        self.preferred_env = preferred_env
        self.venv_path = venv_path
        self.directory_name = directory_name
        self.is_python_project = is_python_project


class EnvironmentDetector:
    """Detect current shell environment."""

    @staticmethod
    def detect_current_environment() -> Dict[str, Any]:
        config = {
            "working_dir": str(Path.cwd()),
            "preferred_env": None,
            "venv_path": None,
            "source": "shell",
        }

        # Detect conda
        conda_env = os.environ.get("CONDA_DEFAULT_ENV")
        if conda_env:
            config["preferred_env"] = conda_env
            return config

        # Detect venv
        venv_path = os.environ.get("VIRTUAL_ENV")
        if venv_path:
            config["venv_path"] = venv_path
            return config

        return config


class ConfigFileHandler:
    """Handle saved configuration files."""

    @staticmethod
    def get_config_file_path() -> Path:
        return Path(".protocol_config.json")
    @staticmethod
    def load_saved_config() -> Optional[Dict[str, Any]]:
        config_file = ConfigFileHandler.get_config_file_path()
        if config_file.exists():
            try:
                with open(config_file, "r") as f:
                    return json.load(f)
            except json.JSONDecodeError as e:
                raise ConfigFileError(
                    f"Invalid JSON format in config file {config_file}: {e}",
                    file_path=config_file,
                    operation="load"
                ) from e
            except (OSError, IOError) as e:
                raise ConfigFileError(
                    f"Failed to read config file {config_file}: {e}",
                    file_path=config_file,
                    operation="load"
                ) from e
        return None

    @staticmethod
    def save_config(config: Dict[str, Any]) -> None:
        config_file = ConfigFileHandler.get_config_file_path()
        try:
            with open(config_file, "w") as f:
                json.dump(config, f, indent=2)
        except (OSError, IOError) as e:
            raise ConfigFileError(
                f"Failed to save config file {config_file}: {e}",
                file_path=config_file,
                operation="save"
            ) from e
        except (TypeError, ValueError) as e:
            raise ConfigFileError(
                f"Invalid configuration data for JSON serialization: {e}",
                file_path=config_file,
                operation="save"
            ) from e


def get_desktop_path() -> Path:
    """Get the user's desktop directory."""
    if sys.platform == "darwin" or sys.platform == "win32":
        return Path.home() / "Desktop"

    # Linux fallback
    desktop_path = Path.home() / "Desktop"
    if desktop_path.exists():
        return desktop_path
    return Path.home()


def list_desktop_directories() -> list[Path]:
    desktop = get_desktop_path()
    directories = []
    try:
        for item in desktop.iterdir():
            if item.is_dir():
                directories.append(item)
    except (OSError, IOError) as e:
        raise DirectorySelectionError(
            f"Failed to list directories in desktop path {desktop}: {e}",
            directory_path=desktop
        ) from e
    except PermissionError as e:
        raise DirectorySelectionError(
            f"Permission denied accessing desktop path {desktop}: {e}",
            directory_path=desktop
        ) from e
    return sorted(directories)


def select_directory_interactive() -> Optional[Path]:
    """Interactively select a directory."""
    directories = list_desktop_directories()

    print("\nProtocol Monk Directory Selector")
    print("===============================")

    if not directories:
        print("No directories found on desktop.")
    else:
        for i, directory in enumerate(directories, 1):
            print(f"{i:2d}. {directory.name}")

    print(f"{len(directories) + 1}. Other directory path")
    print(" 0. Exit")

    try:
        choice_input = input("\nEnter choice: ").strip()
        if not choice_input:
            return None

        try:
            choice = int(choice_input)
        except ValueError as e:
            raise DirectorySelectionError(
                f"Invalid choice input '{choice_input}'. Please enter a number.",
                directory_path=None
            ) from e

        if choice == 0:
            return None
        elif 1 <= choice <= len(directories):
            return directories[choice - 1]
        elif choice == len(directories) + 1:
            path_str = input("Enter directory path: ").strip()
            if path_str:
                try:
                    path = Path(path_str).expanduser().resolve()
                    if path.exists() and path.is_dir():
                        return path
                    raise DirectorySelectionError(
                        f"Invalid directory path '{path_str}'. Path does not exist or is not a directory.",
                        directory_path=path
                    )
                except OSError as e:
                    raise DirectorySelectionError(
                        f"Failed to resolve directory path '{path_str}': {e}",
                        directory_path=path_str
                    ) from e
            return None
        else:
            raise DirectorySelectionError(
                f"Invalid choice {choice}. Please choose a number between 0 and {len(directories) + 1}.",
                directory_path=None
            )
    except KeyboardInterrupt:
        raise DirectorySelectionError(
            "Directory selection cancelled by user.",
            directory_path=None
        )


def detect_python_environment(directory: Path) -> Dict[str, Any]:
    """Simple check for Python project indicators."""
    env_info = {}

    # Check for common Python files
    indicators = ["requirements.txt", "pyproject.toml", "setup.py", "environment.yml"]
    env_info["has_python_files"] = any((directory / f).exists() for f in indicators)

    return env_info


def get_directory_configuration(directory: Path) -> Dict[str, Any]:
    """Get config for a selected directory."""
    config = {
        "working_dir": str(directory),
        "directory_name": directory.name,
        "is_python_project": False,
        "preferred_env": None,
        "venv_path": None,
    }

    env_info = detect_python_environment(directory)
    if env_info.get("has_python_files"):
        config["is_python_project"] = True

    return config


# Global session instance
_active_session = None


def initialize_session() -> ActiveSession:
    """
    Main entry point. Checks for saved config but asks user before auto-loading.
    """
    global _active_session

    config_file = ConfigFileHandler.get_config_file_path()

    # 1. Check for saved session
    if config_file.exists():
        config_data = ConfigFileHandler.load_saved_config()
        if config_data:
            print(f"\n📝 Found previous session config:")
            print(f"   📂 Directory: {config_data.get('working_dir')}")
            print(
                f"   🐍 Env: {config_data.get('preferred_env') or config_data.get('venv_path') or 'None'}"
            )

            choice = input("\nResume this session? [Y/n] ").strip().lower()

            if choice not in ("n", "no"):
                # Auto-update environment variables if needed
                env_config = EnvironmentDetector.detect_current_environment()
                # Prefer current shell env if active, otherwise use saved
                current_env = env_config.get("preferred_env")
                if current_env:
                    config_data["preferred_env"] = current_env

                _active_session = ActiveSession(
                    working_dir=Path(config_data["working_dir"]),
                    preferred_env=config_data.get("preferred_env"),
                    venv_path=config_data.get("venv_path"),
                    directory_name=config_data.get("directory_name", "unknown"),
                    is_python_project=config_data.get("is_python_project", False),
                )
                return _active_session
            else:
                print("Discarding saved session...")
                # Optional: config_file.unlink() if you want to delete it

    # 2. Run Interactive Selector
    directory_path = select_directory_interactive()

    if directory_path:
        config_data = get_directory_configuration(directory_path)

        # Capture current shell environment to save with this session
        env_config = EnvironmentDetector.detect_current_environment()
        config_data["preferred_env"] = env_config.get("preferred_env")
        config_data["venv_path"] = env_config.get("venv_path")

        ConfigFileHandler.save_config(config_data)
        print(f"Configuration saved to {config_file}")

        _active_session = ActiveSession(
            working_dir=Path(config_data["working_dir"]),
            preferred_env=config_data.get("preferred_env"),
            venv_path=config_data.get("venv_path"),
            directory_name=config_data.get("directory_name", "unknown"),
            is_python_project=config_data.get("is_python_project", False),
        )
        return _active_session
    else:
        print("No directory selected. Exiting.", file=sys.stderr)
        sys.exit(1)


def get_active_session() -> ActiveSession:
    if _active_session is None:
        raise Exception("Session not initialized.")
    return _active_session

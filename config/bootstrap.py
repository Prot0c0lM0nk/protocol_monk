#!/usr/bin/env python3
"""
Bootstrap Configuration for Protocol Monk
========================================

Lightweight bootstrap that handles only the essential startup configuration:
- Working directory selection
- Minimal environment validation
- No UI dependencies, no interactive prompts

This is the first thing that runs - it must be bulletproof and minimal.
"""

import os
import sys
from pathlib import Path
from typing import Optional

from exceptions.config import BootstrapError


class BootstrapConfig:
    """Minimal configuration needed to start the application."""
    
    def __init__(self):
        self.working_dir: Optional[Path] = None
        self.config_file = Path(".protocol_config.json")
        
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
        
    def bootstrap(self) -> Path:
        """
        Bootstrap the working directory.
        
        Priority order:
        1. Environment variable PROTOCOL_WORKING_DIR
        2. Saved config file (.protocol_config.json)
        3. Default workspace directory
        
        Returns:
            Path: The working directory to use
            
        Raises:
            BootstrapError: If no valid working directory can be determined
        """
        # Try environment variable first
        self.working_dir = self.get_working_dir_from_env()
        if self.working_dir:
            return self.working_dir
            
        # Try saved config
        self.working_dir = self.get_working_dir_from_config()
        if self.working_dir:
            return self.working_dir
            
        # Fall back to default
        self.working_dir = self.get_default_working_dir()
        return self.working_dir


def bootstrap_application() -> Path:
    """
    Bootstrap the application and return the working directory.
    
    This is the absolute minimum needed to start the application.
    No UI, no interactive prompts, no complex logic.
    
    Returns:
        Path: The working directory to use
        
    Raises:
        BootstrapError: If bootstrap fails
    """
    try:
        bootstrap = BootstrapConfig()
        working_dir = bootstrap.bootstrap()
        
        # Validate working directory is writable
        test_file = working_dir / ".protocol_bootstrap_test"
        try:
            test_file.touch()
            test_file.unlink()
        except (OSError, PermissionError) as e:
            raise BootstrapError(f"Working directory not writable: {working_dir}") from e
            
        return working_dir
        
    except Exception as e:
        if isinstance(e, BootstrapError):
            raise
        raise BootstrapError(f"Bootstrap failed: {e}") from e
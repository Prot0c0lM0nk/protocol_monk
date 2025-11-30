#!/usr/bin/env python3
"""
Environment Check Script
========================

Check what environment information is available to detect current
shell environment for Protocol Monk CLI integration.
"""

import os
import sys
from pathlib import Path


def check_environment():
    """Check current environment variables and working directory."""
    print("Protocol Monk Environment Check")
    print("===============================")

    # Current working directory
    cwd = Path.cwd()
    print(f"Current Directory: {cwd}")

    # Python executable
    python_exe = sys.executable
    print(f"Python Executable: {python_exe}")

    # Environment variables related to Python environments
    env_vars = [
        "CONDA_DEFAULT_ENV",
        "CONDA_PREFIX",
        "VIRTUAL_ENV",
        "PATH",
        "PYTHONPATH",
        "SHELL",
    ]

    print("\nRelevant Environment Variables:")
    print("-------------------------------")

    for var in env_vars:
        value = os.environ.get(var, "(not set)")
        if var == "PATH":
            # Show only first few directories
            paths = value.split(os.pathsep) if value != "(not set)" else []
            if len(paths) > 3:
                value = os.pathsep.join(paths[:3]) + "..."
        print(f"{var:20} = {value}")

    # Detect active environment
    print("\nDetected Environment:")
    print("--------------------")

    conda_env = os.environ.get("CONDA_DEFAULT_ENV")
    venv_path = os.environ.get("VIRTUAL_ENV")

    if conda_env:
        print(f"Active Conda Environment: {conda_env}")
        conda_prefix = os.environ.get("CONDA_PREFIX", "(unknown)")
        print(f"Conda Prefix: {conda_prefix}")
    elif venv_path:
        print(f"Active Virtual Environment: {venv_path}")
        venv_name = Path(venv_path).name
        print(f"Virtual Environment Name: {venv_name}")
    else:
        print("No active Python environment (using system Python)")

    # Check if python executable is in a known environment
    python_path = Path(sys.executable)
    if (
        "conda" in str(python_path)
        or "miniconda" in str(python_path)
        or "anaconda" in str(python_path)
    ):
        print(f"Python appears to be from Conda: {python_path}")
    elif venv_path and python_path.is_relative_to(Path(venv_path)):
        print(f"Python appears to be from Virtual Environment: {python_path}")
    else:
        print(f"Python appears to be system Python: {python_path}")


def main():
    """Main function."""
    check_environment()


if __name__ == "__main__":
    main()

"""Workspace path helpers for NeuralSym."""

from __future__ import annotations

from pathlib import Path


def resolve_workspace_root(workspace_root: str | Path) -> Path:
    """Normalize the workspace root path."""

    return Path(workspace_root).resolve(strict=False)


def resolve_workspace_id(workspace_root: str | Path) -> str:
    """Use the normalized workspace path as a stable workspace ID."""

    return str(resolve_workspace_root(workspace_root))


def resolve_state_dir(workspace_root: str | Path, dirname: str) -> Path:
    """Resolve the NeuralSym state directory inside the workspace."""

    root = resolve_workspace_root(workspace_root)
    return (root / dirname).resolve(strict=False)

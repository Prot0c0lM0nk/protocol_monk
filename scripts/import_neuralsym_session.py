#!/usr/bin/env python3
"""Import a Protocol Monk session transcript into NeuralSym workspace state."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from protocol_monk.plugins.neuralsym.importer import import_session_to_workspace_state


def _resolve_session_path(
    *,
    session: str | None,
    session_workspace: str | None,
    latest: bool,
) -> Path:
    if session:
        return Path(session).expanduser().resolve()

    workspace_root = Path(session_workspace or Path.cwd()).expanduser().resolve()
    sessions_dir = workspace_root / ".protocol_monk" / "sessions"
    if not sessions_dir.exists():
        raise FileNotFoundError(f"Session directory not found: {sessions_dir}")

    candidates = sorted(
        sessions_dir.glob("*.jsonl"),
        key=lambda path: path.stat().st_mtime if path.exists() else 0,
        reverse=True,
    )
    if not candidates:
        raise FileNotFoundError(f"No session files found in {sessions_dir}")

    if latest or not session:
        return candidates[0]
    return candidates[0]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session", type=str, help="Path to a specific session JSONL file")
    parser.add_argument(
        "--session-workspace",
        type=str,
        help="Workspace root containing .protocol_monk/sessions",
    )
    parser.add_argument("--latest", action="store_true", help="Import the latest session file")
    parser.add_argument(
        "--workspace",
        type=str,
        required=True,
        help="Workspace root that should receive the NeuralSym state",
    )
    parser.add_argument(
        "--state-dirname",
        type=str,
        default=".protocol_monk/neuralsym",
        help="Workspace-local NeuralSym state directory",
    )
    parser.add_argument(
        "--advice-token-budget",
        type=int,
        default=256,
        help="Advisory token budget recorded in mission-control input",
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    args = parser.parse_args(argv)

    session_path = _resolve_session_path(
        session=args.session,
        session_workspace=args.session_workspace,
        latest=args.latest,
    )
    result = import_session_to_workspace_state(
        session_path=session_path,
        workspace_root=args.workspace,
        state_dirname=args.state_dirname,
        advice_token_budget=args.advice_token_budget,
    )

    if args.json:
        print(result.model_dump_json(indent=2))
    else:
        print(f"Session: {result.session_path}")
        print(f"Workspace: {args.workspace}")
        print(f"State dir: {result.state_dir}")
        print(f"Imported observations: {result.imported_observations}")
        print(f"Total observations: {result.total_observations}")
        print(f"Skipped duplicate: {result.skipped_duplicate}")
        print(f"Policy signals: {result.policy_signal_count}")
        print(f"Feedback events: {result.feedback_event_count}")
        print(f"Directives: {result.directive_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

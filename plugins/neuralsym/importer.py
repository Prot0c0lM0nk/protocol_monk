"""Offline session import into workspace-scoped NeuralSym state."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

from pydantic import Field

from .advisor import MissionControlAdvisor, NoOpAdvisor
from .bootstrap import (
    bootstrap_observations_from_session_path,
    load_admissible_session_records,
)
from .models import AdviceSnapshot, NeuralSymBaseModel, RuntimeState, WorkspaceProfile
from .storage import NeuralSymStorage
from .workspace import resolve_state_dir, resolve_workspace_id, resolve_workspace_root


class SessionImportResult(NeuralSymBaseModel):
    """Structured result for one session import."""

    workspace_id: str
    state_dir: str
    session_path: str
    session_id: str | None = None
    imported_observations: int = Field(ge=0)
    total_observations: int = Field(ge=0)
    skipped_duplicate: bool = False
    policy_signal_count: int = Field(ge=0)
    feedback_event_count: int = Field(ge=0)
    directive_count: int = Field(ge=0)


def import_session_to_workspace_state(
    *,
    session_path: str | Path,
    workspace_root: str | Path,
    state_dirname: str = ".protocol_monk/neuralsym",
    advice_token_budget: int = 256,
    advisor: MissionControlAdvisor | NoOpAdvisor | None = None,
) -> SessionImportResult:
    """Import one transcript session into workspace NeuralSym storage."""

    return asyncio.run(
        import_session_to_workspace_state_async(
            session_path=session_path,
            workspace_root=workspace_root,
            state_dirname=state_dirname,
            advice_token_budget=advice_token_budget,
            advisor=advisor,
        )
    )


async def import_session_to_workspace_state_async(
    *,
    session_path: str | Path,
    workspace_root: str | Path,
    state_dirname: str = ".protocol_monk/neuralsym",
    advice_token_budget: int = 256,
    advisor: MissionControlAdvisor | NoOpAdvisor | None = None,
) -> SessionImportResult:
    """Import one transcript session into workspace NeuralSym storage."""

    workspace_path = resolve_workspace_root(workspace_root)
    workspace_id = resolve_workspace_id(workspace_path)
    state_dir = resolve_state_dir(workspace_path, state_dirname)
    storage = NeuralSymStorage(state_dir)
    storage.ensure_state_dir()

    records = load_admissible_session_records(session_path)
    session_id = records[0].session_id if records else None

    runtime_state = storage.load_runtime_state() or RuntimeState(workspace_id=workspace_id)
    if session_id is not None and session_id in runtime_state.imported_session_ids:
        profile = storage.load_workspace_profile() or WorkspaceProfile(
            workspace_id=workspace_id,
            workspace_root=str(workspace_path),
        )
        snapshot = storage.load_advice_snapshot() or AdviceSnapshot(workspace_id=workspace_id)
        return SessionImportResult(
            workspace_id=workspace_id,
            state_dir=str(state_dir),
            session_path=str(Path(session_path).resolve()),
            session_id=session_id,
            imported_observations=0,
            total_observations=len(storage.load_observations()),
            skipped_duplicate=True,
            policy_signal_count=len(profile.policy_signals),
            feedback_event_count=len(profile.feedback_events),
            directive_count=len(snapshot.directives),
        )

    imported_observations = bootstrap_observations_from_session_path(
        session_path,
        workspace_id=workspace_id,
    )
    existing_observations = storage.load_observations()
    all_observations = [*existing_observations, *imported_observations]
    storage.save_observations(all_observations)

    profile = storage.load_workspace_profile() or WorkspaceProfile(
        workspace_id=workspace_id,
        workspace_root=str(workspace_path),
    )
    resolved_advisor = advisor or MissionControlAdvisor(
        advice_token_budget=advice_token_budget
    )
    if imported_observations:
        profile, snapshot = await resolved_advisor.build_snapshot(
            profile=profile,
            observations=all_observations,
            turn_id=None,
            round_index=None,
        )
    else:
        snapshot = storage.load_advice_snapshot() or AdviceSnapshot(workspace_id=workspace_id)

    if session_id is not None:
        runtime_state.imported_session_ids = sorted(
            set(runtime_state.imported_session_ids + [session_id])
        )
    runtime_state.imported_observation_count += len(imported_observations)
    runtime_state.last_imported_at = time.time()

    storage.save_workspace_profile(profile)
    storage.save_advice_snapshot(snapshot)
    storage.save_runtime_state(runtime_state)

    return SessionImportResult(
        workspace_id=workspace_id,
        state_dir=str(state_dir),
        session_path=str(Path(session_path).resolve()),
        session_id=session_id,
        imported_observations=len(imported_observations),
        total_observations=len(all_observations),
        skipped_duplicate=False,
        policy_signal_count=len(profile.policy_signals),
        feedback_event_count=len(profile.feedback_events),
        directive_count=len(snapshot.directives),
    )

"""Advisor implementations for NeuralSym."""

from __future__ import annotations

import time

from .models import AdviceSnapshot, Observation, WorkspaceProfile


class NoOpAdvisor:
    """Scaffold advisor that preserves typed flow without generating advice."""

    async def build_snapshot(
        self,
        *,
        profile: WorkspaceProfile,
        observations: list[Observation],
        turn_id: str | None = None,
        round_index: int | None = None,
    ) -> tuple[WorkspaceProfile, AdviceSnapshot]:
        profile.updated_at = time.time()
        snapshot = AdviceSnapshot(
            workspace_id=profile.workspace_id,
            generated_at=time.time(),
            turn_id=turn_id,
            round_index=round_index,
            directives=[],
        )
        return profile, snapshot

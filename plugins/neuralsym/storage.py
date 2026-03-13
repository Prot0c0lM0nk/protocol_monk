"""File-backed structured persistence for NeuralSym."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from .models import (
    AdviceSnapshot,
    Observation,
    ObservationAdapter,
    RuntimeState,
    WorkspaceProfile,
)


class NeuralSymStorage:
    """Persist typed NeuralSym state under a workspace-local directory."""

    def __init__(self, state_dir: Path):
        self.state_dir = Path(state_dir)
        self.workspace_profile_path = self.state_dir / "workspace_profile.json"
        self.observations_path = self.state_dir / "observations.jsonl"
        self.advice_snapshot_path = self.state_dir / "advice_snapshot.json"
        self.runtime_state_path = self.state_dir / "runtime_state.json"

    def ensure_state_dir(self) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)

    def save_workspace_profile(self, profile: WorkspaceProfile) -> None:
        self.ensure_state_dir()
        self._atomic_write(self.workspace_profile_path, profile.model_dump_json(indent=2))

    def load_workspace_profile(self) -> WorkspaceProfile | None:
        if not self.workspace_profile_path.exists():
            return None
        return WorkspaceProfile.model_validate_json(
            self.workspace_profile_path.read_text(encoding="utf-8")
        )

    def append_observation(self, observation: Observation) -> None:
        self.ensure_state_dir()
        with self.observations_path.open("a", encoding="utf-8") as handle:
            handle.write(observation.model_dump_json())
            handle.write("\n")

    def load_observations(self) -> list[Observation]:
        if not self.observations_path.exists():
            return []
        observations: list[Observation] = []
        for line in self.observations_path.read_text(encoding="utf-8").splitlines():
            raw = line.strip()
            if not raw:
                continue
            observations.append(ObservationAdapter.validate_json(raw))
        return observations

    def save_advice_snapshot(self, snapshot: AdviceSnapshot) -> None:
        self.ensure_state_dir()
        self._atomic_write(self.advice_snapshot_path, snapshot.model_dump_json(indent=2))

    def load_advice_snapshot(self) -> AdviceSnapshot | None:
        if not self.advice_snapshot_path.exists():
            return None
        return AdviceSnapshot.model_validate_json(
            self.advice_snapshot_path.read_text(encoding="utf-8")
        )

    def save_runtime_state(self, state: RuntimeState) -> None:
        self.ensure_state_dir()
        self._atomic_write(self.runtime_state_path, state.model_dump_json(indent=2))

    def load_runtime_state(self) -> RuntimeState | None:
        if not self.runtime_state_path.exists():
            return None
        return RuntimeState.model_validate_json(
            self.runtime_state_path.read_text(encoding="utf-8")
        )

    def _atomic_write(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            delete=False,
            suffix=".tmp",
        ) as handle:
            handle.write(content)
            tmp_path = handle.name
        os.replace(tmp_path, path)

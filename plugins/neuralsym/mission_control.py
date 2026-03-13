"""Mission-control model contracts for NeuralSym."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from .models import (
    AdviceDirective,
    ExplicitUserPreferenceObservation,
    FeedbackEvent,
    NeuralSymBaseModel,
    Observation,
    PolicySignal,
    SCHEMA_VERSION,
    ToolResultObservation,
    WorkspaceProfile,
)

MissionControlReasonCode = Literal[
    "explicit_user_override",
    "recent_tool_failure",
    "workspace_policy",
    "turn_context",
    "insufficient_evidence",
]


class MissionControlInput(NeuralSymBaseModel):
    """Structured context packet for the isolated advisor model."""

    schema_version: int = SCHEMA_VERSION
    workspace_id: str
    workspace_root: str
    turn_id: str | None = None
    round_index: int | None = None
    advice_token_budget: int = Field(ge=1)
    available_tool_names: list[str] = Field(default_factory=list)
    active_policy_signals: list[PolicySignal] = Field(default_factory=list)
    feedback_events: list[FeedbackEvent] = Field(default_factory=list)
    recent_observations: list[Observation] = Field(default_factory=list)
    current_turn_observations: list[Observation] = Field(default_factory=list)
    recent_failures: list[ToolResultObservation] = Field(default_factory=list)
    recent_user_overrides: list[ExplicitUserPreferenceObservation] = Field(default_factory=list)


class MissionControlOutput(NeuralSymBaseModel):
    """Strict structured output boundary for the advisor model."""

    schema_version: int = SCHEMA_VERSION
    workspace_id: str
    turn_id: str | None = None
    round_index: int | None = None
    policy_signals_to_upsert: list[PolicySignal] = Field(default_factory=list)
    turn_directives: list[AdviceDirective] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    reason_codes: list[MissionControlReasonCode] = Field(default_factory=list)


def build_mission_control_input(
    *,
    profile: WorkspaceProfile,
    observations: list[Observation],
    available_tool_names: list[str],
    advice_token_budget: int,
    turn_id: str | None = None,
    round_index: int | None = None,
    max_recent_observations: int = 32,
) -> MissionControlInput:
    """Build the isolated model context from structured NeuralSym state."""

    recent_observations = observations[-max(1, max_recent_observations) :]
    current_turn_observations = [
        observation
        for observation in recent_observations
        if turn_id is not None and observation.correlation.turn_id == turn_id
    ]
    recent_failures = [
        observation
        for observation in recent_observations
        if isinstance(observation, ToolResultObservation) and not observation.success
    ]
    recent_user_overrides = [
        observation
        for observation in recent_observations
        if isinstance(observation, ExplicitUserPreferenceObservation)
    ]

    return MissionControlInput(
        workspace_id=profile.workspace_id,
        workspace_root=profile.workspace_root,
        turn_id=turn_id,
        round_index=round_index,
        advice_token_budget=advice_token_budget,
        available_tool_names=sorted({str(name) for name in available_tool_names if str(name).strip()}),
        active_policy_signals=profile.policy_signals,
        feedback_events=profile.feedback_events,
        recent_observations=recent_observations,
        current_turn_observations=current_turn_observations,
        recent_failures=recent_failures,
        recent_user_overrides=recent_user_overrides,
    )


def empty_mission_control_output(
    *,
    workspace_id: str,
    turn_id: str | None = None,
    round_index: int | None = None,
) -> MissionControlOutput:
    """Return the empty structured result for no-advice cases."""

    return MissionControlOutput(
        workspace_id=workspace_id,
        turn_id=turn_id,
        round_index=round_index,
        confidence=0.0,
        reason_codes=["insufficient_evidence"],
    )

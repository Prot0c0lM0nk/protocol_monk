"""Typed NeuralSym models and unions."""

from __future__ import annotations

import time
import uuid
from typing import Annotated, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

SCHEMA_VERSION = 1


def _new_id() -> str:
    return str(uuid.uuid4())


class NeuralSymBaseModel(BaseModel):
    """Base model with strict extra-field handling."""

    model_config = ConfigDict(extra="forbid")


class CorrelationRef(NeuralSymBaseModel):
    """Stable runtime correlation fields."""

    turn_id: str | None = None
    pass_id: str | None = None
    tool_call_id: str | None = None
    round_index: int | None = None
    tool_index: int | None = None


class ObservationBase(NeuralSymBaseModel):
    """Common fields for persisted observations."""

    schema_version: int = SCHEMA_VERSION
    id: str = Field(default_factory=_new_id)
    timestamp: float = Field(default_factory=time.time)
    workspace_id: str
    correlation: CorrelationRef = Field(default_factory=CorrelationRef)


class UserInputObservation(ObservationBase):
    kind: Literal["user_input"] = "user_input"
    request_id: str
    source: str
    text_length: int = Field(ge=0)
    has_context: bool = False


class AssistantPassObservation(ObservationBase):
    kind: Literal["assistant_pass"] = "assistant_pass"
    response_pass_id: str
    content_length: int = Field(ge=0)
    thinking_length: int = Field(ge=0)
    tool_call_count: int = Field(ge=0)
    tool_call_names: list[str] = Field(default_factory=list)
    total_tokens: int = Field(ge=0)


class ToolResultObservation(ObservationBase):
    kind: Literal["tool_result"] = "tool_result"
    tool_name: str
    success: bool
    duration_seconds: float = Field(ge=0.0)
    output_kind: str | None = None
    error_code: str | None = None
    had_error: bool = False
    request_parameter_keys: list[str] = Field(default_factory=list)


class ExplicitUserPreferenceObservation(ObservationBase):
    kind: Literal["explicit_user_preference"] = "explicit_user_preference"
    signal_kind: Literal["explicit_user_override"] = "explicit_user_override"
    override_kind: Literal[
        "avoid_tool",
        "prefer_narrow_reads",
        "preserve_boundaries",
    ]
    target_tool_name: str | None = None
    source_kind: Literal["tool_rejection", "operator_command", "session_input"]


Observation: TypeAlias = Annotated[
    UserInputObservation
    | AssistantPassObservation
    | ToolResultObservation
    | ExplicitUserPreferenceObservation,
    Field(discriminator="kind"),
]
ObservationAdapter = TypeAdapter(Observation)


class PolicySignalBase(NeuralSymBaseModel):
    """Persistent workspace policy signal."""

    schema_version: int = SCHEMA_VERSION
    id: str = Field(default_factory=_new_id)
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)
    source_observation_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class ReadStrategySignal(PolicySignalBase):
    kind: Literal["read_strategy"] = "read_strategy"
    strategy: Literal["narrow_first", "broad_first"]
    scope: Literal["workspace", "turn"] = "workspace"


class EditScopeSignal(PolicySignalBase):
    kind: Literal["edit_scope"] = "edit_scope"
    mode: Literal["minimal", "multi_file_allowed"]
    scope: Literal["workspace", "turn"] = "workspace"


class BoundaryRuleSignal(PolicySignalBase):
    kind: Literal["boundary_rule"] = "boundary_rule"
    rule: Literal["preserve_soc", "allow_cross_boundary"]
    scope: Literal["workspace", "turn"] = "workspace"


class ExplicitUserOverrideSignal(PolicySignalBase):
    kind: Literal["explicit_user_override"] = "explicit_user_override"
    override_kind: Literal[
        "avoid_tool",
        "prefer_narrow_reads",
        "preserve_boundaries",
    ]
    target_tool_name: str | None = None
    scope: Literal["workspace", "turn"] = "turn"


PolicySignal: TypeAlias = Annotated[
    ReadStrategySignal
    | EditScopeSignal
    | BoundaryRuleSignal
    | ExplicitUserOverrideSignal,
    Field(discriminator="kind"),
]
PolicySignalAdapter = TypeAdapter(PolicySignal)


class AdviceDirectiveBase(NeuralSymBaseModel):
    """Typed advice directive used for rendering."""

    schema_version: int = SCHEMA_VERSION
    id: str = Field(default_factory=_new_id)
    priority: int = Field(default=100, ge=0)
    scope: Literal["workspace", "turn"] = "workspace"


class ReadStrategyDirective(AdviceDirectiveBase):
    kind: Literal["read_strategy"] = "read_strategy"
    strategy: Literal["narrow_first", "broad_first"]


class EditScopeDirective(AdviceDirectiveBase):
    kind: Literal["edit_scope"] = "edit_scope"
    mode: Literal["minimal", "multi_file_allowed"]


class BoundaryRuleDirective(AdviceDirectiveBase):
    kind: Literal["boundary_rule"] = "boundary_rule"
    rule: Literal["preserve_soc", "allow_cross_boundary"]


class ExplicitUserOverrideDirective(AdviceDirectiveBase):
    kind: Literal["explicit_user_override"] = "explicit_user_override"
    override_kind: Literal[
        "avoid_tool",
        "prefer_narrow_reads",
        "preserve_boundaries",
    ]
    target_tool_name: str | None = None
    scope: Literal["workspace", "turn"] = "turn"


AdviceDirective: TypeAlias = Annotated[
    ReadStrategyDirective
    | EditScopeDirective
    | BoundaryRuleDirective
    | ExplicitUserOverrideDirective,
    Field(discriminator="kind"),
]
AdviceDirectiveAdapter = TypeAdapter(AdviceDirective)


class FeedbackEventBase(NeuralSymBaseModel):
    """Structured feedback event."""

    schema_version: int = SCHEMA_VERSION
    id: str = Field(default_factory=_new_id)
    timestamp: float = Field(default_factory=time.time)
    workspace_id: str
    linked_observation_ids: list[str] = Field(default_factory=list)


class ToolRejectionFeedbackEvent(FeedbackEventBase):
    kind: Literal["tool_rejection"] = "tool_rejection"
    tool_name: str
    reason_code: Literal["user_rejected"] = "user_rejected"


class OperatorCorrectionFeedbackEvent(FeedbackEventBase):
    kind: Literal["operator_correction"] = "operator_correction"
    correction_kind: Literal[
        "prefer_narrow_reads",
        "preserve_boundaries",
        "avoid_tool",
    ]
    target_tool_name: str | None = None


FeedbackEvent: TypeAlias = Annotated[
    ToolRejectionFeedbackEvent | OperatorCorrectionFeedbackEvent,
    Field(discriminator="kind"),
]
FeedbackEventAdapter = TypeAdapter(FeedbackEvent)


class WorkspaceProfile(NeuralSymBaseModel):
    """Workspace-scoped structured policy state."""

    schema_version: int = SCHEMA_VERSION
    workspace_id: str
    workspace_root: str
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)
    policy_signals: list[PolicySignal] = Field(default_factory=list)
    feedback_events: list[FeedbackEvent] = Field(default_factory=list)


class AdviceSnapshot(NeuralSymBaseModel):
    """Most recent structured advice snapshot."""

    schema_version: int = SCHEMA_VERSION
    workspace_id: str
    generated_at: float = Field(default_factory=time.time)
    turn_id: str | None = None
    round_index: int | None = None
    directives: list[AdviceDirective] = Field(default_factory=list)


class ProviderResolutionInfo(NeuralSymBaseModel):
    """Resolved provider/model details for the session."""

    provider_name: Literal["ollama", "openrouter"] | None = None
    model_name: str | None = None
    used_fallback: bool = False
    locked: bool = False
    available: bool = False


class RuntimeState(NeuralSymBaseModel):
    """Persisted runtime counters and provider resolution state."""

    schema_version: int = SCHEMA_VERSION
    workspace_id: str
    observations_received: int = 0
    observations_processed: int = 0
    dropped_observations: int = 0
    queue_depth: int = 0
    last_batch_processed_at: float | None = None
    last_advice_refresh_at: float | None = None
    imported_session_ids: list[str] = Field(default_factory=list)
    imported_observation_count: int = 0
    last_imported_at: float | None = None
    resolution: ProviderResolutionInfo = Field(default_factory=ProviderResolutionInfo)

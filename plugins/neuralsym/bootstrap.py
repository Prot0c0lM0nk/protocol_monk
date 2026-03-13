"""Structured session bootstrap for NeuralSym."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any, Literal, TypeAlias

from pydantic import Field, TypeAdapter

from .models import (
    AssistantPassObservation,
    CorrelationRef,
    ExplicitUserPreferenceObservation,
    NeuralSymBaseModel,
    Observation,
    ToolResultObservation,
    UserInputObservation,
)
from .observer import sort_parameter_keys

ADMISSIBLE_SESSION_EVENT_TYPES = frozenset(
    {
        "user_input_submitted",
        "response_complete",
        "tool_execution_start",
        "tool_result",
        "tool_execution_complete",
    }
)


class SessionCorrelation(NeuralSymBaseModel):
    """Correlation fields lifted from transcript records."""

    turn_id: str | None = None
    pass_id: str | None = None
    tool_call_id: str | None = None
    round_index: int | None = None
    tool_index: int | None = None
    sequence: int | None = None


class SessionRecordBase(NeuralSymBaseModel):
    """Shared transcript record fields."""

    schema_version: int
    session_id: str
    sequence: int
    timestamp: float
    correlation: SessionCorrelation = Field(default_factory=SessionCorrelation)


class SessionToolCall(NeuralSymBaseModel):
    """Reduced transcript tool-call payload."""

    name: str | None = None
    id: str | None = None
    call_id: str | None = None


class UserInputSubmittedPayload(NeuralSymBaseModel):
    """Admissible user-input payload."""

    text: str = ""
    source: str = ""
    request_id: str = ""
    timestamp: float | None = None
    context: dict[str, Any] | None = None


class ResponseCompletePayload(NeuralSymBaseModel):
    """Admissible response-complete payload."""

    pass_id: str | None = None
    turn_id: str | None = None
    round_index: int | None = None
    content: str = ""
    thinking: str = ""
    tokens: int | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    tool_calls: list[SessionToolCall] = Field(default_factory=list)
    has_tool_calls: bool = False


class ToolExecutionStartPayload(NeuralSymBaseModel):
    """Admissible tool-start payload."""

    tool_name: str = ""
    parameters: dict[str, Any] = Field(default_factory=dict)
    tool_call_id: str = ""
    requires_confirmation: bool = False
    turn_id: str | None = None
    pass_id: str | None = None
    round_index: int | None = None
    tool_index: int | None = None


class ToolResultPayload(NeuralSymBaseModel):
    """Admissible tool-result payload."""

    tool_name: str = ""
    tool_call_id: str = ""
    output: dict[str, Any] | None = None
    success: bool
    error: str | None = None
    error_code: str | None = None
    output_kind: str | None = None
    error_details: dict[str, Any] | None = None
    turn_id: str | None = None
    pass_id: str | None = None
    round_index: int | None = None
    tool_index: int | None = None


class ToolExecutionCompletePayload(NeuralSymBaseModel):
    """Admissible tool-complete payload."""

    tool_name: str = ""
    tool_call_id: str = ""
    success: bool
    duration: float = 0.0
    turn_id: str | None = None
    pass_id: str | None = None
    round_index: int | None = None
    tool_index: int | None = None


class UserInputSubmittedRecord(SessionRecordBase):
    event_type: Literal["user_input_submitted"] = "user_input_submitted"
    payload: UserInputSubmittedPayload


class ResponseCompleteRecord(SessionRecordBase):
    event_type: Literal["response_complete"] = "response_complete"
    payload: ResponseCompletePayload


class ToolExecutionStartRecord(SessionRecordBase):
    event_type: Literal["tool_execution_start"] = "tool_execution_start"
    payload: ToolExecutionStartPayload


class ToolResultRecord(SessionRecordBase):
    event_type: Literal["tool_result"] = "tool_result"
    payload: ToolResultPayload


class ToolExecutionCompleteRecord(SessionRecordBase):
    event_type: Literal["tool_execution_complete"] = "tool_execution_complete"
    payload: ToolExecutionCompletePayload


AdmissibleSessionRecord: TypeAlias = Annotated[
    UserInputSubmittedRecord
    | ResponseCompleteRecord
    | ToolExecutionStartRecord
    | ToolResultRecord
    | ToolExecutionCompleteRecord,
    Field(discriminator="event_type"),
]
AdmissibleSessionRecordAdapter = TypeAdapter(AdmissibleSessionRecord)


def load_admissible_session_records(session_path: str | Path) -> list[AdmissibleSessionRecord]:
    """Load only the transcript events NeuralSym can consume safely."""

    path = Path(session_path)
    records: list[AdmissibleSessionRecord] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        raw = line.strip()
        if not raw:
            continue
        data = json.loads(raw)
        if not isinstance(data, dict):
            continue
        if data.get("event_type") not in ADMISSIBLE_SESSION_EVENT_TYPES:
            continue
        records.append(AdmissibleSessionRecordAdapter.validate_python(data))
    return records


def bootstrap_observations_from_session_path(
    session_path: str | Path,
    *,
    workspace_id: str,
) -> list[Observation]:
    """Convert one session transcript into typed NeuralSym observations."""

    records = load_admissible_session_records(session_path)
    return convert_session_records_to_observations(records, workspace_id=workspace_id)


def convert_session_records_to_observations(
    records: list[AdmissibleSessionRecord],
    *,
    workspace_id: str,
) -> list[Observation]:
    """Translate admissible transcript records into NeuralSym observations."""

    starts: dict[tuple[str, str, str], ToolExecutionStartPayload] = {}
    completes: dict[tuple[str, str, str], ToolExecutionCompletePayload] = {}

    for record in records:
        if isinstance(record, ToolExecutionStartRecord):
            starts[_tool_key(record)] = record.payload
        elif isinstance(record, ToolExecutionCompleteRecord):
            completes[_tool_key(record)] = record.payload

    observations: list[Observation] = []
    for record in records:
        correlation = _correlation_ref(record.correlation)
        if isinstance(record, UserInputSubmittedRecord):
            observations.append(
                UserInputObservation(
                    workspace_id=workspace_id,
                    timestamp=record.timestamp,
                    request_id=record.payload.request_id or correlation.turn_id or "",
                    source=record.payload.source,
                    text_length=len(record.payload.text),
                    has_context=bool(record.payload.context),
                    correlation=correlation,
                )
            )
            continue

        if isinstance(record, ResponseCompleteRecord):
            tool_call_names = [
                str(tool_call.name)
                for tool_call in record.payload.tool_calls
                if str(tool_call.name or "").strip()
            ]
            observations.append(
                AssistantPassObservation(
                    workspace_id=workspace_id,
                    timestamp=record.timestamp,
                    response_pass_id=record.payload.pass_id or correlation.pass_id or "",
                    content_length=len(record.payload.content),
                    thinking_length=len(record.payload.thinking),
                    tool_call_count=len(tool_call_names),
                    tool_call_names=tool_call_names,
                    total_tokens=int(record.payload.total_tokens or record.payload.tokens or 0),
                    correlation=correlation,
                )
            )
            continue

        if isinstance(record, ToolResultRecord):
            start_payload = starts.get(_tool_key(record))
            complete_payload = completes.get(_tool_key(record))
            observations.append(
                ToolResultObservation(
                    workspace_id=workspace_id,
                    timestamp=record.timestamp,
                    tool_name=record.payload.tool_name,
                    success=record.payload.success,
                    duration_seconds=float(
                        complete_payload.duration if complete_payload is not None else 0.0
                    ),
                    output_kind=record.payload.output_kind,
                    error_code=record.payload.error_code,
                    had_error=bool(record.payload.error),
                    request_parameter_keys=sort_parameter_keys(
                        start_payload.parameters if start_payload is not None else None
                    ),
                    correlation=correlation,
                )
            )
            if record.payload.error_code == "user_rejected":
                observations.append(
                    ExplicitUserPreferenceObservation(
                        workspace_id=workspace_id,
                        timestamp=record.timestamp,
                        signal_kind="explicit_user_override",
                        override_kind="avoid_tool",
                        target_tool_name=record.payload.tool_name,
                        source_kind="tool_rejection",
                        correlation=correlation,
                    )
                )

    return observations


def _tool_key(record: ToolExecutionStartRecord | ToolResultRecord | ToolExecutionCompleteRecord) -> tuple[str, str, str]:
    correlation = record.correlation
    payload = record.payload
    return (
        str(correlation.turn_id or payload.turn_id or ""),
        str(correlation.pass_id or payload.pass_id or ""),
        str(correlation.tool_call_id or payload.tool_call_id or ""),
    )


def _correlation_ref(correlation: SessionCorrelation) -> CorrelationRef:
    return CorrelationRef(
        turn_id=correlation.turn_id,
        pass_id=correlation.pass_id,
        tool_call_id=correlation.tool_call_id,
        round_index=correlation.round_index,
        tool_index=correlation.tool_index,
    )

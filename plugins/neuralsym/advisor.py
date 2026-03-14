"""Advisor implementations for NeuralSym."""

from __future__ import annotations

import time
from collections import Counter

from .mission_control import (
    MissionControlInput,
    MissionControlOutput,
    build_mission_control_input,
    empty_mission_control_output,
)
from .models import (
    AdviceSnapshot,
    BoundaryRuleDirective,
    BoundaryRuleSignal,
    EditScopeDirective,
    EditScopeSignal,
    ExplicitUserPreferenceObservation,
    ExplicitUserOverrideDirective,
    ExplicitUserOverrideSignal,
    FeedbackEvent,
    Observation,
    OperatorCorrectionFeedbackEvent,
    PolicySignal,
    ReadStrategyDirective,
    ReadStrategySignal,
    ToolRejectionFeedbackEvent,
    ToolResultObservation,
    WorkspaceProfile,
)


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


class DeterministicMissionControlEngine:
    """Schema-first advisor engine that avoids speculative heuristics."""

    def __init__(self, *, workspace_avoid_tool_threshold: int = 2):
        self.workspace_avoid_tool_threshold = max(1, int(workspace_avoid_tool_threshold))

    def infer(self, mission_input: MissionControlInput) -> MissionControlOutput:
        output = empty_mission_control_output(
            workspace_id=mission_input.workspace_id,
            turn_id=mission_input.turn_id,
            round_index=mission_input.round_index,
        )

        policy_upserts: list[PolicySignal] = []
        turn_directives: list[
            ReadStrategyDirective
            | EditScopeDirective
            | BoundaryRuleDirective
            | ExplicitUserOverrideDirective
        ] = []
        reason_codes: list[str] = []

        rejection_counts: Counter[str] = Counter()
        for feedback in mission_input.feedback_events:
            if isinstance(feedback, ToolRejectionFeedbackEvent):
                rejection_counts[feedback.tool_name] += 1

        for tool_name, count in sorted(rejection_counts.items()):
            if count < self.workspace_avoid_tool_threshold:
                continue
            if _has_workspace_avoid_tool_signal(
                mission_input.active_policy_signals,
                tool_name=tool_name,
            ):
                continue
            policy_upserts.append(
                ExplicitUserOverrideSignal(
                    override_kind="avoid_tool",
                    target_tool_name=tool_name,
                    scope="workspace",
                    confidence=min(1.0, 0.5 + (0.15 * count)),
                )
            )
            reason_codes.extend(["explicit_user_override", "workspace_policy"])

        for override in mission_input.current_turn_observations:
            if not isinstance(override, ExplicitUserPreferenceObservation):
                continue
            turn_directives.append(
                ExplicitUserOverrideDirective(
                    override_kind=override.override_kind,
                    target_tool_name=override.target_tool_name,
                    scope="turn",
                    priority=5,
                )
            )
            if override.override_kind in {"prefer_narrow_reads", "preserve_boundaries"}:
                policy_upserts.extend(
                    _workspace_signal_from_explicit_override(override)
                )
            reason_codes.append("explicit_user_override")

        failures_in_turn = [
            observation
            for observation in mission_input.current_turn_observations
            if isinstance(observation, ToolResultObservation) and not observation.success
        ]
        if failures_in_turn:
            reason_codes.append("recent_tool_failure")

        if mission_input.active_policy_signals:
            reason_codes.append("workspace_policy")

        output.policy_signals_to_upsert = _dedupe_policy_signals(policy_upserts)
        output.turn_directives = _dedupe_directives(turn_directives)
        output.reason_codes = _dedupe_reason_codes(reason_codes) or ["insufficient_evidence"]
        if output.turn_directives or output.policy_signals_to_upsert:
            output.confidence = 0.9
        elif mission_input.active_policy_signals:
            output.confidence = 0.6
        return output


class MissionControlAdvisor:
    """Real advisor using structured mission-control I/O."""

    def __init__(
        self,
        *,
        advice_token_budget: int = 256,
        workspace_avoid_tool_threshold: int = 2,
    ):
        self.advice_token_budget = max(1, int(advice_token_budget))
        self.engine = DeterministicMissionControlEngine(
            workspace_avoid_tool_threshold=workspace_avoid_tool_threshold
        )

    async def build_snapshot(
        self,
        *,
        profile: WorkspaceProfile,
        observations: list[Observation],
        turn_id: str | None = None,
        round_index: int | None = None,
    ) -> tuple[WorkspaceProfile, AdviceSnapshot]:
        profile.updated_at = time.time()
        _merge_feedback_events(profile, observations)
        mission_input = build_mission_control_input(
            profile=profile,
            observations=observations,
            available_tool_names=_collect_available_tool_names(observations),
            advice_token_budget=self.advice_token_budget,
            turn_id=turn_id,
            round_index=round_index,
        )
        mission_output = self.engine.infer(mission_input)
        _upsert_policy_signals(profile, mission_output.policy_signals_to_upsert)

        directives = _dedupe_directives(
            _directives_from_policy_signals(profile.policy_signals)
            + mission_output.turn_directives
        )
        snapshot = AdviceSnapshot(
            workspace_id=profile.workspace_id,
            generated_at=time.time(),
            turn_id=turn_id,
            round_index=round_index,
            directives=directives,
        )
        return profile, snapshot


def _collect_available_tool_names(observations: list[Observation]) -> list[str]:
    names: set[str] = set()
    for observation in observations:
        if isinstance(observation, ToolResultObservation):
            if observation.tool_name.strip():
                names.add(observation.tool_name.strip())
        elif hasattr(observation, "tool_call_names"):
            for tool_name in getattr(observation, "tool_call_names", []):
                if str(tool_name).strip():
                    names.add(str(tool_name).strip())
    return sorted(names)


def _merge_feedback_events(profile: WorkspaceProfile, observations: list[Observation]) -> None:
    existing_linked_ids = {
        linked_id
        for event in profile.feedback_events
        for linked_id in event.linked_observation_ids
    }
    for observation in observations:
        if observation.id in existing_linked_ids:
            continue
        if not isinstance(observation, ExplicitUserPreferenceObservation):
            continue
        if observation.override_kind == "avoid_tool" and observation.target_tool_name:
            profile.feedback_events.append(
                ToolRejectionFeedbackEvent(
                    workspace_id=profile.workspace_id,
                    timestamp=observation.timestamp,
                    linked_observation_ids=[observation.id],
                    tool_name=observation.target_tool_name,
                )
            )
            existing_linked_ids.add(observation.id)
            continue
        profile.feedback_events.append(
            OperatorCorrectionFeedbackEvent(
                workspace_id=profile.workspace_id,
                timestamp=observation.timestamp,
                linked_observation_ids=[observation.id],
                correction_kind=observation.override_kind,
                target_tool_name=observation.target_tool_name,
            )
        )
        existing_linked_ids.add(observation.id)


def _workspace_signal_from_explicit_override(
    override: ExplicitUserPreferenceObservation,
) -> list[PolicySignal]:
    if override.override_kind == "prefer_narrow_reads":
        return [
            ReadStrategySignal(
                strategy="narrow_first",
                scope="workspace",
                source_observation_ids=[override.id],
                confidence=1.0,
            )
        ]
    if override.override_kind == "preserve_boundaries":
        return [
            BoundaryRuleSignal(
                rule="preserve_soc",
                scope="workspace",
                source_observation_ids=[override.id],
                confidence=1.0,
            )
        ]
    return []


def _has_workspace_avoid_tool_signal(signals: list[PolicySignal], *, tool_name: str) -> bool:
    for signal in signals:
        if not isinstance(signal, ExplicitUserOverrideSignal):
            continue
        if signal.scope != "workspace":
            continue
        if signal.override_kind == "avoid_tool" and signal.target_tool_name == tool_name:
            return True
    return False


def _policy_key(signal: PolicySignal) -> tuple[str, str | None]:
    if isinstance(signal, ReadStrategySignal):
        return (signal.kind, signal.scope)
    if isinstance(signal, EditScopeSignal):
        return (signal.kind, signal.scope)
    if isinstance(signal, BoundaryRuleSignal):
        return (signal.kind, signal.scope)
    return (
        f"{signal.kind}:{signal.override_kind}:{signal.target_tool_name or ''}",
        signal.scope,
    )


def _upsert_policy_signals(profile: WorkspaceProfile, new_signals: list[PolicySignal]) -> None:
    if not new_signals:
        return
    index = {_policy_key(signal): idx for idx, signal in enumerate(profile.policy_signals)}
    now = time.time()
    for signal in new_signals:
        key = _policy_key(signal)
        if key not in index:
            profile.policy_signals.append(signal)
            index[key] = len(profile.policy_signals) - 1
            continue
        existing = profile.policy_signals[index[key]]
        signal.created_at = existing.created_at
        signal.updated_at = now
        signal.source_observation_ids = sorted(
            set(existing.source_observation_ids + signal.source_observation_ids)
        )
        signal.confidence = max(existing.confidence, signal.confidence)
        profile.policy_signals[index[key]] = signal


def _directives_from_policy_signals(
    signals: list[PolicySignal],
) -> list[ReadStrategyDirective | EditScopeDirective | BoundaryRuleDirective | ExplicitUserOverrideDirective]:
    directives: list[
        ReadStrategyDirective | EditScopeDirective | BoundaryRuleDirective | ExplicitUserOverrideDirective
    ] = []
    for signal in signals:
        if isinstance(signal, ReadStrategySignal):
            directives.append(
                ReadStrategyDirective(
                    strategy=signal.strategy,
                    scope=signal.scope,
                    priority=30,
                )
            )
        elif isinstance(signal, EditScopeSignal):
            directives.append(
                EditScopeDirective(
                    mode=signal.mode,
                    scope=signal.scope,
                    priority=40,
                )
            )
        elif isinstance(signal, BoundaryRuleSignal):
            directives.append(
                BoundaryRuleDirective(
                    rule=signal.rule,
                    scope=signal.scope,
                    priority=20,
                )
            )
        elif isinstance(signal, ExplicitUserOverrideSignal):
            directives.append(
                ExplicitUserOverrideDirective(
                    override_kind=signal.override_kind,
                    target_tool_name=signal.target_tool_name,
                    scope=signal.scope,
                    priority=10 if signal.scope == "workspace" else 5,
                )
            )
    return directives


def _directive_key(
    directive: ReadStrategyDirective
    | EditScopeDirective
    | BoundaryRuleDirective
    | ExplicitUserOverrideDirective,
) -> tuple[str, str | None, str | None]:
    if isinstance(directive, ReadStrategyDirective):
        return (directive.kind, directive.scope, directive.strategy)
    if isinstance(directive, EditScopeDirective):
        return (directive.kind, directive.scope, directive.mode)
    if isinstance(directive, BoundaryRuleDirective):
        return (directive.kind, directive.scope, directive.rule)
    return (
        f"{directive.kind}:{directive.override_kind}",
        directive.scope,
        directive.target_tool_name,
    )


def _dedupe_policy_signals(signals: list[PolicySignal]) -> list[PolicySignal]:
    deduped: dict[tuple[str, str | None], PolicySignal] = {}
    for signal in signals:
        deduped[_policy_key(signal)] = signal
    return list(deduped.values())


def _dedupe_directives(
    directives: list[
        ReadStrategyDirective | EditScopeDirective | BoundaryRuleDirective | ExplicitUserOverrideDirective
    ],
) -> list[
    ReadStrategyDirective | EditScopeDirective | BoundaryRuleDirective | ExplicitUserOverrideDirective
]:
    deduped: dict[tuple[str, str | None, str | None], object] = {}
    for directive in directives:
        deduped[_directive_key(directive)] = directive
    return list(deduped.values())


def _dedupe_reason_codes(reason_codes: list[str]) -> list[str]:
    ordered: list[str] = []
    for reason_code in reason_codes:
        if reason_code not in ordered:
            ordered.append(reason_code)
    return ordered

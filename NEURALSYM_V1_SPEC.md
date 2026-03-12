# NeuralSym V1 Specification

## Status

- Status: proposed
- Scope: Protocol Monk integration target and reusable package shape
- Version target: v1

## Mission

NeuralSym v1 is a workspace-scoped, advise-only policy memory and guidance plugin for LLM agents.

Its job is to help the agent act in ways that fit the current workspace's norms and the operator's preferences. It should reduce policy-misaligned behavior, not chase a universal notion of "best" tool use.

For Protocol Monk, NeuralSym should:

- listen passively to the current session
- persist learning per workspace/project
- synthesize compact advisory guidance before model calls
- remain optional and non-blocking
- remain reusable outside Protocol Monk

## Product Promise

NeuralSym v1 does not promise "fewer bad tool choices" in the abstract.

It promises:

- better alignment with workspace-specific working style
- better adherence to operator preferences
- better advisory guidance about approach selection
- better continuity of policy across sessions in the same workspace

Examples:

- In a codebase workspace, guidance may prefer narrow reads, domain boundaries, and separation of concerns.
- In a book or research workspace, guidance may prefer broad reading before action.

## Non-Goals

NeuralSym v1 will not:

- block, override, or auto-execute actions
- replace the main agent loop
- become a second autonomous planner
- own UI concerns
- own provider streaming
- depend on simulation scripts or dashboards
- maintain a separate "small model" architecture branch

Model-specific behavior belongs in advice rendering and runtime configuration, not in a split subsystem.

## Design Principles

1. Advise-only
   NeuralSym may recommend, warn, summarize, or highlight preferences. It must not directly enforce behavior in v1.

2. Workspace-scoped memory
   Learned state belongs to the active workspace, not to the global machine profile.

3. Deterministic core
   Observation capture, state persistence, and guidance injection boundaries should be deterministic. LLM use is reserved for interpretation and summarization.

4. Optional integration
   Protocol Monk should remain fully functional when NeuralSym is disabled or unavailable.

5. Narrow injection
   NeuralSym should emit a compact advisory system message for the next pass rather than growing the persistent conversation history.

6. Reusable package shape
   Core NeuralSym concepts should not depend on Protocol Monk-specific types.

## Placement In Protocol Monk

NeuralSym should live under a tracked plugin/extension surface inside `protocol_monk/`.

Recommended package root:

`protocol_monk/plugins/neuralsym/`

Rationale:

- keeps the feature in the tracked package surface
- avoids polluting core agent modules
- makes optional startup wiring explicit
- provides a clean extraction path later if NeuralSym becomes its own package

## Integration Strategy

Protocol Monk already has the correct injection seam:

- `AgentService` composes optional system injections into the model history
- the provider loop remains unaware of those injections

NeuralSym should integrate at that seam.

### Required Protocol Monk Touchpoints

1. Startup wiring
   `protocol_monk/main.py`

2. Per-turn advisory injection
   `protocol_monk/agent/core/service.py`

3. Observation capture from runtime events
   Prefer `AgentService` and `ContextCoordinator` boundaries over provider internals

4. Optional event subscriptions
   `protocol_monk/protocol/bus.py`

### Explicit Non-Integration Areas

NeuralSym should not integrate directly into:

- provider streaming adapters
- UI renderers
- tool implementations
- low-level context token counting

## Runtime Model

NeuralSym should be model-managed, but not model-driven end-to-end.

### Meaning

An LLM may be used to:

- interpret observations
- infer durable workspace policy signals
- compress session experience into reusable advice state
- generate compact advisory guidance

An LLM should not be used to:

- own the event loop
- decide whether observations are persisted
- mutate persistent state without schema boundaries
- replace deterministic policy storage and retrieval

## Provider And Model Policy

NeuralSym needs its own configurable runtime model selection.

### v1 Rule

Each NeuralSym runtime instance uses one active provider for the session.

### Recommended Resolution Policy

1. Prefer a small local Ollama model.
2. If local resolution is unavailable and fallback is enabled, resolve once to a configured OpenRouter model.
3. Lock that provider/model choice for the session.
4. Do not mix providers mid-session.

### Rationale

- preserves predictability
- avoids provider churn inside the advisory loop
- lets NeuralSym stay cheap
- supports local-first operation

### Recommended Default

- default provider preference: `ollama`
- default use case: small local summarizer/instruction model
- optional fallback: inexpensive OpenRouter model

## Core Domain Model

NeuralSym v1 should model policy-aligned behavior, not raw success/failure statistics alone.

### Entities

#### WorkspaceProfile

Persistent per-workspace state describing stable norms and preferences.

Fields:

- `workspace_id`
- `workspace_root`
- `created_at`
- `updated_at`
- `policy_signals`
- `preference_overrides`
- `confidence_summary`
- `runtime_metadata`

#### Observation

A structured fact captured from the host agent runtime.

Observation kinds:

- `user_request`
- `assistant_pass`
- `tool_request`
- `tool_result`
- `user_correction`
- `user_rejection`
- `system_command`
- `session_summary`

Required fields:

- `id`
- `timestamp`
- `workspace_id`
- `kind`
- `payload`
- `correlation`

#### PolicySignal

A durable workspace-specific rule or tendency.

Examples:

- prefer narrow file reads before edits
- preserve separation of concerns during code changes
- avoid broad scans unless the user explicitly asks
- in this workspace, completeness is preferred over speed

Fields:

- `id`
- `category`
- `statement`
- `scope`
- `strength`
- `evidence_refs`
- `source`
- `created_at`
- `updated_at`

#### AdviceSnapshot

The current compact advisory state used to build the next guidance injection.

Fields:

- `workspace_id`
- `generated_at`
- `summary`
- `active_preferences`
- `active_cautions`
- `active_defaults`
- `confidence_notes`

#### FeedbackEvent

A structured signal indicating operator approval, correction, or preference clarification.

Fields:

- `id`
- `timestamp`
- `workspace_id`
- `feedback_type`
- `payload`
- `linked_observation_ids`

## Architecture

Recommended package layout:

```text
protocol_monk/plugins/neuralsym/
├── __init__.py
├── adapter_protocol_monk.py
├── config.py
├── runtime.py
├── observer.py
├── advisor.py
├── renderer.py
├── models.py
├── storage.py
├── workspace.py
└── prompts/
```

### Module Responsibilities

#### `config.py`

Defines NeuralSym runtime settings.

Examples:

- enabled flag
- provider preference
- fallback policy
- model name
- advice token budget
- batch window
- persistence directory name

#### `models.py`

Defines the NeuralSym domain objects and serialization schemas.

#### `storage.py`

Handles workspace-scoped persistence for:

- observations
- workspace profile
- advice snapshot
- optional compaction metadata

This layer should be deterministic and file-backed.

#### `observer.py`

Converts Protocol Monk runtime activity into structured `Observation` records.

#### `advisor.py`

Owns policy interpretation and advice generation.

Responsibilities:

- merge new observations
- update policy signals
- produce a fresh `AdviceSnapshot`

This is the main place where a model-backed summarizer/interpreter is allowed.

#### `renderer.py`

Builds the compact advisory system message for the next model pass.

This must be deterministic from `AdviceSnapshot` plus runtime settings.

#### `runtime.py`

Owns the internal async queue and worker lifecycle.

Responsibilities:

- accept observations quickly
- queue background interpretation work
- cache the latest advice snapshot
- expose a `get_advice_message()` method for `AgentService`

#### `adapter_protocol_monk.py`

Thin integration layer between Protocol Monk types/events and NeuralSym.

## Event Flow

### Passive Learning Path

1. Protocol Monk processes user input, model passes, and tool results as usual.
2. NeuralSym receives structured observations from integration hooks.
3. NeuralSym writes observations to workspace-scoped storage.
4. A background worker batches observations and updates policy state.
5. The latest `AdviceSnapshot` is cached for future requests.

### Advisory Injection Path

1. `AgentService` prepares history for a model pass.
2. `AgentService` requests the latest NeuralSym advice message.
3. If advice is available, it is inserted as an ephemeral system injection.
4. The provider receives the composed history.

### Failure Behavior

If NeuralSym is:

- disabled
- unconfigured
- behind on processing
- unable to reach its configured model
- internally inconsistent

then Protocol Monk continues without NeuralSym advice.

## Concurrency Model

NeuralSym must not perform blocking model work directly inside event-bus handlers.

Reason:

- Protocol Monk's event bus is sequential
- slow subscribers would stall agent progress

### Required Design

- observation ingestion must be fast
- expensive interpretation must run in a background worker
- advisory reads must be non-blocking or bounded

### Recommended Mechanism

- internal `asyncio.Queue`
- single background worker in v1
- bounded retries
- cached last-known-good advice snapshot

## Persistence Model

Learning persists per workspace/project.

Recommended location inside each workspace:

`.protocol_monk/neuralsym/`

Recommended files:

- `workspace_profile.json`
- `observations.jsonl`
- `advice_snapshot.json`
- `runtime_state.json`

### Rationale

- per-project isolation
- easy inspection and deletion
- no accidental cross-project contamination
- no requirement to track the state in Git

## Advice Format

Advice should be short, explicit, and policy-oriented.

It should not restate the whole workspace profile on every turn.

### Guidance Priorities

1. active workspace preferences
2. relevant cautions
3. default approach guidance
4. concise reasoning only when necessary

### Example Shape

```text
[NEURALSYM ADVICE]
- This workspace prefers narrow reads before edits.
- Preserve separation of concerns; avoid cross-module changes unless required.
- If scanning broadly, explain why the broader read is necessary.
- Treat user preference as higher priority than learned defaults.
```

### Advice Constraints

- token-budgeted
- no long histories
- no hidden chain-of-thought requirements
- no imperative blocking language in v1

## Configuration Surface

NeuralSym should have a dedicated settings object rather than piggybacking entirely on `Settings`.

Suggested fields:

- `enabled: bool`
- `provider: str | None`
- `model: str | None`
- `prefer_local_provider: bool`
- `allow_openrouter_fallback: bool`
- `fallback_model: str | None`
- `advice_token_budget: int`
- `batch_window_seconds: float`
- `max_pending_observations: int`
- `workspace_state_dirname: str`
- `log_level: str`

## Protocol Monk API Contract

The NeuralSym runtime should expose a small host-facing contract.

### Proposed Host Interface

```python
class NeuralSymRuntime:
    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    async def observe(self, observation: Observation) -> None: ...
    async def get_advice_message(self) -> str | None: ...
```

### Proposed Integration Adapter Interface

```python
class ProtocolMonkNeuralSymAdapter:
    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    async def on_user_input(self, payload) -> None: ...
    async def on_tool_result(self, payload) -> None: ...
    async def on_assistant_pass(self, payload) -> None: ...
    async def build_system_message(self) -> Message | None: ...
```

## Interpretation Policy

NeuralSym should treat user preference as the highest-order policy signal.

Priority order:

1. explicit user instruction in the current session
2. stable workspace profile
3. recent session tendencies
4. generic fallback heuristics

This prevents NeuralSym from overfitting to old patterns when the user has already clarified the desired approach.

## Reuse Outside Protocol Monk

To stay plug-and-play in other LLM applications:

- the domain model must not depend on Protocol Monk `Message` objects
- the runtime must accept generic observations
- rendering must return plain text advice
- host-specific behavior belongs in adapters

Protocol Monk is one adapter, not the definition of NeuralSym itself.

## Observability

NeuralSym should emit diagnostics, but diagnostics are not the product.

Useful v1 metrics:

- observations received
- observations processed
- advice refresh count
- last refresh latency
- current provider/model
- queue depth
- advice injection hit rate

## Security And Safety

NeuralSym advice must never be treated as authoritative enforcement in v1.

It may:

- warn
- recommend
- summarize preferences

It may not:

- alter tool parameters
- suppress tool results
- auto-rewrite user intent
- change provider behavior directly

## Migration Guidance From Current `NeuralSym/`

### Keep Conceptually

- evidence-backed learning idea
- compact guidance injection concept
- separation between storage, analysis, and guidance

### Discard Or Replace

- standalone simulation scripts as architecture drivers
- dashboard-first design
- hardcoded intent maps as the main reasoning mechanism
- parallel small-model subsystem
- ambiguous failure semantics like `tool_rejection` for all failures
- unfinished "advanced analytics" placeholders presented as features

### Candidate Concepts To Reuse Carefully

- fact/evidence schemas
- tool outcome recording
- recent guidance trace log

These should be reworked to match the new workspace-policy-centered model.

## Phased Implementation Plan

### Phase 1: Scaffolding

- add plugin package
- add config and runtime skeleton
- add workspace-scoped storage
- wire startup and shutdown

### Phase 2: Passive Observation

- emit structured observations from Protocol Monk
- persist observations per workspace
- add background queue/worker

### Phase 3: Advisory Output

- build workspace profile update loop
- render compact advice injection
- inject advice before model passes

### Phase 4: Preference Learning

- promote user corrections into policy signals
- add confidence tracking
- add observation compaction/summarization

### Phase 5: Optional Enhancements

- richer diagnostics
- import/export workspace profile
- replay tools for inspection

## Acceptance Criteria For V1

NeuralSym v1 is complete when:

- it can be enabled or disabled without affecting Protocol Monk stability
- it persists learning separately for each workspace
- it listens passively and processes observations in the background
- it injects compact advisory guidance before model passes
- it uses a dedicated configurable model/provider selection policy
- it never blocks or overrides actions
- it reflects explicit user preference over learned defaults

## Open Questions

These questions do not block the initial plugin scaffold, but they affect later behavior:

- how aggressively should old observations be compacted
- whether advice should refresh every turn or only after material new evidence
- whether explicit user corrections should be stored as immutable high-priority policy signals
- how much of the advice snapshot should be exposed in `/status` or future metrics surfaces

## Recommendation

Proceed with NeuralSym as a Protocol Monk plugin with:

- a deterministic runtime core
- a model-assisted policy interpreter
- a workspace-scoped persistence layer
- a narrow advisory system injection seam

Do not evolve the existing top-level `NeuralSym/` experiment in place beyond using it as reference material.

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List

# --- 0. Provider Signals (The New Stream Contract) ---


@dataclass
class ProviderSignal:
    """
    A unified signal from the AI Provider.
    Replaces raw string streaming.
    """

    type: str  # "content", "tool_call", "thinking", "metrics", "error"
    data: Any  # str, ToolRequest, or Dict

    # Validation: type must be one of the known constants
    # content -> str
    # thinking -> str
    # tool_call -> ToolRequest (or dict to be converted)
    # metrics -> Dict


# --- 1. Upstream Events (UI -> Agent) ---


@dataclass
class UserRequest:
    """Payload for USER_INPUT_SUBMITTED."""

    text: str
    source: str
    request_id: str
    timestamp: float
    context: Optional[Dict[str, Any]] = None


@dataclass
class ConfirmationResponse:
    """Payload for TOOL_CONFIRMATION_SUBMITTED."""

    tool_call_id: str
    decision: str  # "approved", "rejected", "modified"
    timestamp: float
    modified_parameters: Optional[Dict[str, Any]] = None
    feedback: Optional[str] = None


# --- 2. Downstream Events (Agent -> UI) ---


@dataclass
class AgentStatus:
    """Payload for STATUS_CHANGED."""

    status: str
    message: str
    turn_id: Optional[str] = None
    pass_id: Optional[str] = None
    round_index: Optional[int] = None
    tool_call_id: Optional[str] = None
    tool_index: Optional[int] = None


@dataclass
class AgentResponse:
    """Final output from the Thinking Loop."""

    content: str
    tool_calls: List["ToolRequest"]
    tokens: int
    thinking: str = ""
    pass_id: str = ""
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    provider_metrics: Dict[str, Any] = field(default_factory=dict)


# --- 3. Tool Lifecycle ---


@dataclass
class ToolRequest:
    """Internal object representing a 'Need to run a tool'."""

    name: str
    parameters: Dict[str, Any]
    call_id: str
    requires_confirmation: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolResult:
    """The outcome of an execution."""

    tool_name: str
    call_id: str
    success: bool
    output: Optional[Dict[str, Any]]
    duration: float
    error: Optional[str] = None
    error_code: Optional[str] = None
    output_kind: Optional[str] = None
    error_details: Optional[Dict[str, Any]] = None
    request_parameters: Optional[Dict[str, Any]] = None


# --- 4. Context & Config ---


@dataclass
class Message:
    """Atomic conversation unit."""

    role: str
    content: str
    timestamp: float
    metadata: Dict[str, Any] = field(default_factory=dict)
    # First-class tool support fields (backward compatible - all Optional with None defaults)
    tool_call_id: Optional[str] = None  # For role="tool" messages
    tool_calls: Optional[List[Dict[str, Any]]] = None  # For role="assistant" messages
    name: Optional[str] = None  # Tool name (for role="tool" messages)


@dataclass(frozen=True)
class OrthocalContextFile:
    """Compact metadata for a prepared Orthocal bundle file."""

    index: int
    title: str
    path: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "index": int(self.index),
            "title": str(self.title),
            "path": str(self.path),
        }


@dataclass
class SessionMemoryState:
    """Session-scoped working memory, separate from raw chat history."""

    session_goal: str = ""
    active_work: List[str] = field(default_factory=list)
    decisions: List[str] = field(default_factory=list)
    constraints: List[str] = field(default_factory=list)
    open_loops: List[str] = field(default_factory=list)
    important_paths: List[str] = field(default_factory=list)
    carry_forward_summary: str = ""
    updated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def counts(self) -> Dict[str, int]:
        return {
            "active_work_count": len(self.active_work),
            "decisions_count": len(self.decisions),
            "constraints_count": len(self.constraints),
            "open_loops_count": len(self.open_loops),
            "important_paths_count": len(self.important_paths),
        }

    def is_effectively_empty(self) -> bool:
        return not any(
            [
                str(self.session_goal).strip(),
                any(str(item).strip() for item in self.active_work),
                any(str(item).strip() for item in self.decisions),
                any(str(item).strip() for item in self.constraints),
                any(str(item).strip() for item in self.open_loops),
                any(str(item).strip() for item in self.important_paths),
                str(self.carry_forward_summary).strip(),
            ]
        )

    def to_dict(self) -> Dict[str, Any]:
        payload = {
            "session_goal": str(self.session_goal),
            "active_work": list(self.active_work),
            "decisions": list(self.decisions),
            "constraints": list(self.constraints),
            "open_loops": list(self.open_loops),
            "important_paths": list(self.important_paths),
            "carry_forward_summary": str(self.carry_forward_summary),
            "updated_at": str(self.updated_at),
        }
        payload.update(self.counts())
        payload["active"] = not self.is_effectively_empty()
        return payload


@dataclass
class OrthocalContextCapsule:
    """Prepared Orthocal context kept active for the current session."""

    requested_date: str
    calendar: str
    source_url: str
    summary_md_path: str
    reading_files: List[OrthocalContextFile] = field(default_factory=list)
    story_files: List[OrthocalContextFile] = field(default_factory=list)
    briefing_text: str = ""
    updated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "active": True,
            "requested_date": str(self.requested_date),
            "calendar": str(self.calendar),
            "source_url": str(self.source_url),
            "summary_md_path": str(self.summary_md_path),
            "reading_files": [item.to_dict() for item in self.reading_files],
            "story_files": [item.to_dict() for item in self.story_files],
            "readings_count": len(self.reading_files),
            "stories_count": len(self.story_files),
            "briefing_text": str(self.briefing_text),
            "updated_at": str(self.updated_at),
        }


@dataclass
class ContextStats:
    """Pruning metrics."""

    total_tokens: int
    message_count: int
    loaded_files_count: int


@dataclass
class ModelConfig:
    """Model definition."""

    name: str
    provider: str
    context_window: int
    cost_per_token: Optional[float] = None


# --- 5. Setup & Discovery Events ---


@dataclass
class SetupRequiredPayload:
    """Payload for SETUP_REQUIRED event."""

    missing_files: List[str]


@dataclass
class LocalContextPromptPayload:
    """Payload for LOCAL_CONTEXT_PROMPT event."""

    model_name: str
    default_suggestion: int
    family: str


@dataclass
class DiscoveryCompletePayload:
    """Payload for DISCOVERY_COMPLETE event."""

    models_discovered: int
    active_model: str


@dataclass
class MissingModelDataPayload:
    """Payload for MISSING_MODEL_DATA event."""

    model_name: str
    error_details: str

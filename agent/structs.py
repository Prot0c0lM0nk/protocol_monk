from dataclasses import dataclass, field
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


@dataclass
class AgentResponse:
    """Final output from the Thinking Loop."""

    content: str
    tool_calls: List["ToolRequest"]
    tokens: int


# --- 3. Tool Lifecycle ---


@dataclass
class ToolRequest:
    """Internal object representing a 'Need to run a tool'."""

    name: str
    parameters: Dict[str, Any]
    call_id: str
    requires_confirmation: bool = False


@dataclass
class ToolResult:
    """The outcome of an execution."""

    tool_name: str
    call_id: str
    success: bool
    output: Any
    duration: float
    error: Optional[str] = None


# --- 4. Context & Config ---


@dataclass
class Message:
    """Atomic conversation unit."""

    role: str
    content: str
    timestamp: float
    metadata: Dict[str, Any] = field(default_factory=dict)


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
from enum import Enum


class EventTypes(str, Enum):
    """
    Canonical Event Names from 01_EVENT_SPECIFICATION.md.
    Using an Enum prevents typo bugs (e.g., 'user_input' vs 'user_input_submitted').
    """

    # 1. System Events
    INFO = "info"
    STATUS_CHANGED = "status_changed"
    WARNING = "warning"
    ERROR = "error"

    # 2. Conversation Events (Downstream)
    STREAM_CHUNK = "stream_chunk"
    THINKING_STARTED = "thinking_started"
    THINKING_STOPPED = "thinking_stopped"
    RESPONSE_COMPLETE = "response_complete"

    # 3. Tool Execution Events
    TOOL_EXECUTION_START = "tool_execution_start"
    TOOL_CONFIRMATION_REQUESTED = "tool_confirmation_requested"
    TOOL_EXECUTION_PROGRESS = "tool_execution_progress"
    TOOL_RESULT = "tool_result"
    TOOL_EXECUTION_COMPLETE = "tool_execution_complete"

    # 4. Input Events (Upstream: UI -> Agent)
    USER_INPUT_SUBMITTED = "user_input_submitted"  # <--- EXACT MATCH
    USER_INPUT_CANCELLED = "user_input_cancelled"
    TOOL_CONFIRMATION_SUBMITTED = "tool_confirmation_submitted"
    SYSTEM_COMMAND_ISSUED = "system_command_issued"

    # 5. Command/Config Events
    COMMAND_RESULT = "command_result"
    MODEL_SWITCHED = "model_switched"
    PROVIDER_SWITCHED = "provider_switched"
    AUTO_CONFIRM_CHANGED = "auto_confirm_changed"

    # 6. Context Events
    CONTEXT_OVERFLOW = "context_overflow"
    TASK_COMPLETE = "task_complete"

    # 7. Setup & Discovery Events
    SETUP_REQUIRED = "setup_required"
    LOCAL_CONTEXT_PROMPT = "local_context_prompt"
    SETUP_COMPLETE = "setup_complete"
    MISSING_MODEL_DATA = "missing_model_data"
    DISCOVERY_COMPLETE = "discovery_complete"

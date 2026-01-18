from dataclasses import dataclass, field
from typing import Dict, Optional, Any


@dataclass
class Message:
    """
    A single atomic unit of conversation history.

    Attributes:
        role: "user", "assistant", or "system".
        content: The text content.
        timestamp: When this message was created.
        metadata: Optional technical data (file paths, tool IDs, token counts).
    """

    role: str
    content: str
    timestamp: float
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ContextStats:
    """
    Snapshot of the current context state.
    Used by the logic layer to decide if pruning is needed.
    """

    total_tokens: int
    message_count: int
    loaded_files_count: int

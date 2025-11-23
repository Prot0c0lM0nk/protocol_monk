import time
from dataclasses import dataclass, field

@dataclass
class Message:
    """
    Represents a single message in the conversation.

    Attributes:
        role: "user", "assistant", or "system"
        content: The message text
        timestamp: When message was created
        importance: Score 1-5, higher = more important to preserve
    """
    role: str
    content: str
    timestamp: float = field(default_factory=time.time)
    importance: int = 3  # Default medium importance
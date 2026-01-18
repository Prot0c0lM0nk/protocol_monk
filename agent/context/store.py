from typing import List, Optional
from .structs import Message


class ContextStore:
    """
    Passive container for conversation history.
    """

    def __init__(self):
        self._messages: List[Message] = []
        self._system_prompt: Optional[Message] = None

    def set_system_prompt(self, message: Message) -> None:
        """Sets the immutable system prompt."""
        self._system_prompt = message

    def add(self, message: Message) -> None:
        """Appends a message to the history."""
        self._messages.append(message)

    def replace_history(self, new_history: List[Message]) -> None:
        """
        Replaces entire history (used after pruning).
        Note: We extract the system prompt if it exists in the new history,
        or keep the existing one if not provided (depending on pruning logic).
        """
        self._messages = []
        for msg in new_history:
            if msg.role == "system":
                self._system_prompt = msg
            else:
                self._messages.append(msg)

    def get_full_history(self) -> List[Message]:
        """Returns the complete context for the LLM."""
        history = []
        if self._system_prompt:
            history.append(self._system_prompt)
        history.extend(self._messages)
        return history

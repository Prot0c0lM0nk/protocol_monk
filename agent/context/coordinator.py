import time
import uuid
from typing import List

from protocol_monk.config.settings import Settings
from protocol_monk.exceptions.context import ContextError
from .structs import Message, ContextStats
from .store import ContextStore
from .file_tracker import FileTracker
from . import logic


class ContextCoordinator:
    """
    High-level facade for context management.
    The AgentService talks ONLY to this, not to the Store or Logic directly.
    """

    def __init__(self, store: ContextStore, tracker: FileTracker, settings: Settings):
        self._store = store
        self._tracker = tracker
        self._settings = settings
        
        # Use computed values from settings
        self._limit = settings.context_window_limit
        self._pruning_target = settings.active_model_config['pruning_target']
        
        # Initialize token estimator with model family
        from protocol_monk.utils.token_estimation import SmartTokenEstimator
        self._token_estimator = SmartTokenEstimator(settings.model_family)
        
        # Set system prompt (already loaded by Pydantic)
        sys_msg = Message(
            role="system", 
            content=settings.system_prompt, 
            timestamp=time.time()
        )
        self._store.set_system_prompt(sys_msg)

    async def add_user_message(self, text: str) -> ContextStats:
        """
        Adds user input, calculates tokens, and auto-prunes if needed.
        """
        msg = Message(
            role="user",
            content=text,
            timestamp=time.time(),
            metadata={"id": str(uuid.uuid4())},
        )

        # 1. Add to store
        self._store.add(msg)

        # 2. Check and Prune
        self._ensure_limits()

        return self._get_stats()

    def _ensure_limits(self) -> None:
        """
        Private method to enforce context window limits.
        """
        history = self._store.get_full_history()

        # Calculate current load
        total_tokens = sum(logic.count_tokens(m.content) for m in history)

        stats = ContextStats(
            total_tokens=total_tokens,
            message_count=len(history),
            loaded_files_count=0,  # TODO: Hook up tracker count
        )

        if logic.should_prune(stats, self._limit):
            # Perform Pruning
            # We target 80% of limit to give breathing room
            target = int(self._limit * 0.8)
            new_history = logic.prune_messages(history, target)

            # Update Store
            self._store.replace_history(new_history)

            # Sync File Tracker (Garbage Collection)
            active_ids = {
                m.metadata.get("id") for m in new_history if m.metadata.get("id")
            }
            self._tracker.sync_with_history(active_ids)

    def _get_stats(self) -> ContextStats:
        history = self._store.get_full_history()
        return ContextStats(
            total_tokens=sum(logic.count_tokens(m.content) for m in history),
            message_count=len(history),
            loaded_files_count=0,
        )

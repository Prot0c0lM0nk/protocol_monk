import json
import time
import uuid
from typing import List, Optional, Dict, Any

from protocol_monk.config.settings import Settings
from protocol_monk.agent.structs import Message, ContextStats, ToolResult
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
        self._pruning_target = int(self._limit * settings.pruning_threshold)

        # Initialize token estimator with model family
        from protocol_monk.utils.token_estimation import SmartTokenEstimator

        self._token_estimator = SmartTokenEstimator(settings.model_family)

        # Set system prompt (already loaded by Pydantic)
        sys_msg = Message(
            role="system", content=settings.system_prompt, timestamp=time.time()
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
            # Use the pre-calculated pruning target (80% of limit by default)
            target = self._pruning_target
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

    async def reset(self) -> None:
        """
        Reset the context by clearing all messages except the system prompt.
        """
        # Clear all messages except system prompt
        self._store._messages.clear()

        # Reset file tracker
        self._tracker._loaded_files.clear()

        # Note: System prompt remains intact

    async def add_tool_result(self, result: ToolResult) -> ContextStats:
        """
        Add a tool execution result so the next model pass can consume it.
        """
        envelope = {
            "type": "tool_result",
            "tool_name": result.tool_name,
            "tool_call_id": result.call_id,
            "success": result.success,
            "duration_seconds": result.duration,
            "output_kind": result.output_kind,
            "error_code": result.error_code,
            "error": result.error,
            "error_details": result.error_details,
            "output": result.output,
        }
        content = json.dumps(envelope, ensure_ascii=False, default=str)

        msg = Message(
            role="tool",
            content=content,
            timestamp=time.time(),
            metadata={
                "tool_name": result.tool_name,
                "tool_call_id": result.call_id,
                "success": result.success,
                "duration": result.duration,
            },
        )
        self._store.add(msg)
        self._ensure_limits()
        return self._get_stats()

    async def add_assistant_pass(
        self,
        content: str,
        thinking: str = "",
        pass_id: str = "",
        tokens: int = 0,
        tool_call_count: int = 0,
        tool_calls: Optional[List[Dict[str, Any]]] = None,
    ) -> ContextStats:
        """
        Persist each assistant pass in-order so follow-up model calls keep continuity.
        """
        content = content or ""
        thinking = thinking or ""

        if content and thinking:
            combined = f"{content}\n\n[reasoning]\n{thinking}"
        elif content:
            combined = content
        elif thinking:
            combined = f"[reasoning]\n{thinking}"
        else:
            combined = ""

        msg = Message(
            role="assistant",
            content=combined,
            timestamp=time.time(),
            metadata={
                "id": str(uuid.uuid4()),
                "pass_id": pass_id,
                "tokens": tokens,
                "tool_call_count": tool_call_count,
                "content_length": len(content),
                "thinking_length": len(thinking),
                "tool_calls": tool_calls or [],
            },
        )
        self._store.add(msg)
        self._ensure_limits()
        return self._get_stats()


class ContextStore:
    """
    Passive container for conversation history.

    THREAD SAFETY:
    - This class is NOT thread-safe by design
    - It's only accessed from async code (no true parallelism)
    - All mutations happen atomically (no await points between operations)
    - Therefore: No race condition in current architecture

    FUTURE CONSIDERATION:
    - If threading is added, this WILL need synchronization
    - If await points are added between mutations, this WILL need locking
    """

    def __init__(self):
        self._messages: List[Message] = []
        self._system_prompt: Optional[Message] = None

    def replace_history(self, new_history: List[Message]) -> None:
        """
        Replaces entire history (used after pruning).

        SAFETY: This runs atomically in async code:
        - No await points between clear and rebuild
        - No other coroutine can interleave
        - GIL ensures atomic list operations
        """
        self._messages = []  # ← Atomic
        for msg in new_history:
            if msg.role == "system":
                self._system_prompt = msg
            else:
                self._messages.append(msg)  # ← Atomic

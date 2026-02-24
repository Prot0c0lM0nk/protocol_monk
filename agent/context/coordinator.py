import json
import logging
import time
import uuid
from pathlib import Path
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

    FILE_READ_TOOL = "read_file"
    FILE_MUTATION_TOOLS = {
        "create_file",
        "append_to_file",
        "replace_lines",
        "delete_lines",
        "insert_in_file",
    }

    def __init__(self, store: ContextStore, tracker: FileTracker, settings: Settings):
        self._store = store
        self._tracker = tracker
        self._settings = settings
        self._logger = logging.getLogger("ContextCoordinator")

        # Use computed values from settings
        self._limit = settings.context_window_limit
        self._pruning_target = max(1, int(self._limit * settings.pruning_threshold))

        # Initialize token estimator with model family
        from protocol_monk.utils.token_estimation import SmartTokenEstimator

        self._token_estimator = SmartTokenEstimator(settings.model_family)

        # Set system prompt (already loaded by Pydantic)
        sys_msg = Message(
            role="system", content=settings.system_prompt, timestamp=time.time()
        )
        self._store.set_system_prompt(sys_msg)

    def _estimate_tokens(self, text: str) -> int:
        try:
            return self._token_estimator.estimate_tokens(text or "")
        except Exception:
            return logic.count_tokens(text)

    def _count_history_tokens(self, history: List[Message]) -> int:
        return sum(self._estimate_tokens(m.content) for m in history)

    def _normalize_workspace_path(self, filepath: str) -> str:
        workspace_root = Path(self._settings.workspace_root)
        target = Path(filepath.strip())
        if not target.is_absolute():
            target = workspace_root / target
        try:
            return str(target.resolve(strict=False))
        except Exception:
            return str(target)

    def _record_file_tracking(self, result: ToolResult, message_id: str) -> None:
        if not result.success:
            return

        request_parameters = result.request_parameters or {}
        raw_path = request_parameters.get("filepath")
        if not isinstance(raw_path, str) or not raw_path.strip():
            return

        file_path = self._normalize_workspace_path(raw_path)
        if result.tool_name == self.FILE_READ_TOOL:
            self._tracker.mark_loaded(file_path, message_id)
            return

        if result.tool_name in self.FILE_MUTATION_TOOLS:
            self._tracker.remove_file(file_path)

    def _tool_result_context_limit(self) -> int:
        raw_limit = getattr(self._settings, "tool_result_context_max_chars", 4000)
        try:
            limit = int(raw_limit)
        except (TypeError, ValueError):
            limit = 4000
        return max(256, limit)

    def _compact_tool_output_for_context(self, output: Any) -> tuple[Any, int, bool]:
        if output is None:
            return None, 0, False

        limit = self._tool_result_context_limit()

        if isinstance(output, str):
            total_chars = len(output)
            if total_chars <= limit:
                return output, total_chars, False
            clipped = output[:limit]
            return (
                f"{clipped}... [truncated {total_chars - limit} chars for context replay]",
                total_chars,
                True,
            )

        serialized = json.dumps(output, ensure_ascii=False, default=str)
        total_chars = len(serialized)
        if total_chars <= limit:
            return output, total_chars, False

        clipped = serialized[:limit]
        return (
            f"{clipped}... [truncated {total_chars - limit} chars for context replay]",
            total_chars,
            True,
        )

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
        total_tokens = self._count_history_tokens(history)

        stats = ContextStats(
            total_tokens=total_tokens,
            message_count=len(history),
            loaded_files_count=self._tracker.count(),
        )

        if self._limit > 0 and logic.should_prune(stats, self._limit):
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
            pruned_total_tokens = self._count_history_tokens(new_history)
            self._logger.info(
                "Pruned context window: tokens %s -> %s, messages %s -> %s, loaded_files=%s",
                total_tokens,
                pruned_total_tokens,
                len(history),
                len(new_history),
                self._tracker.count(),
            )

    def _get_stats(self) -> ContextStats:
        history = self._store.get_full_history()
        return ContextStats(
            total_tokens=self._count_history_tokens(history),
            message_count=len(history),
            loaded_files_count=self._tracker.count(),
        )

    def get_stats(self) -> ContextStats:
        return self._get_stats()

    async def reset(self) -> None:
        """
        Reset the context by clearing all messages except the system prompt.
        """
        self._store.clear_messages()

        # Reset file tracker
        self._tracker.clear()

        # Note: System prompt remains intact

    async def add_tool_result(self, result: ToolResult) -> ContextStats:
        """
        Add a tool execution result so the next model pass can consume it.
        """
        context_output, output_chars, output_truncated = self._compact_tool_output_for_context(
            result.output
        )
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
            "output": context_output,
            "output_chars": output_chars,
            "output_truncated": output_truncated,
            "request_parameters": result.request_parameters,
        }
        content = json.dumps(envelope, ensure_ascii=False, default=str)
        message_id = str(uuid.uuid4())

        msg = Message(
            role="tool",
            content=content,
            timestamp=time.time(),
            metadata={
                "id": message_id,
                "tool_name": result.tool_name,
                "tool_call_id": result.call_id,
                "success": result.success,
                "duration": result.duration,
                "output_chars": output_chars,
                "output_truncated": output_truncated,
                "request_parameters": result.request_parameters or {},
            },
        )
        self._store.add(msg)
        self._record_file_tracking(result, message_id)
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

        msg = Message(
            role="assistant",
            content=content,
            timestamp=time.time(),
            metadata={
                "id": str(uuid.uuid4()),
                "pass_id": pass_id,
                "tokens": tokens,
                "tool_call_count": tool_call_count,
                "content_length": len(content),
                "thinking": thinking,
                "thinking_length": len(thinking),
                "tool_calls": tool_calls or [],
            },
        )
        self._store.add(msg)
        self._ensure_limits()
        return self._get_stats()

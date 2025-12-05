#!/usr/bin/env python3
"""
Context Manager
===============
Manages conversation history, token budgeting, and file content tracking.
Acts as the central memory hub for the ProtocolAgent.
"""

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional

from exceptions import ContextValidationError, NeuralSymIntegrationError
from exceptions import ConfigurationError
from config.static import settings

from .file_tracker import FileTracker

# Component imports
from .message import Message

# NeuralSym integration
from .neural_sym_integration import NEURALSYM_AVAILABLE, NeuralSymContextManager
from .pruner import ContextPruner
from .token_accountant import TokenAccountant

if TYPE_CHECKING:
    from tools.registry import ToolRegistry


# pylint: disable=too-many-instance-attributes
class ContextManager:
    """
    Manages conversation history and coordinates token budgeting.
    Acts as the central hub for the ProtocolAgent's memory.
    """

    def __init__(
        self,
        max_tokens: int = 16384,
        working_dir: Optional[Path] = None,
        tokenizer=None,
        tool_registry: Optional["ToolRegistry"] = None,
    ):
        self.logger = logging.getLogger(__name__)
        self.tool_registry = tool_registry
        self.conversation: List[Message] = []
        self._lock = asyncio.Lock()
        self.system_message = (
            "[System prompt not yet initialized. Call async_initialize()]"
        )

        # Instantiate components
        self.accountant = TokenAccountant(max_tokens=max_tokens, tokenizer=tokenizer)
        self.tracker = FileTracker(working_dir=working_dir or Path.cwd())
        self.pruner = ContextPruner(max_tokens=max_tokens)

        # Initialize NeuralSym integration if available
        if NEURALSYM_AVAILABLE:
            self.neural_sym = NeuralSymContextManager(
                working_dir=working_dir or Path.cwd()
            )
        else:
            self.neural_sym = None

    async def async_initialize(self):
        """Initialize async components and load the system prompt from disk.

        Raises:
            ContextValidationError: If system message fails to initialize properly
        """
        self.system_message = await self._build_system_message()
        # Validate that system message was successfully built
        if not self.system_message or "[ERROR]" in self.system_message:
            raise ContextValidationError(
                "System message failed to initialize properly",
                validation_type="system_message_initialization",
                invalid_value=self.system_message,
            )
        self.accountant.recalculate(self.system_message, self.conversation)

    async def _build_system_message(self) -> str:
        """
        Reads the system prompt template and injects tool definitions.

        Returns:
            str: Built system message with tool definitions

        Raises:
            ConfigurationError: If system prompt template file is not found
            ContextValidationError: If system prompt building fails
        """
        try:
            # Run file I/O in a separate thread to avoid blocking
            prompt_template = await asyncio.to_thread(
                settings.filesystem.system_prompt_file.read_text, encoding="utf-8"
            )

            if self.tool_registry and hasattr(
                self.tool_registry, "get_formatted_tool_schemas"
            ):
                tool_definitions = await self.tool_registry.get_formatted_tool_schemas()
            else:
                tool_definitions = (
                    "[ERROR: Tool registry not available. Tools will not work.]"
                )

            return prompt_template.replace(
                "{{AVAILABLE_TOOLS_SECTION}}", tool_definitions
            )

        except FileNotFoundError:
            error_msg = (
                f"System prompt template not found at: "
                f"{settings.filesystem.system_prompt_file}."
            )
            self.logger.critical(error_msg, exc_info=True)
            raise ConfigurationError(message=error_msg) from None
        except Exception as e:
            error_msg = f"Failed to build system prompt: {e}"
            self.logger.error(error_msg, exc_info=True)
            raise ContextValidationError(
                error_msg, validation_type="system_message", invalid_value=None
            ) from e

    async def _check_and_update_files(self, content: str):
        """
        Check if content is a file path and update tracker if valid.

        Args:
            content: Content string to check for file path

        Returns:
            None: Updates file tracker if valid file path found

        Raises:
            Exception: Various exceptions from file operations (caught internally)
        """
        # Quick heuristic check before expensive operations
        if len(content) >= 256 or "\n" in content:
            return

        try:
            possible_file = self.tracker.working_dir / content
            if possible_file.exists() and possible_file.is_file():
                await self.tracker.replace_old_file_content(
                    str(possible_file), self.conversation
                )
        except Exception as e:  # pylint: disable=broad-exception-caught
            # Validate file path and raise proper exception if it looks like a path
            if (
                not content
                or content.startswith(".")
                or "/" in content
                or "\\" in content
            ):
                raise ContextValidationError(
                    f"Invalid file path in content: {content}",
                    validation_type="file_path",
                    invalid_value=content,
                ) from e

    async def add_message(
        self, role: str, content: str, importance: Optional[int] = None
    ):
        """
        Add a message to the conversation.
        Handles token counting, pruning, and file content management automatically.

        Args:
            role: Message role (user, assistant, system)
            content: Message content
            importance: Message importance level (optional)
        """
        async with self._lock:
            # Log meaningful information about what's being added
            content_preview = content[:50] + "..." if len(content) > 50 else content
            self.logger.debug("Adding %s message: %s", role, content_preview)

            # 1. Estimate tokens
            new_tokens = self.accountant.estimate(content)

            # 2. Prune if budget exceeded
            if not self.accountant.check_budget(new_tokens):
                self.logger.info("Context approaching limit, pruning...")
                self.conversation = self.pruner.prune(
                    self.conversation, self.accountant
                )
                self.accountant.recalculate(self.system_message, self.conversation)

            # 3. Check for file updates
            await self._check_and_update_files(content)

            # 4. Add the new message
            if importance is None:
                importance = 5 if role == "tool" else 3

            msg = Message(role=role, content=content, importance=importance)
            self.conversation.append(msg)

            # 5. Update token count
            self.accountant.add(new_tokens)

    async def add_user_message(self, content: str, importance: int = 4):
        """
        Add a message from the user.

        Args:
            content: User message content
            importance: Message importance level (default: 4)
        """
        await self.add_message("user", content, importance)

    async def add_assistant_message(self, content: str, importance: int = 3):
        """
        Add a message from the assistant (AI).

        Args:
            content: Assistant message content
            importance: Message importance level (default: 3)
        """
        await self.add_message("assistant", content, importance)

    async def get_context(self, model_name: str = None) -> List[Dict]:
        """
        Formats the conversation for the LLM API.
        Automatically applies NeuralSym enhancement if the model is small/weak.

        Args:
            model_name: Name of the model to format context for (optional)

        Returns:
            List[Dict]: Formatted conversation context for API

        Raises:
            NeuralSymIntegrationError: If NeuralSym enhancement fails for the model
        """
        # 1. Check context size before proceeding
        if model_name:
            await self.check_context_before_generation(model_name)

        # 2. Get the base context (System + History)
        base_context = await self._get_base_context()

        # 3. Check if we need to enhance it (Small Model Logic)
        if model_name and self.neural_sym:
            # Check if model is small (contains size indicators)
            small_identifiers = [
                "8b",
                "4b",
                "2b",
                "1.7b",
                "0.6b",
                "small",
                "mini",
                "tiny",
            ]
            is_small_model = any(x in model_name.lower() for x in small_identifiers)

            if is_small_model:
                try:
                    return await self.neural_sym.get_enhanced_context(
                        base_context, model_name
                    )
                except Exception as e:
                    raise NeuralSymIntegrationError(
                        f"NeuralSym enhancement failed for model {model_name}",
                        operation="get_enhanced_context",
                        model_name=model_name,
                        original_error=e,
                    ) from e
        return base_context

    async def _get_base_context(self) -> List[Dict]:
        """
        Standard context construction without AI enhancement.

        Returns:
            List[Dict]: Basic conversation context without enhancements
        """
        async with self._lock:
            context = [{"role": "system", "content": self.system_message}]
            for msg in self.conversation:
                context.append({"role": msg.role, "content": msg.content})
            return context

    async def clear(self):
        """
        Resets the entire context state.

            None: Clears conversation and resets trackers
        """
        async with self._lock:
            self.conversation = []
            await self.tracker.clear()
            self.accountant.recalculate(self.system_message, self.conversation)

    @property
    def max_tokens(self) -> int:
        """
        Return the maximum token limit.

        Returns:
            int: Maximum allowed tokens in context
        """
        return self.accountant.max_tokens

    def get_total_tokens(self) -> int:
        """
        Get the current total token count.

        Returns:
            int: Current total tokens in context
        """
        return self.accountant.total_tokens

    async def get_stats(self) -> Dict:
        """
        Returns current usage statistics.

        Returns:
            Dict: Statistics including tokens, messages, and files tracked
        """
        async with self._lock:
            stats = self.accountant.get_stats()
            stats["total_messages"] = len(self.conversation)
            stats["files_tracked"] = len(self.tracker.files_shown)
            return stats

    def prune_context(self, strategy: str, _target_limit: int):
        """
        Prune context based on strategy and target limit.

        Args:
            strategy: Pruning strategy to use
            _target_limit: Target token limit for pruning

            None: Modifies conversation context in-place
        """
        if strategy in ["strict", "archive"]:
            self.conversation = self.pruner.prune(self.conversation, self.accountant)
        elif strategy == "smart":
            if len(self.conversation) > 2:
                self.conversation = self.conversation[-2:]

        self.accountant.recalculate(self.system_message, self.conversation)

    # --- Neural Sym Passthrough Methods ---

    def record_tool_execution_outcome(self, *args, **kwargs):
        """
        Forward tool execution results to NeuralSym for learning.

        Args:
            *args: Variable arguments to pass to NeuralSym
            **kwargs: Keyword arguments to pass to NeuralSym

        Raises:
            NeuralSymIntegrationError: If NeuralSym recording fails
        """
        if self.neural_sym:
            try:
                self.neural_sym.record_interaction_outcome(*args, **kwargs)
            except Exception as e:
                raise NeuralSymIntegrationError(
                    "NeuralSym recording failed",
                    operation="record_interaction_outcome",
                    original_error=e,
                ) from e

    def _check_context_size_for_model(self, model_name: str) -> dict:
        """
        Check if current context size is appropriate for the given model.

        Args:
            model_name: Name of the model to check against

        Returns:
            dict: Status and information about context size compatibility
        """
        from agent.model_manager import RuntimeModelManager

        # Get current context stats
        stats = self.accountant.get_stats()
        current_tokens = stats["total_tokens"]

        # Get model's context window
        model_manager = RuntimeModelManager()
        model_info = model_manager.get_available_models().get(model_name)
        if not model_info:
            # If model not found, use a safe default
            model_context_window = 32768  # Conservative default
        else:
            model_context_window = model_info.context_window

        # Define thresholds
        warning_threshold = int(model_context_window * 0.8)  # 80%
        critical_threshold = int(model_context_window * 0.95)  # 95%
        hard_limit = model_context_window  # 100%

        result = {
            "current_tokens": current_tokens,
            "model_context_window": model_context_window,
            "warning_threshold": warning_threshold,
            "critical_threshold": critical_threshold,
            "hard_limit": hard_limit,
            "is_warning": current_tokens > warning_threshold,
            "is_critical": current_tokens > critical_threshold,
            "is_over_limit": current_tokens > hard_limit,
            "usage_percent": (
                round((current_tokens / model_context_window) * 100, 2)
                if model_context_window > 0
                else 0
            ),
        }

        return result

    def _get_context_size_advice(self, check_result: dict) -> str:
        """
        Generate user-friendly advice based on context size check.

        Args:
            check_result: Dictionary with context size analysis results

        Returns:
            str: User-friendly advice message
        """
        if check_result["is_over_limit"]:
            return f"🚨 CRITICAL: Context ({check_result['current_tokens']:,} tokens) exceeds model limit ({check_result['hard_limit']:,} tokens). Please clear context with '/clear'."
        elif check_result["is_critical"]:
            return f"⚠️  WARNING: Context ({check_result['current_tokens']:,} tokens) is critically large ({check_result['usage_percent']}% of limit). Consider clearing with '/clear'."
        elif check_result["is_warning"]:
            return f"⚠️  NOTICE: Context ({check_result['current_tokens']:,} tokens) is large ({check_result['usage_percent']}% of limit). Consider clearing with '/clear'."
        else:
            return f"✅ Context ({check_result['current_tokens']:,} tokens) is within limits ({check_result['usage_percent']}% of {check_result['model_context_window']:,} token limit)."

    async def check_context_before_generation(self, model_name: str) -> dict:
        """
        Check context size before generation and return status.
        Raises an exception if context exceeds hard limits.

        Args:
            model_name: Name of the model to check context against

        Returns:
            dict: Context size analysis and status information

        Raises:
            ContextValidationError: If context exceeds hard limits
        """
        check_result = self._check_context_size_for_model(model_name)

        # Log the status
        advice = self._get_context_size_advice(check_result)
        self.logger.info(advice)

        # Raise exception if over hard limit
        if check_result["is_over_limit"]:
            raise ContextValidationError(
                f"Context size ({check_result['current_tokens']:,} tokens) exceeds model limit ({check_result['hard_limit']:,} tokens)",
                validation_type="context_size",
                invalid_value=check_result["current_tokens"],
            )

        return check_result

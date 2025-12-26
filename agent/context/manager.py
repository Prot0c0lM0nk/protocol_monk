#!/usr/bin/env python3
"""
Context Manager
===============
Manages conversation history, token budgeting, and file content tracking.
Acts as the central memory hub for the ProtocolAgent.
"""

import asyncio
import re
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional

from exceptions import ConfigurationError, ContextValidationError
from config.static import settings

from .file_tracker import FileTracker

# Component imports
from .message import Message


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

        # Add validation optimization to break circular dependency
        self._recent_validation_attempts: set[str] = set()
        self._successful_file_paths: set[str] = set()
        self._validation_cache_ttl = 60  # Cache TTL in seconds
        self._last_validation_cleanup = 0

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
        Uses atomic operations to eliminate TOCTOU race conditions.

        OPTIMIZED: Now with deduplication and success-only context updates
        to break circular dependency with PathValidator.

        Args:
            content: Content string to check for file path

        Returns:
            None: Updates file tracker only if valid file path found and operation succeeds

        Raises:
            Exception: Various exceptions from file operations (caught internally)
        """
        # Use new validation method to check if content is likely a file path
        if not self._is_likely_file_path(content):
            return

        # Deduplication: Skip if we recently processed this path
        if self._should_skip_validation_attempt(content):
            self.logger.debug("Skipping duplicate validation attempt for: %s", content)
            return

        # Track this validation attempt
        self._track_validation_attempt(content)

        # Clean up old validation attempts periodically
        self._cleanup_validation_cache()

        try:
            possible_file = self.tracker.working_dir / content

            # ATOMIC VALIDATION: Try to open the file instead of checking existence
            # This eliminates the TOCTOU race condition between exists() and is_file()
            with possible_file.open("r") as f:
                # SUCCESS: Only update context for successful operations
                await self.tracker.replace_old_file_content(
                    str(possible_file), self.conversation
                )
                # Track successful file path for optimization
                self._track_successful_file_path(content)
                self.logger.debug("Successfully updated context for file: %s", content)

        except (FileNotFoundError, IsADirectoryError, PermissionError):
            # File doesn't exist, is a directory, or we can't access it
            # These are expected exceptions for invalid paths - silently ignore
            # IMPORTANT: Do NOT update context for failed validations
            self.logger.debug(
                "File validation failed for: %s (no context update)", content
            )
            pass

        except Exception as e:
            # Log unexpected errors before deciding whether to raise
            self.logger.warning(
                "Unexpected error while checking file path '%s': %s",
                content,
                str(e),
                exc_info=True,
            )
            # Only raise if content looks like a deliberate path attempt
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

            # 1. Estimate tokens using temporary accountant to break circular dependency
            temp_accountant = TokenAccountant(max_tokens=self.accountant.max_tokens)
            new_tokens = temp_accountant.estimate(content)

            # 2. Prune if budget exceeded using temporary accountant for decision
            if not temp_accountant.check_budget(new_tokens):
                self.logger.info("Context approaching limit, pruning...")
                self.conversation = self.pruner.prune(
                    self.conversation, temp_accountant
                )
                # Recalculate with main accountant after pruning
                self.accountant.recalculate(self.system_message, self.conversation)

            # 3. Check for file updates
            await self._check_and_update_files(content)

            # 4. Add the new message
            if importance is None:
                importance = 5 if role == "tool" else 3

            msg = Message(role=role, content=content, importance=importance)
            self.conversation.append(msg)

            # 5. Update token count with main accountant
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

    async def get_context(self, model_name: str = None, provider: str = "ollama") -> List[Dict]:
        """
        Formats the conversation for the LLM API.

        Args:
            model_name: Name of the model to format context for (optional)
            provider: Provider name ('ollama' or 'openrouter')

        Returns:
            List[Dict]: Formatted conversation context for API
        """
        async with self._lock:
            # 1. Check context size within lock to prevent race conditions
            if model_name:
                await self.check_context_before_generation(model_name, provider)

            # 2. Get the base context (System + History)
            base_context = await self._get_base_context()

            # 3. Return the base context directly
            return base_context

    async def _get_base_context(self) -> List[Dict]:
        """
        Standard context construction without AI enhancement.
        
        Converts tool messages to user role format for compatibility with models
        that don't support the 'tool' role (like many Ollama models).
        
        NEW: Detects when tool results appear without preceding assistant tool calls
        and adds implicit assistant intent to maintain conversation flow without
        contaminating training data with fake messages.
        
        NOTE: This method should ONLY be called from within an existing lock context
        to avoid deadlocks.
        
        IMPORTANT: Tool results are formatted with explicit "RESULT - COMPLETED" markers
        to prevent models from confusing tool results with new tool requests.
        """
        # DO NOT acquire lock here - caller must already hold the lock
        context = [{"role": "system", "content": self.system_message}]
        
        # Track if we need to add implicit assistant intent before tool results
        last_role_was_tool = False
        
        for i, msg in enumerate(self.conversation):
            # Convert tool messages to user role for model compatibility
            if msg.role == "tool":
                # Check if this is the first tool message after a user message
                # (indicating assistant made tool calls that weren't recorded)
                if not last_role_was_tool and i > 0 and self.conversation[i-1].role == "user":
                    # 1. Extract the tool name safely outside the f-string
                    if 'Tool: ' in msg.content:
                        # Split by newline first to avoid the backslash issue entirely
                        tool_name = msg.content.split('Tool: ')[1].split('\n')[0]
                    else:
                        tool_name = 'available'
    
                    # 2. Use the simple variable inside the f-string
                    implicit_intent = f"I will use the {tool_name} tool to help with your request."
                    context.append({"role": "assistant", "content": implicit_intent})
                
                # Extract tool name from content if available (format: "Tool: name\nOutput: ...")
                tool_name = "Unknown"
                content_lines = msg.content.split('\n')
                for line in content_lines:
                    if line.startswith("Tool: "):
                        tool_name = line.replace("Tool: ", "").strip()
                        break
                
                # Format with explicit completion markers and visual boxing
                formatted_result = (
                    "╔══════════════════════════════════════════════════════════════╗\n"
                    "║  TOOL EXECUTION RESULT - COMPLETED                              ║\n"
                    "╚══════════════════════════════════════════════════════════════╝\n\n"
                    f"Tool Name: {tool_name}\n"
                    "Execution Status: COMPLETED\n\n"
                    "Output:\n"
                    f"{msg.content}\n\n"
                    "╚══════════════════════════════════════════════════════════════╝"
                )
                context.append({"role": "user", "content": formatted_result})
                last_role_was_tool = True
            else:
                context.append({"role": msg.role, "content": msg.content})
                last_role_was_tool = False
                
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

    def _check_context_size_for_model(self, model_name: str, provider: str = "ollama") -> dict:
        """
        Check if current context size is appropriate for the given model.

        Args:
            model_name: Name of the model to check against
            provider: Provider name ('ollama' or 'openrouter')

        Returns:
            dict: Status and information about context size compatibility
        """
        from agent.model_manager import RuntimeModelManager

        # Get current context stats
        stats = self.accountant.get_stats()
        current_tokens = stats["total_tokens"]

        # Get model's context window using CORRECT provider
        model_manager = RuntimeModelManager(provider=provider)
        model_info = model_manager.get_available_models().get(model_name)
        
        if not model_info:
            # If model not found, use a safe default
            self.logger.warning(
                f"Model '{model_name}' not found in {provider} model map. Using default context window."
            )
            model_context_window = 32768  # Conservative default
        else:
            model_context_window = model_info.context_window

        # Define thresholds
        warning_threshold = int(model_context_window * 0.8)
        critical_threshold = int(model_context_window * 0.95)
        hard_limit = model_context_window

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

    async def check_context_before_generation(self, model_name: str, provider: str = "ollama") -> dict:
        """
        Check context size before generation and return status.
        Raises an exception if context exceeds hard limits.

        Args:
            model_name: Name of the model to check against
            provider: Provider name ('ollama' or 'openrouter')

        Returns:
            dict: Context size analysis and status information
        """
        check_result = self._check_context_size_for_model(model_name, provider)

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

    def _is_likely_file_path(self, content: str) -> bool:
        """
        NEW validation method to reliably distinguish file paths from regular text content.

        Args:
            content: Content string to validate

        Returns:
            bool: True if content is likely a file path, False otherwise
        """
        # Quick heuristic checks
        if not content or len(content) >= 256 or "\n" in content:
            return False

        # Check for common file path patterns
        # Look for file extensions
        common_extensions = {
            ".py",
            ".txt",
            ".md",
            ".json",
            ".yaml",
            ".yml",
            ".xml",
            ".csv",
            ".js",
            ".html",
            ".css",
            ".sh",
            ".bash",
            ".zsh",
            ".cfg",
            ".conf",
            ".ini",
            ".log",
            ".sql",
            ".gitignore",
            ".dockerignore",
        }

        # Check if content has a file extension
        if "." in content and any(content.endswith(ext) for ext in common_extensions):
            return True

        # Check for path separators
        if "/" in content or "\\" in content:
            return True

        # Check if content looks like a relative path
        if content.startswith("./") or content.startswith("../"):
            return True

        # Check if content looks like an absolute path
        if content.startswith("/") or (len(content) > 1 and content[1] == ":"):
            return True

        return False

    def _detect_context_poisoning(self, context: List[Dict]) -> bool:
        """
        NEW monitoring method to detect signs of corrupted context.

        Args:
            context: List of context messages to check

        Returns:
            bool: True if context poisoning is detected, False otherwise
        """
        # Check for repeated error messages
        error_count = 0
        for msg in context:
            content = msg.get("content", "")
            if "error" in content.lower() or "exception" in content.lower():
                error_count += 1
                # If more than 30% of messages contain errors, flag as poisoned
                if error_count / len(context) > 0.3:
                    return True

        # Check for excessive repetition of identical messages
        content_hashes = {}
        for msg in context:
            content = msg.get("content", "")
            content_hash = hash(content)
            content_hashes[content_hash] = content_hashes.get(content_hash, 0) + 1
            # If any message appears more than 3 times, flag as poisoned
            if content_hashes[content_hash] > 3:
                return True

        return False

    def _should_skip_validation_attempt(self, content: str) -> bool:
        """
        Check if we should skip this validation attempt due to recent processing.

        Args:
            content: File path content to check

        Returns:
            bool: True if we should skip this validation attempt
        """
        import time

        # Clean up old attempts if TTL has expired
        current_time = time.time()
        if current_time - self._last_validation_cleanup > self._validation_cache_ttl:
            self._cleanup_validation_cache()

        # Skip if this path was recently processed
        return content in self._recent_validation_attempts

    def _track_validation_attempt(self, content: str) -> None:
        """
        Track a validation attempt to prevent duplicate processing.

        Args:
            content: File path content that was attempted
        """
        import time

        self._recent_validation_attempts.add(content)
        self._last_validation_cleanup = time.time()

    def _track_successful_file_path(self, content: str) -> None:
        """
        Track a successfully validated file path for optimization.

        Args:
            content: File path content that was successfully processed
        """
        self._successful_file_paths.add(content)

    def _cleanup_validation_cache(self) -> None:
        """
        Clean up old validation attempts from the cache.
        Keeps the cache size manageable and prevents memory growth.
        """
        import time

        # Simple cleanup - clear all recent attempts
        # In a production system, you might want more sophisticated TTL logic
        self._recent_validation_attempts.clear()
        self._last_validation_cleanup = time.time()

        # Also limit successful paths cache size
        if len(self._successful_file_paths) > 1000:
            # Keep only the most recent 500 successful paths
            # Convert to list, take last 500, convert back to set
            recent_successes = list(self._successful_file_paths)[-500:]
            self._successful_file_paths = set(recent_successes)

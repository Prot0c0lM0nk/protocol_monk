import logging
from typing import Any, List, Optional

from agent.context.exceptions_expanded import (
    ContextValidationError,
    TokenEstimationError,
)
from agent.context.message import Message
from agent.core_exceptions import ConfigurationError

# Import the official estimator from utils
from utils.token_estimation import SmartTokenEstimator


class TokenAccountant:
    """
    Manages token counting and budget for the context.

    ARCHITECTURAL STRICTNESS:
    - Delegates ALL estimation logic to SmartTokenEstimator.
    - NO fallback math (e.g., len/4) allowed.
    - If estimation fails, it is an error, not a guess.
    """

    def __init__(self, max_tokens: int, tokenizer: Optional[Any] = None):
        # Validate max_tokens to prevent infinite budget case
        if max_tokens <= 0:
            raise ContextValidationError(
                f"Invalid max_tokens value: {max_tokens}. Must be positive.",
                validation_type="max_tokens",
                invalid_value=max_tokens,
            )
        self.max_tokens = max_tokens
        self.total_tokens = 0
        self.logger = logging.getLogger(__name__)

        # Initialize the Estimator
        # We default to 'qwen' family as the safe baseline for our specific use case
        try:
            self.estimator = SmartTokenEstimator(model_family="qwen")
        except Exception as e:
            raise ConfigurationError(
                message=f"CRITICAL: Failed to initialize SmartTokenEstimator: {e}",
                root_cause=e,
            )

    def estimate(self, text: str) -> int:
        """
        Estimate tokens for a single string using the strictly defined estimator.

        Args:
            text: Text string to estimate tokens for

        Returns:
            int: Estimated token count for the text

        Raises:
            TokenEstimationError: If token estimation fails
        """
        if not text:
            return 0

        try:
            return self.estimator.estimate_tokens(text)
        except Exception as e:
            # DO NOT fallback to character math.
            # We want to know if our estimator is broken.
            self.logger.error(
                f"CRITICAL: Token estimation failed for text snippet: {e}",
                exc_info=True,
            )
            raise TokenEstimationError(
                f"Token estimation failed for text: {e}",
                estimator_name=getattr(self.estimator, "__class__.__name__", "Unknown"),
                failed_text=text[:100] if text else "",
                original_error=e,
            ) from e

    def add(self, tokens: int):
        """
        Add tokens to the total count.

        Args:
            tokens: Number of tokens to add to total

        Raises:
            ContextValidationError: If max_tokens is invalid
        """
        if self.max_tokens <= 0:
            raise ContextValidationError(
                f"Invalid max_tokens value: {self.max_tokens}. Must be positive.",
                validation_type="max_tokens",
                invalid_value=self.max_tokens,
            )
        self.total_tokens += tokens
        self.logger.debug(f"Added {tokens} tokens. Total: {self.total_tokens}")

    def check_budget(self, new_tokens: int) -> bool:
        """
        Check if adding new_tokens would exceed the 90% pruning threshold.
        Returns True if budget is OK, False if pruning is needed.

        Args:
            new_tokens: Number of tokens to check against budget

        Returns:
            bool: True if within budget, False if pruning needed
        """
        if self.max_tokens <= 0:
            return True  # Infinite budget or unconfigured

        pruning_threshold = int(self.max_tokens * 0.9)  # Trigger at 90% instead of 80%
        return (self.total_tokens + new_tokens) <= pruning_threshold

    def recalculate(self, system_message: str, messages: List[Message]):
        """
        Recalculate the total token count from scratch.
        This is the source of truth for the context state.

        Args:
            system_message: System message to include in calculation
            messages: List of conversation messages to include
        """
        running_total = 0

        # 1. System Prompt
        running_total += self.estimate(system_message)

        # 2. Conversation History
        for msg in messages:
            running_total += self.estimate(msg.content)

        self.total_tokens = running_total
        self.logger.debug(f"Recalculated total tokens: {self.total_tokens}")

    def get_stats(self) -> dict:
        """
        Get current token statistics.

        Returns:
            dict: Token usage statistics including total, max, and percentage
        """
        usage_percent = (
            (self.total_tokens / self.max_tokens) * 100 if self.max_tokens > 0 else 0
        )
        return {
            "total_tokens": self.total_tokens,
            "max_tokens": self.max_tokens,
            "usage_percent": round(usage_percent, 2),
        }

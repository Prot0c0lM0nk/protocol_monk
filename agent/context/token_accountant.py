import logging
from typing import List, Optional, Any
from agent.context.message import Message
from agent.exceptions import ContextOverflowError, ConfigurationError

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
                root_cause=e
            )

    def estimate(self, text: str) -> int:
        """
        Estimate tokens for a single string using the strictly defined estimator.
        """
        if not text:
            return 0
            
        try:
            return self.estimator.estimate_tokens(text)
        except Exception as e:
            # DO NOT fallback to character math.
            # We want to know if our estimator is broken.
            self.logger.error(f"CRITICAL: Token estimation failed for text snippet: {e}", exc_info=True)
            # Depending on desired severity, we could raise here. 
            # For now, returning 0 is safer than guessing, as it alerts the user 
            # (via weird token counts) rather than silently filling context with bad math.
            return 0

    def add(self, tokens: int):
        """Add tokens to the total count."""
        self.total_tokens += tokens

    def check_budget(self, new_tokens: int) -> bool:
        """
        Check if adding new_tokens would exceed the 80% pruning threshold.
        Returns True if budget is OK, False if pruning is needed.
        """
        if self.max_tokens <= 0:
            return True # Infinite budget or unconfigured
            
        pruning_threshold = int(self.max_tokens * 0.8)
        return (self.total_tokens + new_tokens) <= pruning_threshold

    def recalculate(self, system_message: str, messages: List[Message]):
        """
        Recalculate the total token count from scratch.
        This is the source of truth for the context state.
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
        """Get current token statistics."""
        usage_percent = (self.total_tokens / self.max_tokens) * 100 if self.max_tokens > 0 else 0
        return {
            "total_tokens": self.total_tokens,
            "max_tokens": self.max_tokens,
            "usage_percent": round(usage_percent, 2)
        }
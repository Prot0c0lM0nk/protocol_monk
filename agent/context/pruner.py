import logging
from typing import List
from agent.context.message import Message
from agent.context.token_accountant import TokenAccountant
from agent.context.exceptions_expanded import TokenEstimationError


class ContextPruner:
    """Handles pruning logic when token limits are exceeded."""

    def __init__(self, max_tokens: int):
        self.max_tokens = max_tokens
        self.logger = logging.getLogger(__name__)

    def prune(
        self, conversation: List[Message], accountant: TokenAccountant
    ) -> List[Message]:
        """
        Prunes the conversation list to fit 60% of max_tokens.
        Uses the TokenAccountant for accurate token estimation.
        """
        self.logger.info(f"Pruning conversation. Start count: {len(conversation)}")

        # Enhanced minimum conversation logic that considers token budget constraints
        if len(conversation) <= 4:  # Keep minimum viable conversation
            # But still validate that we're within token budget
            current_tokens = sum(
                accountant.estimate(msg.content) for msg in conversation
            )
            if current_tokens > self.max_tokens:
                self.logger.warning(
                    f"Minimum conversation ({len(conversation)} messages) exceeds token budget ({current_tokens} > {self.max_tokens})"
                )
            return conversation

        # 1. Run scoring
        scored_messages = []
        total_messages = len(conversation)

        for i, msg in enumerate(conversation):
            score = msg.importance

            # Recency boost: more recent = higher score
            # Scales from 0 (oldest) to 2 (newest)
            recency_boost = (i / total_messages) * 2
            score += recency_boost

            # Role boost: user messages are always important
            if msg.role == "user":
                score += 2

            scored_messages.append((score, i, msg))

        # 2. Sort by score (highest first)
        scored_messages.sort(key=lambda x: x[0], reverse=True)

        # 3. Keep top messages that fit in token budget
        kept_messages = []
        current_tokens = 0
        target_tokens = int(self.max_tokens * 0.6)  # Target 60% after pruning

        for score, original_index, msg in scored_messages:
            # Use the TokenAccountant for accurate token estimation
            # Use the TokenAccountant for accurate token estimation
            try:
                msg_tokens = accountant.estimate(msg.content)
            except TokenEstimationError:
                # Re-raise token estimation errors with context about pruning
                raise
            except Exception as e:
                # Handle any other estimation failures
                raise TokenEstimationError(
                    f"Token estimation failed during pruning for message: {e}",
                    estimator_name=getattr(
                        accountant.estimator, "__class__.__name__", "Unknown"
                    ),
                    failed_text=msg.content[:100] if msg.content else "",
                    original_error=e,
                ) from e

            if current_tokens + msg_tokens <= target_tokens:
                kept_messages.append((original_index, msg))
                current_tokens += msg_tokens

        # 4. Rebuild conversation in chronological order
        final_list = [msg for _, msg in sorted(kept_messages, key=lambda x: x[0])]
        self.logger.info(f"Pruning complete. New count: {len(final_list)}")
        return final_list

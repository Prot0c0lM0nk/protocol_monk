#!/usr/bin/env python3
"""
Context Pruner Module
=====================
Handles the logic for trimming conversation history when token limits are reached.
Prioritizes messages based on importance scores, recency, and role.
"""

import logging
from typing import List, Tuple

from agent.context.exceptions_expanded import TokenEstimationError
from agent.context.message import Message
from agent.context.token_accountant import TokenAccountant


class ContextPruner:
    """Handles pruning logic when token limits are exceeded."""

    def __init__(self, max_tokens: int):
        self.max_tokens = max_tokens
        self.logger = logging.getLogger(__name__)

    def _score_messages(
        self, conversation: List[Message]
    ) -> List[Tuple[float, int, Message]]:
        """Calculate importance scores for each message."""
        scored_messages = []
        total_messages = len(conversation)

        for i, msg in enumerate(conversation):
            score = float(msg.importance)

            # Recency boost: more recent = higher score
            # Scales from 0 (oldest) to 2 (newest)
            recency_boost = (i / total_messages) * 2
            score += recency_boost

            # Role boost: user messages are always important
            if msg.role == "user":
                score += 2

            scored_messages.append((score, i, msg))
        return scored_messages

    def _estimate_message_tokens(
        self, msg: Message, accountant: TokenAccountant
    ) -> int:
        """Estimate tokens for a single message with error handling."""
        try:
            return accountant.estimate(msg.content)
        except TokenEstimationError:
            # Re-raise known token estimation errors
            raise
        except Exception as e:
            # Wrap unknown errors
            estimator_name = getattr(
                accountant.estimator, "__class__.__name__", "Unknown"
            )
            raise TokenEstimationError(
                f"Token estimation failed during pruning: {e}",
                estimator_name=estimator_name,
                failed_text=msg.content[:100] if msg.content else "",
                original_error=e,
            ) from e

    def _select_fitting_messages(
        self,
        scored_messages: List[Tuple[float, int, Message]],
        accountant: TokenAccountant,
    ) -> List[Tuple[int, Message]]:
        """Select highest scoring messages that fit within the budget."""
        kept_messages = []
        current_tokens = 0
        target_tokens = int(
            self.max_tokens * 0.7
        )  # Target 70% after pruning (more aggressive)

        # Iterate through messages (highest score first)
        for _, original_index, msg in scored_messages:
            msg_tokens = self._estimate_message_tokens(msg, accountant)

            if current_tokens + msg_tokens <= target_tokens:
                kept_messages.append((original_index, msg))
                current_tokens += msg_tokens

        return kept_messages

    def prune(
        self, conversation: List[Message], accountant: TokenAccountant
    ) -> List[Message]:
        """
        Prunes the conversation list to fit 60% of max_tokens.
        Uses the TokenAccountant for accurate token estimation.
        """
        self.logger.info("Pruning conversation. Start count: %d", len(conversation))

        # Enhanced minimum conversation logic
        if len(conversation) <= 4:
            current_tokens = sum(
                accountant.estimate(msg.content) for msg in conversation
            )
            if current_tokens > self.max_tokens:
                self.logger.warning(
                    "Minimum conversation (%d msgs) exceeds budget (%d > %d)",
                    len(conversation),
                    current_tokens,
                    self.max_tokens,
                )
                # Even for minimum conversations, we must fit within limits
                # Try to prune individual messages if needed
                return self._select_fitting_messages(
                    [(0.0, i, msg) for i, msg in enumerate(conversation)], accountant
                )
            return conversation

        # 1. Score messages
        scored_messages = self._score_messages(conversation)

        # 2. Sort by score (highest first)
        scored_messages.sort(key=lambda x: x[0], reverse=True)

        # 3. Select messages that fit in budget
        kept_messages = self._select_fitting_messages(scored_messages, accountant)

        # 4. Rebuild conversation in chronological order
        final_list = [msg for _, msg in sorted(kept_messages, key=lambda x: x[0])]

        self.logger.info("Pruning complete. New count: %d", len(final_list))
        return final_list

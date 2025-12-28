#!/usr/bin/env python3
"""
Context Pruner Module
=====================
Handles the logic for trimming conversation history when token limits are reached.
Prioritizes messages based on importance scores, recency, and role.
"""

import logging
import json
from typing import List, Tuple

from exceptions import TokenEstimationError
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
        """
        Calculate importance scores for each message.
        """
        scored_messages = []
        total_messages = len(conversation)

        for i, msg in enumerate(conversation):
            score = float(msg.importance)

            # Recency boost: more recent = higher score
            recency_boost = (i / total_messages) * 2
            score += recency_boost

            # Role boost
            if msg.role == "user":
                score += 2
            elif msg.role == "tool":
                score += 1

            scored_messages.append((score, i, msg))
        return scored_messages

    def _estimate_message_tokens(
        self, msg: Message, accountant: TokenAccountant
    ) -> int:
        """
        Estimate tokens for a single message with error handling.
        Handles both text content and native tool calls.
        """
        try:
            total_tokens = 0
            
            # 1. Estimate Text Content
            if msg.content:
                total_tokens += accountant.estimate(msg.content)
            
            # 2. Estimate Tool Calls (Assistant)
            if msg.tool_calls:
                # Serialize to string to get a rough token count for the JSON structure
                tool_str = json.dumps(msg.tool_calls)
                total_tokens += accountant.estimate(tool_str)
                
            # 3. Estimate Tool Results (Tool)
            # (Content is already handled in step 1, but if we had extra fields they'd go here)
            
            return max(1, total_tokens) # Ensure we never return 0 for a valid message

        except TokenEstimationError:
            raise
        except Exception as e:
            estimator_name = getattr(
                accountant.estimator, "__class__.__name__", "Unknown"
            )
            # Fallback for safety
            self.logger.warning(f"Token estimation failed: {e}. using fallback.")
            return 10

    def _select_fitting_messages(
        self,
        scored_messages: List[Tuple[float, int, Message]],
        accountant: TokenAccountant,
    ) -> List[Tuple[int, Message]]:
        """
        Select highest scoring messages that fit within the budget.
        """
        kept_messages = []
        current_tokens = 0
        target_tokens = int(self.max_tokens * 0.7)

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
        Prunes the conversation list to fit within max_tokens.
        """
        self.logger.info("Pruning conversation. Start count: %d", len(conversation))

        if len(conversation) <= 4:
            # Minimal logic for short convos
            current_tokens = sum(self._estimate_message_tokens(msg, accountant) for msg in conversation)
            if current_tokens > self.max_tokens:
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
        final_list = [msg for _, msg in sorted(kept_messages, key=lambda x: x[1])]

        self.logger.info("Pruning complete. New count: %d", len(final_list))
        return final_list
import logging
from typing import List
from agent.context.message import Message
from agent.context.token_accountant import TokenAccountant

class ContextPruner:
    """Handles pruning logic when token limits are exceeded."""
    def __init__(self, max_tokens: int):
        self.max_tokens = max_tokens
        self.logger = logging.getLogger(__name__)

    def prune(self, conversation: List[Message], accountant: TokenAccountant) -> List[Message]:
        """
        Prunes the conversation list to fit 60% of max_tokens.
        Uses the TokenAccountant for accurate token estimation.
        """
        self.logger.info(f"Pruning conversation. Start count: {len(conversation)}")
        
        if len(conversation) <= 4:  # Keep minimum viable conversation
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
            msg_tokens = accountant.estimate(msg.content)
            
            if current_tokens + msg_tokens <= target_tokens:
                kept_messages.append((original_index, msg))
                current_tokens += msg_tokens

        # 4. Rebuild conversation in chronological order
        final_list = [msg for _, msg in sorted(kept_messages, key=lambda x: x[0])]
        self.logger.info(f"Pruning complete. New count: {len(final_list)}")
        return final_list
from typing import List, Tuple
from protocol_monk.agent.structs import Message, ContextStats


def count_tokens(text: str) -> int:
    """
    Pure function to estimate token count.

    TODO: Replace with 'tiktoken' or similar in future iterations.
    For now, we use a safe estimation (chars / 4).
    """
    if not text:
        return 0
    return len(text) // 4


def should_prune(stats: ContextStats, limit: int) -> bool:
    """
    Decides if context is overflowing.
    """
    return stats.total_tokens > limit


def prune_messages(messages: List[Message], target_token_count: int) -> List[Message]:
    """
    Pure pruning algorithm.

    Strategy:
    1. Always keep the SYSTEM prompt (index 0).
    2. Remove messages from the beginning of the conversation (after system)
       until we fit within target_token_count.
    3. Return a NEW list.
    """
    if not messages:
        return []

    # 1. Identify System Prompt
    system_msg = None
    if messages[0].role == "system":
        system_msg = messages[0]
        conversation = messages[1:]
    else:
        conversation = messages[:]

    # 2. Calculate current load
    current_tokens = sum(count_tokens(m.content) for m in conversation)
    if system_msg:
        current_tokens += count_tokens(system_msg.content)

    # 3. Prune if needed
    pruned_conversation = list(conversation)  # Copy
    while current_tokens > target_token_count and pruned_conversation:
        removed_msg = pruned_conversation.pop(0)
        current_tokens -= count_tokens(removed_msg.content)

    # 4. Reassemble
    result = []
    if system_msg:
        result.append(system_msg)
    result.extend(pruned_conversation)

    return result

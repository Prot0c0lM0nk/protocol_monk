import json
from typing import List, Set, Optional
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


def _find_tool_call_ids(message: Message) -> Set[str]:
    """
    Extract all tool_call_ids from an assistant message.
    Checks both first-class field and metadata for backward compatibility.
    """
    if message.role != "assistant":
        return set()

    call_ids = set()

    # Check first-class field first
    if message.tool_calls:
        for tc in message.tool_calls:
            if isinstance(tc, dict) and tc.get("id"):
                call_ids.add(str(tc["id"]))

    # Also check metadata for any additional call IDs
    metadata_calls = message.metadata.get("tool_calls") or []
    for tc in metadata_calls:
        if isinstance(tc, dict) and tc.get("id"):
            call_ids.add(str(tc["id"]))

    return call_ids


def _get_tool_call_id(message: Message) -> Optional[str]:
    """
    Get tool_call_id from a tool-role message.
    Checks both first-class field and metadata for backward compatibility.
    """
    if message.role != "tool":
        return None

    # Check first-class field first
    if message.tool_call_id:
        return message.tool_call_id

    # Fallback to metadata
    return message.metadata.get("tool_call_id")


def _message_tokens(message: Message) -> int:
    """
    Estimate tokens for a message including content, metadata, and tool fields.
    """
    total = count_tokens(message.content or "")

    # Include metadata in token count
    if message.metadata:
        total += count_tokens(json.dumps(message.metadata, ensure_ascii=False, default=str))

    # Include first-class tool fields
    if message.tool_call_id:
        total += count_tokens(message.tool_call_id)
    if message.name:
        total += count_tokens(message.name)
    if message.tool_calls:
        total += count_tokens(json.dumps(message.tool_calls, ensure_ascii=False, default=str))

    return total


def _build_turn_chunks(messages: List[Message]) -> List[List[Message]]:
    """
    Group messages into atomic turn chunks.

    Turn chunk structure:
    - A turn starts with a user message
    - It includes the assistant response (with optional tool_calls)
    - It includes all tool result messages that match the assistant's tool_calls
    - A turn ends when:
      - A new user message starts
      - All tool results for the assistant's tool_calls have been received

    This ensures we never orphan tool results from their parent assistant message.
    """
    if not messages:
        return []

    chunks: List[List[Message]] = []
    current_chunk: List[Message] = []
    pending_tool_ids: Set[str] = set()

    for msg in messages:
        # System messages are standalone
        if msg.role == "system":
            if current_chunk:
                chunks.append(current_chunk)
                current_chunk = []
            chunks.append([msg])
            continue

        current_chunk.append(msg)

        if msg.role == "assistant":
            # Track tool call IDs this assistant is waiting for
            call_ids = _find_tool_call_ids(msg)
            pending_tool_ids.update(call_ids)

        if msg.role == "tool":
            # Remove from pending when we see the result
            tool_id = _get_tool_call_id(msg)
            if tool_id and tool_id in pending_tool_ids:
                pending_tool_ids.discard(tool_id)

        # Check if turn is complete
        # A turn ends when:
        # 1. We see a user message (new turn starting)
        # 2. An assistant responded with no tool calls
        # 3. All tool results have been received
        if msg.role == "user":
            # User message starts a new turn - finalize previous if exists
            if len(current_chunk) > 1:
                # More than just this user message means we had a previous turn
                prev_chunk = current_chunk[:-1]
                current_chunk = [msg]
                chunks.append(prev_chunk)
        elif msg.role == "assistant" and not pending_tool_ids:
            # Assistant with no pending tool calls - turn complete
            chunks.append(current_chunk)
            current_chunk = []
        elif msg.role == "tool" and not pending_tool_ids:
            # All tool results received - turn complete
            chunks.append(current_chunk)
            current_chunk = []

    # Handle remaining messages
    if current_chunk:
        chunks.append(current_chunk)

    return chunks


def prune_messages(messages: List[Message], target_token_count: int) -> List[Message]:
    """
    Turn-aware pruning algorithm.

    Strategy:
    1. Always keep the SYSTEM prompt (first message with role="system").
    2. Build atomic turn chunks (user -> assistant -> tool_results).
    3. Remove complete chunks from the beginning (oldest first).
    4. Never orphan tool results from their parent assistant message.

    This prevents the structural failure where tool results exist without
    their corresponding assistant tool_calls, which causes provider-side
    validation errors and model confusion.
    """
    if not messages:
        return []

    # Separate system prompt
    system_msg = None
    conversation = messages[:]
    if messages and messages[0].role == "system":
        system_msg = messages[0]
        conversation = messages[1:]

    if not conversation:
        # Only system prompt
        return [system_msg] if system_msg else []

    # Build turn chunks
    chunks = _build_turn_chunks(conversation)

    # Calculate current tokens
    def chunk_tokens(chunk: List[Message]) -> int:
        return sum(_message_tokens(m) for m in chunk)

    current_tokens = sum(chunk_tokens(chunk) for chunk in chunks)
    if system_msg:
        current_tokens += _message_tokens(system_msg)

    # Prune chunks from the beginning (oldest first)
    pruned_chunks = list(chunks)
    while current_tokens > target_token_count and pruned_chunks:
        removed_chunk = pruned_chunks.pop(0)
        current_tokens -= chunk_tokens(removed_chunk)

    # Reassemble
    result: List[Message] = []
    if system_msg:
        result.append(system_msg)
    for chunk in pruned_chunks:
        result.extend(chunk)

    return result
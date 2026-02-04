#!/usr/bin/env python3
"""
Context Manager V2 - Lock-Free Architecture
===========================================
Eliminates race conditions through:
- No blocking locks
- Atomic state operations
- Background processing
- Event-driven coordination
"""

import json
import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional, Any
from collections import defaultdict

from exceptions import ConfigurationError, ContextValidationError
from config.static import settings

from .file_tracker_v2 import LockFreeFileTracker
from .message import Message
from .pruner import ContextPruner
from .token_manager_v2 import AsyncTokenManager

if TYPE_CHECKING:
    from tools.registry import ToolRegistry


class ContextManagerV2:
    """
    Lock-free context manager using atomic operations and background tasks.
    Eliminates deadlock risk by avoiding shared locks entirely.
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

        # Conversation state (immutable snapshots for thread safety)
        self.conversation: List[Message] = []
        self.system_message = "[System prompt not initialized]"

        # Lock-free components
        self.file_tracker = LockFreeFileTracker(working_dir=working_dir or Path.cwd())
        self.token_manager = AsyncTokenManager(
            max_tokens=max_tokens, tokenizer=tokenizer, model_family="qwen"
        )
        self.pruner = ContextPruner(max_tokens=max_tokens)

        # Event coordination (instead of locks)
        self._message_events = defaultdict(asyncio.Event)
        self._operation_queue: asyncio.Queue = asyncio.Queue()
        self._background_task: asyncio.Task | None = None
        self._running = False

        # Stats
        self._messages_added = 0
        self._operations_processed = 0

    async def start(self):
        """Start background services."""
        if self._running:
            return

        self._running = True

        # Start background services
        await self.file_tracker.start()
        await self.token_manager.start()

        # Start operation processor
        self._background_task = asyncio.create_task(self._operation_processor())

        self.logger.info("ContextManagerV2 started")

    async def stop(self):
        """Stop background services."""
        if not self._running:
            return

        self._running = False

        # Stop background services
        await self.file_tracker.stop()
        await self.token_manager.stop()

        # Stop operation processor
        if self._background_task:
            self._background_task.cancel()
            try:
                await self._background_task
            except asyncio.CancelledError:
                pass
            self._background_task = None

        self.logger.info("ContextManagerV2 stopped")

    async def async_initialize(self):
        """Initialize async components and load system prompt."""
        await self.start()
        self.system_message = await self._build_system_message()
        await self.token_manager.request_recalculation(
            self.system_message, self.conversation
        )

    async def _build_system_message(self) -> str:
        """Reads the system prompt template."""
        try:
            return await asyncio.to_thread(
                settings.filesystem.system_prompt_file.read_text, encoding="utf-8"
            )
        except Exception as e:
            self.logger.error(f"Failed to build system prompt: {e}")
            return "You are Protocol Monk."

    # --- Message Addition Methods (Lock-Free) ---

    async def add_message(
        self, role: str, content: str, importance: Optional[int] = None
    ):
        """
        Add a standard text message.
        Non-blocking - queues the operation for background processing.
        """
        # Queue operation instead of blocking
        await self._operation_queue.put(
            {
                "type": "add_message",
                "role": role,
                "content": content,
                "importance": importance,
            }
        )

        # Wait for completion (but don't block other operations)
        event = asyncio.Event()
        msg_id = f"msg_{self._messages_added}"
        self._message_events[msg_id] = event
        await event.wait()

        # Clean up event
        self._message_events.pop(msg_id, None)

    async def _process_add_message(
        self, role: str, content: str, importance: Optional[int]
    ):
        """
        Actually add the message (runs in background).
        """
        # 1. Trigger file tracker tick (non-blocking)
        await self.file_tracker.tick(self.conversation)

        # 2. Check budget (non-blocking read)
        temp_tokens = self.token_manager.estimate(content or "")
        if not self.token_manager.check_budget(temp_tokens):
            # Prune if needed
            self.conversation = self.pruner.prune(self.conversation, self.token_manager)
            # Request recalculation after prune
            await self.token_manager.request_recalculation(
                self.system_message, self.conversation
            )

        # 3. Create and add message (atomic append)
        imp = importance if importance is not None else (4 if role == "user" else 3)
        msg = Message(role=role, content=content, importance=imp)
        self.conversation.append(msg)

        # 4. Update tokens (atomic add)
        self.token_manager.add(temp_tokens)

        # 5. Signal completion
        self._messages_added += 1
        msg_id = f"msg_{self._messages_added - 1}"
        if msg_id in self._message_events:
            self._message_events[msg_id].set()
            self._message_events.pop(msg_id, None)

    async def add_user_message(self, content: str, importance: int = 4):
        """Add a user message."""
        await self.add_message("user", content, importance)

    async def add_assistant_message(self, content: str, importance: int = 3):
        """Add an assistant message."""
        await self.add_message("assistant", content, importance)

    async def add_tool_call_message(self, tool_calls: List[Dict]):
        """Add an assistant message containing tool calls."""
        # Queue operation
        await self._operation_queue.put(
            {"type": "add_tool_call", "tool_calls": tool_calls}
        )

        # Wait for completion
        event = asyncio.Event()
        msg_id = f"msg_{self._messages_added}"
        self._message_events[msg_id] = event
        await event.wait()
        self._message_events.pop(msg_id, None)

    async def _process_add_tool_call(self, tool_calls: List[Dict]):
        """Process tool call message addition with Robust Format Translation."""
        # Trigger file tracker tick
        await self.file_tracker.tick(self.conversation)

        # Convert tool calls
        converted_tool_calls = []
        for tc in tool_calls:
            # 1. Handle Pydantic Objects (Ollama SDK native)
            if hasattr(tc, "function"):
                func = tc.function
                arguments = func.arguments
                if isinstance(arguments, str):
                    try:
                        arguments = json.loads(arguments)
                    except json.JSONDecodeError:
                        pass
                converted_tool_calls.append(
                    {
                        "type": "function",
                        "function": {
                            "name": func.name,
                            "arguments": arguments,
                        },
                    }
                )

            # 2. Handle Internal "MonkCode" Format ({"action": "...", "parameters": ...})
            # This is the translation layer that fixes the crash.
            elif isinstance(tc, dict) and "action" in tc:
                converted_tool_calls.append(
                    {
                        "type": "function",
                        "function": {
                            "name": tc["action"],
                            "arguments": tc.get("parameters", {}),
                        },
                    }
                )

            # 3. Handle Standard API Dicts ({"function": ...})
            elif isinstance(tc, dict) and "function" in tc:
                converted_tool_calls.append(tc)

            # 4. Fallback (try to wrap whatever it is)
            else:
                converted_tool_calls.append({"type": "function", "function": tc})

        # Create and add
        msg = Message(
            role="assistant",
            content=None,
            tool_calls=converted_tool_calls,
            importance=5,
        )
        self.conversation.append(msg)

        # Update tokens
        self.token_manager.add(100 * len(converted_tool_calls))

        # Signal completion
        msg_id = f"msg_{self._messages_added}"
        if msg_id in self._message_events:
            self._message_events[msg_id].set()
            self._message_events.pop(msg_id, None)

    async def add_tool_result_message(
        self,
        tool_name: str,
        tool_call_id: Optional[str],
        content: str,
        file_path: Optional[str] = None,
    ):
        """Add a tool result message with file decay support."""
        # Queue operation
        await self._operation_queue.put(
            {
                "type": "add_tool_result",
                "tool_name": tool_name,
                "tool_call_id": tool_call_id,
                "content": content,
                "file_path": file_path,
            }
        )

        # Wait for completion
        event = asyncio.Event()
        msg_id = f"msg_{self._messages_added}"
        self._message_events[msg_id] = event
        await event.wait()
        self._message_events.pop(msg_id, None)

    async def _process_add_tool_result(
        self,
        tool_name: str,
        tool_call_id: Optional[str],
        content: str,
        file_path: Optional[str],
    ):
        """Process tool result message addition."""
        # Trigger file tracker tick
        await self.file_tracker.tick(self.conversation)

        # Trigger decay if file path provided
        metadata = {}
        if file_path:
            await self.file_tracker.trigger_decay(
                file_path, self.conversation, grace_period_msgs=20
            )
            metadata = {"file_read": file_path}

        # Create and add
        msg = Message(
            role="tool",
            content=content,
            name=tool_name,
            tool_call_id=tool_call_id,
            importance=5,
            metadata=metadata,
        )
        self.conversation.append(msg)

        # Update tokens
        self.token_manager.add(self.token_manager.estimate(content))

        # Signal completion
        msg_id = f"msg_{self._messages_added}"
        if msg_id in self._message_events:
            self._message_events[msg_id].set()
            self._message_events.pop(msg_id, None)

    async def remove_last_message(self):
        """Remove the last message."""
        await self._operation_queue.put({"type": "remove_last"})

        event = asyncio.Event()
        msg_id = f"remove_{self._messages_added}"
        self._message_events[msg_id] = event
        await event.wait()
        self._message_events.pop(msg_id, None)

    async def _process_remove_last(self):
        """Process message removal."""
        if not self.conversation:
            return

        msg = self.conversation.pop()

        # Request recalculation
        await self.token_manager.request_recalculation(
            self.system_message, self.conversation
        )

        self.logger.info(f"Context Scrub: Removed last message (role={msg.role})")

        # Signal completion
        msg_id = f"remove_{self._messages_added}"
        if msg_id in self._message_events:
            self._message_events[msg_id].set()
            self._message_events.pop(msg_id, None)

    # --- Context Retrieval (Non-Blocking) ---

    async def get_context(
        self, model_name: str = None, provider: str = "ollama"
    ) -> List[Dict]:
        """
        Get conversation context for LLM.
        Non-blocking read of current state.
        """
        # Start with system message
        context = [{"role": "system", "content": self.system_message}]

        # Append conversation (read-only, no locks needed)
        for msg in self.conversation:
            context.append(msg.to_dict())

        return context

    async def clear(self):
        """Clear all conversation state."""
        await self._operation_queue.put({"type": "clear"})

        event = asyncio.Event()
        msg_id = f"clear_{self._messages_added}"
        self._message_events[msg_id] = event
        await event.wait()
        self._message_events.pop(msg_id, None)

    async def _process_clear(self):
        """Process clear operation."""
        self.conversation = []
        await self.file_tracker.clear()
        await self.token_manager.request_recalculation(
            self.system_message, self.conversation
        )

        # Signal completion
        msg_id = f"clear_{self._messages_added}"
        if msg_id in self._message_events:
            self._message_events[msg_id].set()
            self._message_events.pop(msg_id, None)

    # --- Properties and Stats ---

    @property
    def max_tokens(self) -> int:
        """Get max token limit."""
        return self.token_manager.max_tokens

    async def get_stats(self) -> Dict:
        """Get current statistics."""
        stats = self.token_manager.get_stats()
        stats["total_messages"] = len(self.conversation)
        stats["messages_added"] = self._messages_added
        stats["operations_processed"] = self._operations_processed
        return stats

    def get_total_tokens(self) -> int:
        """Get current token count (non-blocking)."""
        return self.token_manager.total_tokens

    async def clear_old_messages(self):
        """Clear old messages to prevent overflow."""
        await self._operation_queue.put({"type": "clear_old"})

        event = asyncio.Event()
        msg_id = f"clear_old_{self._messages_added}"
        self._message_events[msg_id] = event
        await event.wait()
        self._message_events.pop(msg_id, None)

    async def _process_clear_old_messages(self):
        """Process old message clearing."""
        self.logger.info("Clearing old messages due to context overflow")

        if len(self.conversation) <= 2:
            return

        # Keep system message if present
        system_msg = None
        conversation_start = 0
        if self.conversation and self.conversation[0].role == "system":
            system_msg = self.conversation[0]
            conversation_start = 1

        # Find complete pairs from end
        conv_messages = self.conversation[conversation_start:]
        kept_pairs = []

        i = len(conv_messages) - 1
        while i >= 1:
            if (
                conv_messages[i].role == "assistant"
                and conv_messages[i - 1].role == "user"
            ):
                kept_pairs.insert(0, conv_messages[i - 1])
                kept_pairs.insert(1, conv_messages[i])
                i -= 2
            else:
                break

        # Fallback if no pairs
        if not kept_pairs and len(conv_messages) >= 2:
            last_two = conv_messages[-2:]
            if last_two[0].role != last_two[1].role:
                kept_pairs = last_two
            else:
                kept_pairs = [conv_messages[-1]]
        elif not kept_pairs and conv_messages:
            kept_pairs = [conv_messages[-1]]

        # Rebuild conversation
        self.conversation = []
        if system_msg:
            self.conversation.append(system_msg)
        self.conversation.extend(kept_pairs)

        # Request recalculation
        await self.token_manager.request_recalculation(
            self.system_message, self.conversation
        )

        self.logger.info(f"Cleared old messages. New count: {len(self.conversation)}")

        # Signal completion
        msg_id = f"clear_old_{self._messages_added}"
        if msg_id in self._message_events:
            self._message_events[msg_id].set()
            self._message_events.pop(msg_id, None)

    async def update_max_tokens(self, new_max_tokens: int):
        """Update max token limit."""
        await self._operation_queue.put(
            {"type": "update_max_tokens", "new_max_tokens": new_max_tokens}
        )

        event = asyncio.Event()
        msg_id = f"update_max_{self._messages_added}"
        self._message_events[msg_id] = event
        await event.wait()
        self._message_events.pop(msg_id, None)

    async def _process_update_max_tokens(self, new_max_tokens: int):
        """Process max tokens update."""
        self.token_manager.max_tokens = new_max_tokens
        self.pruner.max_tokens = new_max_tokens
        self.logger.info(f"Context window updated to {new_max_tokens:,} tokens")

        # Trigger prune if needed
        if self.token_manager.total_tokens > new_max_tokens:
            self.logger.warning(
                f"Current token usage ({self.token_manager.total_tokens:,}) exceeds "
                f"new limit ({new_max_tokens:,}), triggering prune..."
            )
            self.conversation = self.pruner.prune(self.conversation, self.token_manager)
            await self.token_manager.request_recalculation(
                self.system_message, self.conversation
            )

        # Signal completion
        msg_id = f"update_max_{self._messages_added}"
        if msg_id in self._message_events:
            self._message_events[msg_id].set()
            self._message_events.pop(msg_id, None)

    # --- Background Operation Processor ---

    async def _operation_processor(self):
        """
        Background task that processes queued operations.
        This is the heart of the lock-free architecture.
        """
        while self._running:
            try:
                # Wait for operation with timeout
                operation = await asyncio.wait_for(
                    self._operation_queue.get(), timeout=0.1
                )

                # Process operation
                op_type = operation.get("type")

                if op_type == "add_message":
                    await self._process_add_message(
                        operation["role"],
                        operation["content"],
                        operation.get("importance"),
                    )

                elif op_type == "add_tool_call":
                    await self._process_add_tool_call(operation["tool_calls"])

                elif op_type == "add_tool_result":
                    await self._process_add_tool_result(
                        operation["tool_name"],
                        operation.get("tool_call_id"),
                        operation["content"],
                        operation.get("file_path"),
                    )

                elif op_type == "remove_last":
                    await self._process_remove_last()

                elif op_type == "clear":
                    await self._process_clear()

                elif op_type == "clear_old":
                    await self._process_clear_old_messages()

                elif op_type == "update_max_tokens":
                    await self._process_update_max_tokens(operation["new_max_tokens"])

                self._operations_processed += 1

            except asyncio.TimeoutError:
                # No operations, continue loop
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error processing operation: {e}", exc_info=True)
                # Increment counter to prevent deadlock for waiting operations
                self._operations_processed += 1

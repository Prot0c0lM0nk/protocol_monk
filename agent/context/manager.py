#!/usr/bin/env python3
"""
Context Manager
===============
Manages conversation history using Native Tool Calling standards.
"""

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional, Any

from exceptions import ConfigurationError, ContextValidationError
from config.static import settings

from .file_tracker import FileTracker
from .message import Message
from .pruner import ContextPruner
from .token_accountant import TokenAccountant

if TYPE_CHECKING:
    from tools.registry import ToolRegistry


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
        self.system_message = "[System prompt not initialized]"

        # Instantiate components
        self.accountant = TokenAccountant(max_tokens=max_tokens, tokenizer=tokenizer)
        self.tracker = FileTracker(working_dir=working_dir or Path.cwd())
        self.pruner = ContextPruner(max_tokens=max_tokens)

    async def async_initialize(self):
        """Initialize async components and load system prompt."""
        self.system_message = await self._build_system_message()
        self.accountant.recalculate(self.system_message, self.conversation)

    async def _build_system_message(self) -> str:
        """Reads the system prompt template."""
        try:
            return await asyncio.to_thread(
                settings.filesystem.system_prompt_file.read_text, encoding="utf-8"
            )
        except Exception as e:
            self.logger.error(f"Failed to build system prompt: {e}")
            return "You are Protocol Monk."

    # --- Message Addition Methods ---

    async def add_message(
        self, role: str, content: str, importance: Optional[int] = None
    ):
        """Add a standard text message (User/System)."""
        async with self._lock:
            # 1. Run Decay Tick
            await self.tracker.tick(self.conversation)

            # 2. Basic pruning check
            temp_tokens = self.accountant.estimate(content or "")
            if not self.accountant.check_budget(temp_tokens):
                self.conversation = self.pruner.prune(self.conversation, self.accountant)
            
            # 3. Create and add
            imp = importance if importance is not None else (4 if role == "user" else 3)
            msg = Message(role=role, content=content, importance=imp)
            self.conversation.append(msg)
            self.accountant.add(temp_tokens)

    async def add_user_message(self, content: str, importance: int = 4):
        """
        Add a message from the user.
        """
        await self.add_message("user", content, importance)

    async def add_assistant_message(self, content: str, importance: int = 3):
        """
        Add a message from the assistant (AI).
        """
        await self.add_message("assistant", content, importance)

    async def add_tool_call_message(self, tool_calls: List[Dict]):
        """
        Add an Assistant message containing tool calls.
        """
        async with self._lock:
            # 1. Run Decay Tick
            await self.tracker.tick(self.conversation)

            msg = Message(
                role="assistant",
                content=None,
                tool_calls=tool_calls,
                importance=5 
            )
            self.conversation.append(msg)
            # Estimate tokens roughly
            self.accountant.add(100 * len(tool_calls)) 

    async def add_tool_result_message(
        self, 
        tool_name: str, 
        tool_call_id: Optional[str], 
        content: str,
        file_path: Optional[str] = None
    ):
        """
        Add a Tool Result message.
        Handles "Graceful Decay" if a file path is involved.
        """
        async with self._lock:
            # 1. Run Decay Tick first
            await self.tracker.tick(self.conversation)

            # 2. Trigger Decay for OLD reads (if this is a file read)
            if file_path:
                # We start the countdown for ANY previous copies of this file
                # Default 20 messages = approx 5 turns
                await self.tracker.trigger_decay(file_path, self.conversation, grace_period_msgs=20)
                metadata = {"file_read": file_path}
            else:
                metadata = {}

            # 3. Add New Message
            msg = Message(
                role="tool",
                content=content,
                name=tool_name,
                tool_call_id=tool_call_id,
                importance=5,
                metadata=metadata
            )
            self.conversation.append(msg)
            
            # 4. Update Tokens
            self.accountant.add(self.accountant.estimate(content))

    async def _tick(self):
        """
        Run the decay timer on the file tracker.
        Should be called before adding new messages.
        """
        await self.tracker.tick(self.conversation)

    # --- Context Retrieval ---

    async def get_context(
        self, model_name: str = None, provider: str = "ollama"
    ) -> List[Dict]:
        """
        Formats the conversation strictly for the LLM API.
        Returns native list-of-dicts.
        """
        async with self._lock:
            # Start with System Message
            context = [{"role": "system", "content": self.system_message}]
            
            # Append History (using to_dict to strip internal fields)
            for msg in self.conversation:
                context.append(msg.to_dict())
                
            return context

    async def clear(self):
        async with self._lock:
            self.conversation = []
            await self.tracker.clear()
            self.accountant.recalculate(self.system_message, self.conversation)

    @property
    def max_tokens(self) -> int:
        """
        Return the maximum token limit.
        Required by status display.
        """
        return self.accountant.max_tokens
            
    async def get_stats(self) -> Dict:
        """Returns current usage statistics."""
        async with self._lock:
            stats = self.accountant.get_stats()
            stats["total_messages"] = len(self.conversation)
            return stats
        
    def get_total_tokens(self) -> int:
        """
        Get the current total token count.
        Required by CommandDispatcher for guardrail checks.
        """
        return self.accountant.total_tokens
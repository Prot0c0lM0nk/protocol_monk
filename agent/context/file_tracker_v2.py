#!/usr/bin/env python3
"""
Lock-Free File Tracker V2
=========================
Uses atomic operations and background tasks instead of locks.
Eliminates deadlock risk by avoiding shared locks entirely.
"""

import asyncio
import logging
from pathlib import Path
from typing import List, Dict, Set
from collections import defaultdict
from dataclasses import dataclass, field
from agent.context.message import Message


@dataclass
class DecayEntry:
    """Represents a file decay operation."""
    filepath: str
    message_index: int  # Index in conversation
    turns_remaining: int


class LockFreeFileTracker:
    """
    Lock-free file tracking using:
    - Atomic state updates
    - Background decay processing
    - No blocking locks
    """

    def __init__(self, working_dir: Path):
        self.working_dir = working_dir
        self.logger = logging.getLogger(__name__)

        # Atomic state - no locks needed
        self._decay_queue: asyncio.Queue[DecayEntry] = asyncio.Queue()
        self._file_read_counts: Dict[str, int] = defaultdict(int)
        self._background_task: asyncio.Task | None = None
        self._running = False

    async def start(self):
        """Start background decay processing."""
        if self._running:
            return

        self._running = True
        self._background_task = asyncio.create_task(self._decay_processor())
        self.logger.info("LockFreeFileTracker started")

    async def stop(self):
        """Stop background processing."""
        if not self._running:
            return

        self._running = False
        if self._background_task:
            self._background_task.cancel()
            try:
                await self._background_task
            except asyncio.CancelledError:
                pass
            self._background_task = None

        self.logger.info("LockFreeFileTracker stopped")

    async def trigger_decay(
        self,
        filepath: str,
        conversation: List[Message],
        grace_period_msgs: int = 40
    ):
        """
        Mark old reads of a file for decay.
        Non-blocking - just queues the operation.
        """
        if not filepath:
            return

        # Find all messages with this file read that aren't decaying yet
        for idx, msg in enumerate(conversation):
            if (
                msg.metadata.get("file_read") == filepath
                and "turns_left" not in msg.metadata
            ):
                # Queue decay operation - no lock needed
                entry = DecayEntry(
                    filepath=filepath,
                    message_index=idx,
                    turns_remaining=grace_period_msgs
                )
                await self._decay_queue.put(entry)

                # Atomic update to metadata
                msg.metadata["turns_left"] = grace_period_msgs

                self.logger.debug(
                    f"Queued decay for {filepath} at index {idx}, "
                    f"expires in {grace_period_msgs} messages"
                )

    async def tick(self, conversation: List[Message]):
        """
        Process one tick of decay.
        Non-blocking - just queues decrements.
        """
        # Find all decaying messages and queue decrements
        for idx, msg in enumerate(conversation):
            if "turns_left" in msg.metadata:
                turns = msg.metadata["turns_left"]
                if turns > 0:
                    # Queue decrement
                    entry = DecayEntry(
                        filepath=msg.metadata.get("file_read", "unknown"),
                        message_index=idx,
                        turns_remaining=turns - 1
                    )
                    await self._decay_queue.put(entry)
                    msg.metadata["turns_left"] = turns - 1

    async def _decay_processor(self):
        """
        Background task that processes decay queue.
        Runs independently without blocking main operations.
        """
        while self._running:
            try:
                # Wait for entry with timeout to allow graceful shutdown
                entry = await asyncio.wait_for(
                    self._decay_queue.get(),
                    timeout=0.1
                )

                if entry.turns_remaining <= 0:
                    # Mark as expired - this is done atomically
                    # The actual invalidation happens when conversation is accessed
                    self.logger.debug(
                        f"Decay complete for {entry.filepath} at index {entry.message_index}"
                    )

            except asyncio.TimeoutError:
                # No entries to process, continue loop
                continue
            except asyncio.CancelledError:
                # Task cancelled, exit gracefully
                break
            except Exception as e:
                self.logger.error(f"Error in decay processor: {e}")

    def get_expired_files(self, conversation: List[Message]) -> Set[str]:
        """
        Get set of files that have expired decay counters.
        This is a read-only operation, no locks needed.
        """
        expired = set()
        for msg in conversation:
            if msg.metadata.get("turns_left", 0) <= 0:
                filepath = msg.metadata.get("file_read")
                if filepath:
                    expired.add(filepath)
        return expired

    async def invalidate_expired(self, conversation: List[Message]):
        """
        Invalidate all expired file reads.
        Called periodically from background.
        """
        for msg in conversation:
            if msg.metadata.get("turns_left", 0) <= 0:
                filepath = msg.metadata.get("file_read", "unknown_file")

                # Replace content with expiration notice
                msg.content = (
                    f"[System: File content '{filepath}' refreshed. "
                    "See latest messages for current version.]"
                )

                # Clean up metadata
                msg.metadata.pop("turns_left", None)
                msg.metadata.pop("file_read", None)

                self.logger.info(f"Invalidated expired file: {filepath}")

    async def clear(self):
        """Reset all state."""
        # Clear queue
        while not self._decay_queue.empty():
            try:
                self._decay_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

        # Clear counters
        self._file_read_counts.clear()

        self.logger.info("File tracker cleared")

    def get_stats(self) -> Dict:
        """Get current statistics."""
        return {
            "decay_queue_size": self._decay_queue.qsize(),
            "tracked_files": len(self._file_read_counts),
            "running": self._running
        }
import logging
import asyncio
from pathlib import Path
from typing import List

from agent.context.message import Message


class FileTracker:
    """
    Manages file invalidation with a 'Grace Period' decay system.
    Prevents context loops by allowing stale reads to linger briefly.
    """

    def __init__(self, working_dir: Path):
        self.working_dir = working_dir
        self.logger = logging.getLogger(__name__)
        self._lock: asyncio.Lock = asyncio.Lock()

    async def trigger_decay(
        self, filepath: str, conversation: List[Message], grace_period_msgs: int = 20
    ):
        """
        Marks ACTIVE reads of 'filepath' to expire after 'grace_period_msgs'.
        This is called when a NEW read of the same file occurs.
        
        Args:
            grace_period_msgs: How many messages (not turns) until expiration.
                             ~4 messages = 1 conversation turn. 
                             20 messages approx 5 turns.
        """
        if not filepath:
            return

        async with self._lock:
            for msg in conversation:
                # Find active reads (file_read tag present) that aren't yet decaying (no turns_left)
                if msg.metadata.get("file_read") == filepath and "turns_left" not in msg.metadata:
                    msg.metadata["turns_left"] = grace_period_msgs
                    self.logger.info(
                        f"File '{filepath}' marked for decay. Expires in {grace_period_msgs} messages."
                    )

    async def tick(self, conversation: List[Message]):
        """
        Decrements decay counters and invalidates expired messages.
        Must be called whenever a new message is added to history.
        """
        async with self._lock:
            for msg in conversation:
                if "turns_left" in msg.metadata:
                    msg.metadata["turns_left"] -= 1
                    
                    if msg.metadata["turns_left"] <= 0:
                        # EXPIRE THE MESSAGE
                        filepath = msg.metadata.get("file_read", "unknown_file")
                        
                        msg.content = (
                            f"[System: The content of '{filepath}' has been invalidated "
                            "to save context. See newer messages for the latest version.]"
                        )
                        
                        # Cleanup metadata tags
                        del msg.metadata["turns_left"]
                        if "file_read" in msg.metadata:
                            del msg.metadata["file_read"]
                        
                        self.logger.info(f"File '{filepath}' context expired and invalidated.")

    async def clear(self):
        """Reset state."""
        pass
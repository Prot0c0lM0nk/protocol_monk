import logging
import asyncio
from pathlib import Path
from typing import List

from agent.context.message import Message


class FileTracker:
    """
    Manages file invalidation logic.
    Ensures stale file reads are neutralized in the context history.
    """

    def __init__(self, working_dir: Path):
        self.working_dir = working_dir
        self.logger = logging.getLogger(__name__)
        self._lock: asyncio.Lock = asyncio.Lock()

    async def invalidate_file_content(
        self, filepath: str, conversation: List[Message]
    ):
        """
        Scans conversation history. If 'filepath' was previously read,
        replaces its content with a placeholder to force model to use the new read.
        """
        if not filepath:
            return

        async with self._lock:
            for msg in conversation:
                # Check our internal metadata tag
                if msg.metadata.get("file_read") == filepath:
                    # Mutate content to hide stale data
                    msg.content = (
                        f"[System: The content of '{filepath}' has been invalidated "
                        "because a newer version was read. See the latest message.]"
                    )
                    # Remove the tag so we don't process this message again
                    del msg.metadata["file_read"]
                    self.logger.info(f"Invalidated stale context for file: {filepath}")

    async def clear(self):
        """Reset state."""
        pass
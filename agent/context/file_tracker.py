import logging
import re
import asyncio  # Added import
from pathlib import Path
from typing import List, Set

from agent.context.message import Message


class FileTracker:
    """
    Manages file-shown state and content replacement logic.
    Ensures we don't waste context tokens on duplicate file contents.
    """

    def __init__(self, working_dir: Path):
        self.working_dir = working_dir
        self.files_shown: Set[str] = set()
        self._lock: asyncio.Lock = asyncio.Lock()  # NEW: protects files_shown set
        self.logger = logging.getLogger(__name__)

    async def track_file_shown(self, filepath: str) -> int:
        """Mark a file as shown to the user with thread-safe operations."""
        async with self._lock:  # NEW: Acquire lock
            if filepath not in self.files_shown:
                self.files_shown.add(filepath)
                return 1
            return 0

    async def get_file_shown_count(self, filepath: str) -> int:
        """Check if a file is in the tracked set safely."""
        async with self._lock:  # NEW: Acquire lock
            return 1 if filepath in self.files_shown else 0

    @staticmethod
    def _exact_path_match(filepath: str, text: str) -> bool:
        """
        Helper function for regex boundary matching to prevent false positives.

        Args:
            filepath: File path to match
            text: Text to search in

        Returns:
            bool: True if exact path match found
        """
        # For file paths, we want to match the exact path when it appears in text
        # but we're more flexible about boundaries since paths can appear in various contexts
        escaped_path = re.escape(filepath)
        # Look for the path with flexible boundaries - allow it to be preceded by space, colon, or other separators
        # and followed by space, punctuation, or end of string
        pattern = r"(?:^|[\s:>])" + escaped_path + r"(?:$|[\s.,;:!?])"
        match = re.search(pattern, text)
        return bool(match)

    def _validate_file_exists(self, filepath: str) -> bool:
        """
        Validate that a file exists and is readable using atomic operations.
        Eliminates TOCTOU race conditions by using exception-based validation.

        Args:
            filepath: Path to the file to validate

        Returns:
            bool: True if file exists, is readable, and is within working directory
        """
        try:
            path = Path(filepath)
            # Resolve the path to handle relative paths and symlinks
            resolved_path = path.resolve()
            # Resolve working directory as well for consistent comparison
            resolved_working_dir = self.working_dir.resolve()

            # ATOMIC VALIDATION: Try to open the file instead of checking existence
            # This eliminates the TOCTOU race condition between exists() and is_file()
            with resolved_path.open("r") as f:
                # If we can open it, it exists and is a file
                pass

            # Verify it's within working directory boundaries
            return str(resolved_path).startswith(str(resolved_working_dir))

        except (FileNotFoundError, IsADirectoryError, PermissionError):
            # File doesn't exist, is a directory, or we can't access it
            return False
        except Exception as e:
            # Log unexpected errors but don't expose internal details
            self.logger.warning(
                f"Error validating file path {filepath}: {type(e).__name__}"
            )
            return False

    async def replace_old_file_content(
        self, filepath: str, conversation: List[Message]
    ):
        """
        Scans conversation history. If 'filepath' appears multiple times,
        replaces older occurrences with a placeholder to save tokens.

        Args:
            filepath: Path to the file to process
            conversation: List of conversation messages

        Returns:
            None: Modifies conversation in-place
        """
        # Validate file existence first
        if not self._validate_file_exists(filepath):
            self.logger.warning(
                f"File does not exist, skipping replacement: {filepath}"
            )
            return

        # Find indices of messages that contain this file using exact boundary matching
        candidates = [
            (idx, msg)
            for idx, msg in enumerate(conversation)
            if self._exact_path_match(filepath, msg.content)
            and len(msg.content) > 200
            and not msg.content.startswith("[File previously shown")
        ]

        # If we don't have at least 2 copies, there is nothing to replace
        if len(candidates) <= 1:
            return

        # Replace all but the *newest* candidate (the last one in the list)
        for idx, msg in candidates[:-1]:
            msg.content = f"[File previously shown: {filepath}]"
            self.logger.debug(f"Replaced old instance of {filepath} at index {idx}")

    async def clear(self):
        """Reset the tracker state safely."""
        async with self._lock:  # NEW: Acquire lock
            self.files_shown.clear()

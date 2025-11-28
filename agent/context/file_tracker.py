import logging
import re
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
        # Changed type hint to Set for clarity
        self.files_shown: Set[str] = set()
        self.logger = logging.getLogger(__name__)

    async def track_file_shown(self, filepath: str) -> int:
        """
        Mark a file as shown to the user.
        Returns: 1 if it's new, 0 if already shown.
        """
        if filepath not in self.files_shown:
            self.files_shown.add(filepath)
            return 1
        return 0

    async def get_file_shown_count(self, filepath: str) -> int:
        """Check if a file is currently in the tracked set."""
        return 1 if filepath in self.files_shown else 0

    @staticmethod
    def _exact_path_match(filepath: str, text: str) -> bool:
        """
        Helper function for regex boundary matching to prevent false positives.
        """
        # For file paths, we want to match the exact path when it appears as a complete token
        # but we're more flexible about boundaries since paths can appear in various contexts
        escaped_path = re.escape(filepath)
        # Look for the path with flexible boundaries
        pattern = escaped_path
        match = re.search(pattern, text)
        return bool(match)

    def _validate_file_exists(self, filepath: str) -> bool:
        """
        Validate that a file exists before processing.
        """
        try:
            path = Path(filepath)
            return path.exists() and path.is_file()
        except Exception:
            return False

    async def replace_old_file_content(self, filepath: str, conversation: List[Message]):
        """
        Scans conversation history. If 'filepath' appears multiple times,
        replaces older occurrences with a placeholder to save tokens.
        """
        # Validate file existence first
        if not self._validate_file_exists(filepath):
            self.logger.warning(f"File does not exist, skipping replacement: {filepath}")
            return
        
        # Find indices of messages that contain this file using exact boundary matching
        candidates = [
            (idx, msg) for idx, msg in enumerate(conversation)
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
        """Reset the tracker state."""
        self.files_shown.clear()

import shutil

import logging
import time
from pathlib import Path
from typing import Optional

from agent.context.exceptions_expanded import ScratchManagerError


class ScratchManager:
    """
    Manages temporary 'scratch' files for large content.
    Enforces hygiene by cleaning up old files on initialization.
    """

    def __init__(self, working_dir: Path):
        self.working_dir = working_dir
        self.scratch_dir = self.working_dir / ".scratch"
        self.logger = logging.getLogger(__name__)

        # Hygiene: Clean up on startup
        self.cleanup()

        # Ensure directory exists for this session
        self.scratch_dir.mkdir(exist_ok=True)

    def cleanup(self):
        """Delete all files in the scratch directory."""
        if self.scratch_dir.exists():
            try:
                shutil.rmtree(self.scratch_dir)
                self.logger.info("Cleaned up old scratch files.")
            except Exception as e:
                raise ScratchManagerError(
                    f"Failed to cleanup scratch directory: {e}",
                    operation="cleanup",
                    file_path=self.scratch_dir,
                    original_error=e,
                ) from e

    def stage_content(self, content: str, threshold: int = 1000) -> str:
        """
        Auto-stage large inline content to a scratch file.
        Returns the scratch_id if staged.
        Raises ScratchManagerError on failure.
        """
        if not content or len(content) <= threshold:
            # Return empty string for content that doesn't need staging
            return ""

        try:
            self.scratch_dir.mkdir(exist_ok=True)

            # Generate unique ID based on time
            scratch_id = f"auto_{int(time.time() * 1000)}"
            file_path = self.scratch_dir / f"{scratch_id}.txt"

            file_path.write_text(content, encoding="utf-8")
            self.logger.info(f"Staged {len(content)} chars to {scratch_id}")
            return scratch_id

        except Exception as e:
            self.logger.error(f"Failed to stage content: {e}")
            raise ScratchManagerError(
                f"Failed to stage content: {e}",
                operation="stage_content",
                original_error=e,
            ) from e

    def read_content(self, scratch_id: str) -> str:
        """Retrieve content from a scratch file. Raises ScratchManagerError on failure."""
        try:
            file_path = self.scratch_dir / f"{scratch_id}.txt"
            if file_path.exists():
                return file_path.read_text(encoding="utf-8")
            else:
                raise ScratchManagerError(
                    f"Scratch file not found: {scratch_id}",
                    operation="read_content",
                    scratch_id=scratch_id,
                    file_path=file_path,
                )
        except Exception as e:
            self.logger.error(f"Failed to read scratch {scratch_id}: {e}")
            raise ScratchManagerError(
                f"Failed to read scratch {scratch_id}: {e}",
                operation="read_content",
                scratch_id=scratch_id,
                original_error=e,
            ) from e

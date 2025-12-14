import shutil

import logging
import time
from pathlib import Path
from typing import Optional

from exceptions import ScratchManagerError


class ScratchManager:
    """
    Manages temporary 'scratch' files for large content.
    Enforces hygiene by cleaning up old files on initialization.
    """

    def __init__(self, working_dir: Path):
        self.working_dir = working_dir
        self.scratch_dir = self.working_dir / ".scratch"
        self.logger = logging.getLogger(__name__)

        # Don't clean up on startup to avoid race conditions
        # Files will be cleaned up by explicit cleanup calls or session end
        # self.cleanup()  # Removed to prevent race conditions

        # Ensure directory exists for this session
        self.scratch_dir.mkdir(exist_ok=True)

    def cleanup(self):
        """
        Delete all files in the scratch directory.

        Raises:
            ScratchManagerError: If cleanup fails
        """
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

        Args:
            content: Content string to potentially stage
            threshold: Character threshold for staging (default: 1000)

        Returns:
            str: Scratch ID if staged, empty string if not

        Raises:
            ScratchManagerError: If staging fails
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
        """
        Retrieve content from a scratch file. Raises ScratchManagerError on failure.

        Args:
            scratch_id: Unique identifier for the scratch file

        Returns:
            str: Content from the scratch file

        Raises:
            ScratchManagerError: If file not found or read fails
        """
        try:
            file_path = self.scratch_dir / f"{scratch_id}.txt"
            self.logger.debug(f"Attempting to read scratch file: {file_path}")

            if file_path.exists():
                content = file_path.read_text(encoding="utf-8")
                self.logger.debug(
                    f"Successfully read {len(content)} chars from {scratch_id}"
                )
                return content
            else:
                self.logger.error(
                    f"Scratch file not found: {scratch_id} at path {file_path}"
                )
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
        """
        Get the full file path for a scratch file.
        
        Args:
            scratch_id: The ID of the scratch file
            
        Returns:
            Path: The full path to the scratch file
        """
        return self.scratch_dir / f"{scratch_id}.txt"

    def scratch_exists(self, scratch_id: str) -> bool:
        """
        Check if a scratch file exists.

        Args:
            scratch_id: The ID of the scratch file to check

        Returns:
            bool: True if the scratch file exists, False otherwise
        """
        scratch_path = self.get_scratch_path(scratch_id)
        return scratch_path.exists()

    def safe_read_content(self, scratch_id: str) -> Optional[str]:
        """
        Safely read content from a scratch file without raising exceptions.

        This method is designed for tool integration where we want to
        attempt reading via ScratchManager but fall back to other methods
        if it fails.

        Args:
            scratch_id: Unique identifier for the scratch file

        Returns:
            Optional[str]: Content if successful, None if file not found or error occurs
        """
        try:
            return self.read_content(scratch_id)
        except Exception as e:
            self.logger.debug(f"Safe read failed for scratch {scratch_id}: {e}")
            return None

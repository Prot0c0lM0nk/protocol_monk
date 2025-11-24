import logging
import shutil
import time
from pathlib import Path
from typing import Optional

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
                self.logger.warning(f"Failed to cleanup scratch dir: {e}")

    def stage_content(self, content: str, threshold: int = 1000) -> Optional[str]:
        """
        Auto-stage large inline content to a scratch file.
        Returns the scratch_id if staged, None otherwise.
        """
        if not content or len(content) <= threshold:
            return None

        try:
            self.scratch_dir.mkdir(exist_ok=True)
            
            # Generate unique ID based on time
            scratch_id = f"auto_{int(time.time() * 1000)}"
            file_path = self.scratch_dir / f"{scratch_id}.txt"
            
            file_path.write_text(content, encoding='utf-8')
            self.logger.info(f"Staged {len(content)} chars to {scratch_id}")
            return scratch_id
            
        except Exception as e:
            self.logger.error(f"Failed to stage content: {e}")
            return None

    def read_content(self, scratch_id: str) -> Optional[str]:
        """Retrieve content from a scratch file."""
        try:
            file_path = self.scratch_dir / f"{scratch_id}.txt"
            if file_path.exists():
                return file_path.read_text(encoding='utf-8')
            return None
        except Exception as e:
            self.logger.error(f"Failed to read scratch {scratch_id}: {e}")
            return None
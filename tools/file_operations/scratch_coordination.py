#!/usr/bin/env python3
"""
Scratch Coordination Utility

Provides safe coordination between file operation tools and the ScratchManager
without introducing circular dependencies or breaking existing contracts.
"""

import logging
from pathlib import Path
from typing import Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from agent.scratch_manager import ScratchManager

logger = logging.getLogger(__name__)


def get_scratch_manager() -> Optional["ScratchManager"]:
    """
    Safely retrieve a ScratchManager instance if available.

    Returns:
        Optional[ScratchManager]: ScratchManager instance or None if unavailable
    """
    try:
        # Import here to avoid circular dependencies
        from agent.scratch_manager import ScratchManager

        # Try to get the global instance if it exists
        # This is a safe way to check without breaking existing patterns
        return ScratchManager
    except ImportError:
        logger.debug("ScratchManager not available for import")
        return None
    except Exception as e:
        logger.debug(f"Error accessing ScratchManager: {e}")
        return None


def try_scratch_manager_stage(
    content: str, working_dir: Path, threshold: int = 1000
) -> Optional[str]:
    """
    Try to stage content using ScratchManager if available.

    Args:
        content: Content to stage
        working_dir: Working directory
        threshold: Character threshold for staging

    Returns:
        Optional[str]: scratch_id if successful, None if ScratchManager unavailable
    """
    try:
        # Get ScratchManager class (not instance - avoid instance management)
        scratch_manager_class = get_scratch_manager()
        if not scratch_manager_class:
            return None

        # Create temporary instance for this operation
        # This avoids global instance management issues
        scratch_manager = scratch_manager_class(working_dir)

        # Use the stage_content method
        scratch_id = scratch_manager.stage_content(content, threshold)

        if scratch_id:
            logger.info(f"Successfully staged content via ScratchManager: {scratch_id}")
            return scratch_id

    except Exception as e:
        logger.debug(f"ScratchManager staging failed: {e}")

    return None


def try_scratch_manager_read(scratch_id: str, working_dir: Path) -> Optional[str]:
    """
    Try to read scratch content using ScratchManager if available.

    Args:
        scratch_id: The ID of the scratch file to read
        working_dir: Working directory

    Returns:
        Optional[str]: Content if successful, None if ScratchManager unavailable
    """
    try:
        # Get ScratchManager class
        scratch_manager_class = get_scratch_manager()
        if not scratch_manager_class:
            return None

        # Create temporary instance for this operation
        scratch_manager = scratch_manager_class(working_dir)

        # Use the safe_read_content method to avoid exceptions
        content = scratch_manager.safe_read_content(scratch_id)

        if content is not None:
            logger.info(f"Successfully read scratch via ScratchManager: {scratch_id}")
            return content

    except Exception as e:
        logger.debug(f"ScratchManager reading failed: {e}")

    return None

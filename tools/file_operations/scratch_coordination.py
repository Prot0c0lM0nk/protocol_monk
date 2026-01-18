#!/usr/bin/env python3
"""
Scratch Coordination Utility
"""

import logging
from pathlib import Path
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    # Future-proofing: This will eventually live in utils
    from protocol_monk.utils.scratch import ScratchManager

logger = logging.getLogger(__name__)


def get_scratch_manager() -> Optional["ScratchManager"]:
    """Safely retrieve a ScratchManager instance if available."""
    try:
        # Import here to avoid circular dependencies
        # Updated to new path structure defined in 09_FILE_STRUCTURE
        from protocol_monk.utils.scratch import ScratchManager

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
    """Try to stage content using ScratchManager if available."""
    try:
        scratch_manager_class = get_scratch_manager()
        if not scratch_manager_class:
            return None

        # Create temporary instance
        scratch_manager = scratch_manager_class(working_dir)
        return scratch_manager.stage_content(content, threshold)

    except Exception as e:
        logger.debug(f"ScratchManager staging failed: {e}")

    return None


def try_scratch_manager_read(scratch_id: str, working_dir: Path) -> Optional[str]:
    """Try to read scratch content using ScratchManager if available."""
    try:
        scratch_manager_class = get_scratch_manager()
        if not scratch_manager_class:
            return None

        scratch_manager = scratch_manager_class(working_dir)
        content = scratch_manager.safe_read_content(scratch_id)

        if content is not None:
            logger.info(f"Successfully read scratch via ScratchManager: {scratch_id}")
            return content

    except Exception as e:
        logger.debug(f"ScratchManager reading failed: {e}")

    return None

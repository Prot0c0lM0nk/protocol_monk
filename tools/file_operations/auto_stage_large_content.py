#!/usr/bin/env python3
"""
Auto Stage Large Content Function
"""

import logging
import time
from pathlib import Path
from typing import Optional


def auto_stage_large_content(
    content: str, working_dir: Path, threshold: int = 1000
) -> Optional[str]:
    """
    Auto-stage large inline content to scratch file.

    Args:
        content: The text content to check/stage.
        working_dir: The agent's working directory.
        threshold: Character count threshold for staging.

    Returns:
        Optional[str]: scratch_id if staged, None otherwise.
    """
    logger = logging.getLogger(__name__)
    if not content or len(content) <= threshold:
        return None

    try:
        scratch_dir = working_dir / ".scratch"
        scratch_dir.mkdir(exist_ok=True)

        # Generate unique scratch ID
        # Use milliseconds for uniqueness
        scratch_id = f"auto_{int(time.time() * 1000)}"
        scratch_path = scratch_dir / f"{scratch_id}.txt"

        # Write to scratch
        scratch_path.write_text(content, encoding="utf-8")

        logger.info(
            "Auto-staged large content (%d chars) as '%s'",
            len(content),
            scratch_id,
        )
        return scratch_id
    except OSError as e:
        logger.error("Auto-staging failed: %s", e, exc_info=True)
        return None

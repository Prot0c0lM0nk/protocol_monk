#!/usr/bin/env python3
"""
Auto Stage Large Content Function
"""

import shutil
import tempfile

import logging
import os
import time
from pathlib import Path
from typing import Optional


def auto_stage_large_content(
    content: str, working_dir: Path, threshold: int = 1000
) -> Optional[str]:
    """
    Auto-stage large inline content to scratch file.
    Returns scratch_id if staged, None otherwise.
    """
    logger = logging.getLogger(__name__)
    if not content or len(content) <= threshold:
        return None

    try:
        scratch_dir = working_dir / ".scratch"
        scratch_dir.mkdir(exist_ok=True)

        # Generate unique scratch ID
        import time

        scratch_id = (
            f"auto_{int(time.time() * 1000)}"  # Use milliseconds for uniqueness
        )
        scratch_path = scratch_dir / f"{scratch_id}.txt"

        # Write to scratch
        scratch_path.write_text(content, encoding="utf-8")

        logger.info(
            f"Auto-staged large content ({len(content)} chars) as '{scratch_id}'"
        )
        return scratch_id
    except Exception as e:
        logger.error(f"Auto-staging failed: {e}", exc_info=True)
        return None

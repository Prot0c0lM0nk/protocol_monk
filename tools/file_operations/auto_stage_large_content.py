#!/usr/bin/env python3
"""
Auto Stage Large Content Function
"""

import logging
import time
from pathlib import Path
from typing import Optional

from protocol_monk.tools.file_operations.scratch_coordination import (
    try_scratch_manager_stage,
)


def auto_stage_large_content(
    content: str, working_dir: Path, threshold: int = 1000
) -> Optional[str]:
    """Auto-stage large inline content to scratch file."""
    logger = logging.getLogger(__name__)
    if not content or len(content) <= threshold:
        return None

    # Try ScratchManager first
    scratch_id = try_scratch_manager_stage(content, working_dir, threshold)
    if scratch_id:
        return scratch_id

    # Fallback to local logic
    try:
        scratch_dir = working_dir / ".scratch"
        scratch_dir.mkdir(exist_ok=True)

        scratch_id = f"auto_{int(time.time() * 1000)}"
        scratch_path = scratch_dir / f"{scratch_id}.txt"

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

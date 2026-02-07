"""
ui/textual/models/detail_record.py
Typed detail record for on-demand chat popups.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(slots=True)
class DetailRecord:
    """Stores full detail content for a compact chat bullet."""

    id: str
    kind: str
    title: str
    summary: str
    full_text: str
    syntax_hint: Optional[str] = None
    tool_name: Optional[str] = None
    created_at: Optional[datetime] = None

from pydantic import BaseModel
from typing import Optional

class ModelInfo(BaseModel):
    """Data class for model information."""
    name: str
    provider: str
    context_window: int
    hf_path: str

class SwitchReport(BaseModel):
    """Data class for model switch assessment report."""
    safe: bool
    current_tokens: int
    target_limit: int
    recommendation: str  # e.g., "SAFE", "PRUNE", "ARCHIVE"
    message: Optional[str] = None

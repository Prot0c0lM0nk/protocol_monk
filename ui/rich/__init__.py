"""
ui/rich - Rich CLI Package for Protocol Monk

Rich-themed UI with enhanced visual styling:
- renderer.py: View layer (Rich console operations with styles)
- input.py: Input abstraction (prompt_toolkit wrapper with Rich integration)
- interface.py: Controller layer (event orchestration, state machine)
"""

from .interface import RichUI


def create_rich_ui() -> RichUI:
    """Factory function to create RichUI instance"""
    return RichUI()

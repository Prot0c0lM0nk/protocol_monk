"""
ui/rich - Rich CLI Package for Protocol Monk

Rich-themed UI with enhanced visual styling:
- renderer.py: View layer (Rich console operations with styles)
- input_handler.py: Input layer (prompt_toolkit wrapper with Rich integration)
- interface.py: Controller layer (event orchestration, state machine)
"""

from .interface import RichUI


def create_rich_ui(event_bus=None) -> RichUI:
    """Factory function to create RichUI instance"""
    return RichUI(event_bus=event_bus)

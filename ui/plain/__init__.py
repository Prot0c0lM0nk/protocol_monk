"""
ui/plain - Plain CLI Package for Protocol Monk EDA

Refactored from ui/plain.py into MVC architecture:
- renderer.py: View layer (Rich console operations)
- input.py: Input abstraction (prompt_toolkit wrapper)
- interface.py: Controller layer (event orchestration, state machine)
"""

from .interface import PlainUI

def create_plain_ui() -> PlainUI:
    """Factory function to create PlainUI instance"""
    return PlainUI()
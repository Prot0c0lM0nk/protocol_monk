"""
PlainRenderer - Simple terminal output for PlainUI.
Colors can be added later.
"""

import sys
from typing import Dict, Any


class PlainRenderer:
    """
    Simple terminal output without complex formatting.
    Colors can be added later.
    """

    def __init__(self):
        self._last_was_stream = False

    def stream(self, text: str):
        """Write text directly to stdout (for LLM tokens)."""
        sys.stdout.write(text)
        sys.stdout.flush()
        self._last_was_stream = True

    def new_line(self):
        """Force a newline if we were just streaming."""
        if self._last_was_stream:
            sys.stdout.write("\n")
            sys.stdout.flush()
            self._last_was_stream = False

    def print_system(self, text: str):
        """System info message."""
        self.new_line()
        print(f"[SYSTEM] {text}")

    def print_error(self, text: str):
        """Error message."""
        self.new_line()
        print(f"[ERROR] {text}")

    def print_warning(self, text: str):
        """Warning message."""
        self.new_line()
        print(f"[WARN] {text}")

    def print_tool_call(self, tool_name: str, params: Dict[str, Any]):
        """Tool call display."""
        self.new_line()
        param_str = str(params)
        if len(param_str) > 150:
            param_str = param_str[:147] + "..."
        print(f"[TOOL CALL] {tool_name}({param_str})")

    def print_tool_result(self, tool_name: str, output: str):
        """Tool result display."""
        self.new_line()
        preview = output[:200] + "..." if len(output) > 200 else output
        print(f"[TOOL RESULT] {tool_name}: {preview}")



    def render_selection_list(self, title: str, items):
        """Render a simple selection list (1-based)."""
        self.new_line()
        print(f"\n{title}")
        print("-" * 40)
        
        for idx, item in enumerate(items, 1):
            if hasattr(item, "name"):
                name = getattr(item, "name", str(item))
                extra = ""
                if hasattr(item, "provider"):
                    extra = f" ({item.provider})"
                print(f"  [{idx}] {name}{extra}")
            else:
                print(f"  [{idx}] {item}")
        
        print("-" * 40)

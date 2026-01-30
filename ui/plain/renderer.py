import sys
from typing import Optional, Dict, Any

class PlainRenderer:
    """
    Handles formatting and writing to stdout/stderr.
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
        self.new_line()
        print(f"\033[94m[SYSTEM]\033[0m {text}")  # Blue text if terminal supports it, else mostly harmless

    def print_error(self, text: str):
        self.new_line()
        print(f"\033[91m[ERROR]\033[0m {text}")   # Red

    def print_warning(self, text: str):
        self.new_line()
        print(f"\033[93m[WARN]\033[0m {text}")    # Yellow

    def print_tool_call(self, tool_name: str, params: Dict[str, Any]):
        self.new_line()
        # Truncate params if they are huge for display purposes
        param_str = str(params)
        if len(param_str) > 150:
            param_str = param_str[:147] + "..."
        print(f"\033[95m[TOOL CALL]\033[0m {tool_name}({param_str})") # Magenta

    def print_tool_result(self, tool_name: str, output: str):
        self.new_line()
        preview = output[:200] + "..." if len(output) > 200 else output
        print(f"\033[92m[TOOL RESULT]\033[0m {tool_name}: {preview}") # Green
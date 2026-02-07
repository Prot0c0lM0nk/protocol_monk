"""
ui/textual/widgets/spinners.py
Animated spinners and progress indicators for the Textual TUI.
"""

from textual.widgets import Static
from textual.reactive import reactive
import itertools
import time


class Spinner(Static):
    """
    Animated spinner widget for Textual.
    
    Provides multiple spinner styles:
    - dots: ⠋ ⠙ ⠹ ⠸ ⠼ ⠴ ⠦ ⠧ ⠇ ⠏
    - bars: ▁ ▂ ▃ ▄ ▅ ▆ ▇ █ ▇ ▆ ▅ ▄ ▃ ▁
    - clock: 🕒 🕓 🕔 🕕 🕖 🕗 🕘 🕙 🕚 🕛 🕜 🕛
    - arrows: ← ↑ → ↓
    - globe: 🌍 🌎 🌏 🌐
    """
    
    # Spinner frames for each style
    SPINNERS = {
        "dots": ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"],
        "dots_quiet": ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴"],
        "bars": ["▁", "▂", "▃", "▄", "▅", "▆", "▇", "█", "▇", "▆", "▅", "▄", "▃", "▂"],
        "clock": ["🕒", "🕒", "🕒", "🕓", "🕓", "🕓", "🕔", "🕔", "🕔", "🕒", "🕒", "🕒"],
        "arrows": ["←", "↖", "↑", "↗", "→", "↘", "↓", "↙"],
        "globe": ["🌍", "🌎", "🌏", "🌐"],
        "moon": ["🌑", "🌒", "🌓", "🌔", "🌕", "🌖", "🌗", "🌘"],
        "line": ["|", "/", "-", "\\"],
        "flip": ["_", "_", "-", "-", "=", "=", "≈", "≈", "~", "≈", "=", "=", "-", "-", "_", "_"],
        "pong": ["▐", "▌", "▐", "▌", "█", "█", "█", "█"],
        "bouncing_bar": ["□", "◱", "◧", "◨", "◩", "◸", "◹", "◺"],
    }
    
    # Reactive attributes
    active = reactive(False)
    spinner_style = reactive("dots")
    text = reactive("Processing...")
    
    def __init__(
        self, 
        text: str = "Processing...", 
        style: str = "dots",
        speed: float = 0.1,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.text = text
        self.spinner_style = style
        self.speed = speed
        self._frames = self.SPINNERS.get(style, self.SPINNERS["dots"])
        self._frame_index = 0
        self._last_update = 0
        self._task = None
        self._active = False
    
    def on_mount(self) -> None:
        """Start the spinner animation when mounted."""
        self.start()
    
    def start(self) -> None:
        """Start the spinner animation."""
        if self._active:
            return
        self._active = True
        self._last_update = time.time()
        self._task = self.app.call_later(self.speed, self._animate)
    
    def stop(self) -> None:
        """Stop the spinner animation."""
        self._active = False
        if self._task:
            self._task.cancel()
            self._task = None
        self.update(f"  {self.text}")
    
    def _animate(self) -> None:
        """Update the spinner frame."""
        if not self._active:
            return
        
        current_time = time.time()
        if current_time - self._last_update >= self.speed:
            self._frame_index = (self._frame_index + 1) % len(self._frames)
            frame = self._frames[self._frame_index]
            self.update(f"  {frame} {self.text}")
            self._last_update = current_time
        
        self._task = self.app.call_later(self.speed, self._animate)
    
    def watch_active(self, new_value: bool) -> None:
        """React to active state changes."""
        if new_value:
            self.start()
        else:
            self.stop()
    
    def watch_spinner_style(self, new_value: str) -> None:
        """Update spinner frames when style changes."""
        self._frames = self.SPINNERS.get(new_value, self.SPINNERS["dots"])
        self._frame_index = 0
        if self._active:
            self.update(f"  {self._frames[0]} {self.text}")
    
    def watch_text(self, new_value: str) -> None:
        """Update text when it changes."""
        self.text = new_value
        if self._active:
            frame = self._frames[self._frame_index] if self._frames else "•"
            self.update(f"  {frame} {self.text}")


class ProgressBar(Static):
    """
    Progress bar widget for Textual.
    
    Shows visual progress for multi-step operations.
    """
    
    progress = reactive(0.0)
    label = reactive("Processing...")
    show_percentage = reactive(True)
    
    def __init__(
        self, 
        label: str = "Processing...", 
        show_percentage: bool = True,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.label = label
        self.show_percentage = show_percentage
        self.progress = 0.0
    
    def on_mount(self) -> None:
        """Initial render."""
        self._render_bar()
    
    def update_progress(self, value: float, label: str = None) -> None:
        """Update progress and optionally label."""
        self.progress = max(0.0, min(1.0, value))
        if label:
            self.label = label
        self._render_bar()
    
    def _render_bar(self) -> None:
        """Render the progress bar."""
        # Calculate bar length (20 characters)
        bar_length = 20
        filled = int(self.progress * bar_length)
        empty = bar_length - filled
        
        # Build bar
        bar = "█" * filled + "░" * empty
        
        # Build label with percentage
        if self.show_percentage:
            percentage = int(self.progress * 100)
            text = f"{self.label} [{percentage:3d}%]"
        else:
            text = self.label
        
        # Update widget
        self.update(f"  {text}\n  [{bar}]")


class ThinkingIndicator(Static):
    """
    Enhanced thinking indicator with spinner and status text.
    
    Shows:
    - Animated spinner
    - Status text ("Thinking...", "Processing tool...", etc.)
    - Optional sub-status ("Reading file...", "Running command...")
    """
    
    status = reactive("Thinking...")
    sub_status = reactive("")
    spinner_style = reactive("dots")
    
    def __init__(
        self,
        status: str = "Thinking...",
        sub_status: str = "",
        spinner_style: str = "dots",
        **kwargs
    ):
        super().__init__(**kwargs)
        self.status = status
        self.sub_status = sub_status
        self.spinner_style = spinner_style
        self._spinner = Spinner(
            text=status,
            style=spinner_style,
            speed=0.15
        )
        self._sub_status = Static(f"  {sub_status}", classes="sub-status")
    
    def compose(self):
        """Compose the thinking indicator."""
        yield self._spinner
        if self.sub_status:
            yield self._sub_status
    
    def update_status(self, status: str, sub_status: str = "") -> None:
        """Update status and optional sub-status."""
        self.status = status
        self.sub_status = sub_status
        self._spinner.text = status
        self._sub_status.update(f"  {sub_status}")
    
    def start(self) -> None:
        """Start the spinner."""
        self._spinner.start()
    
    def stop(self) -> None:
        """Stop the spinner."""
        self._spinner.stop()
        self.update(f"  ✓ {self.status}")


class ExecutionProgress(Static):
    """
    Tool execution progress tracker.
    
    Shows:
    - Current tool name
    - Progress (X/Y tools)
    - Optional spinner per tool
    """
    
    current = reactive(0)
    total = reactive(0)
    tool_name = reactive("")
    spinner_style = reactive("bars")
    
    def __init__(
        self,
        total: int = 0,
        tool_name: str = "",
        spinner_style: str = "bars",
        **kwargs
    ):
        super().__init__(**kwargs)
        self.total = total
        self.current = 0
        self.tool_name = tool_name
        self.spinner_style = spinner_style
        self._spinner = Spinner(
            text=f"Executing {tool_name}...",
            style=spinner_style,
            speed=0.1
        )
    
    def compose(self):
        """Compose the execution progress."""
        yield self._spinner
        yield Static(f"  Tool {self.current}/{self.total}", classes="tool-counter")
    
    def update_tool(self, current: int, total: int, tool_name: str) -> None:
        """Update tool progress."""
        self.current = current
        self.total = total
        self.tool_name = tool_name
        self._spinner.text = f"Executing {tool_name}..."
        self._spinner.update(f"  {self._spinner._frames[0]} Executing {tool_name}...")
        self.query_one(".tool-counter").update(f"  Tool {current}/{total}")
    
    def start(self) -> None:
        """Start the spinner."""
        self._spinner.start()
    
    def stop(self) -> None:
        """Stop the spinner."""
        self._spinner.stop()

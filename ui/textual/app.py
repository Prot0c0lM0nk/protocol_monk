from textual import on, work
from textual.app import App
from textual.binding import Binding
from textual.containers import Container
from textual.screen import Screen
from textual.widgets import Header, Footer, Label

from agent.monk import ProtocolAgent
from ui.textual.interface import TextualUI
from ui.textual.screens.approval import ApprovalScreen
from ui.textual.screens.chat import ChatScreen

# Define the greeting banner for Textual UI
TEXTUAL_GREETING = """☦ P R O T O C O L   M O N K ☦

"The Protocol is a path. A discipline.
A way of seeing code not as chaos,
but as sacred geometry waiting to be understood."

Type /help for guidance.
Type /quit to return to the desert of the real.
"""


class MonkCodeTUI(App):
    """Main application for Textual TUI."""

    # CSS_PATH = "styles.tcss"  # Disabled - using programmatic styling instead
    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit"),
        Binding("ctrl+c", "quit", "Quit"),
    ]
    SCREENS = {
        "chat": ChatScreen,
        "approval": ApprovalScreen,
    }

    def __init__(self, agent: ProtocolAgent):
        super().__init__()
        self.agent = agent
        self.ui = None
        self.chat_screen = None

    def compose(self):
        """Compose the main application layout."""
        yield Header()
        yield Container(id="main-container")
        yield Footer()

    async def on_mount(self):
        """Initialize the UI and push the main screen."""
        try:
            # Apply programmatic styling first
            await self._apply_programmatic_styles()

            # Create the Textual UI bridge
            self.ui = TextualUI(self)

            # Inject UI into agent
            self.agent.ui = self.ui

            # Push the main chat screen
            self.chat_screen = ChatScreen()
            await self.push_screen(self.chat_screen)

            # Display startup banner
            await self.ui.display_startup_banner(TEXTUAL_GREETING)

            # Update footer with key bindings
            self.query_one(Footer).text = "Ctrl+Q to quit | Type /help for guidance"

        except Exception as e:
            # Handle initialization errors gracefully
            error_container = self.query_one("#main-container")
            await error_container.mount(
                Label(f"Failed to initialize: {str(e)}", id="error-label")
            )
            self.log(f"Initialization error: {e}")

    def _apply_programmatic_styles(self):
        """Apply Orthodox Matrix theme styling programmatically to avoid CSS parsing issues."""
        try:
            # Color definitions based on Rich theme
            primary = "#00ff00"  # Matrix Green
            secondary = "#9370db"  # Medium Purple
            accent = "#ffaa44"  # Orthodox Gold
            tech = "#00d7ff"  # Machine Blue
            success = "#44ff44"  # Bright Green
            error_color = "#dc143c"  # Crimson
            surface = "#1a1a1a"  # Dark background
            panel = "#2d2d2d"  # Panel background
            text = "#e8e8e8"  # Light text
            text_muted = "#a0a0a0"  # Dimmed text

            # Apply styles to the app screen
            self.screen.styles.background = surface
            self.screen.styles.color = text

        except Exception as e:
            self.log(f"Error applying programmatic styles: {e}")
            # Continue anyway - styling is nice but not critical
            error_container = self.query_one("#main-container")
            error_container.mount(
                Label(f"Failed to initialize: {str(e)}", id="error-label")
            )
            self.log(f"Initialization error: {e}")

    @work(thread=True)
    async def action_quit(self):
        """Handle application quit with proper cleanup."""
        try:
            if self.ui:
                self.ui = None
            if self.agent:
                await self.agent.close()
        except Exception as e:
            self.log(f"Error during quit: {e}")
        finally:
            self.exit()

    def on_unmount(self):
        """Clean up resources on unmount."""
        try:
            if self.ui:
                self.ui = None
            if self.agent:
                # Note: agent.close() should be async, but we handle it in action_quit
                pass
        except Exception as e:
            self.log(f"Error during unmount: {e}")

    async def push_screen_wait(self, screen: Screen, wait_for_dismiss=True):
        """Push a screen and wait for dismissal if requested."""
        if wait_for_dismiss:
            return await self.push_screen_wait(screen)
        else:
            await self.push_screen(screen)
            return None

    def notify_status(self, message: str):
        """Update status in the footer or status bar."""
        footer = self.query_one(Footer)
        if footer:
            # Keep essential info but append status
            base_text = "Ctrl+Q to quit | "
            footer.text = base_text + message


"""--- End of app.py ---

**Key Changes Made:**

1. **Added proper Textual imports**: `Header`, `Footer`, `Binding`, `work` decorator
2. **Implemented `compose()` method**: Now properly structures the app with Header, main container, and Footer
3. **Added global key bindings**: Ctrl+Q and Ctrl+C for quitting
4. **Enhanced error handling**: Graceful handling of initialization errors
5. **Proper worker usage**: `action_quit` now uses `@work` for async cleanup
6. **Better lifecycle management**: Added `on_unmount` for cleanup
7. **Status notifications**: Added `notify_status` method for footer updates
8. **Screen management**: Added `push_screen_wait` helper for modal screens

The refactored version now properly follows Textual's architecture with proper widget composition, error handling, and lifecycle management.

Please upload the next file from the plan: `ui/textual/interface.py` so I can continue with the refactoring.
"""

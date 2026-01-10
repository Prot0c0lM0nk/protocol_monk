from textual.app import App, SystemCommand
from textual.command import Provider, Hit, DiscoveryHit
from textual.screen import Screen
from ui.textual.screens import ChatScreen
from ui.textual.interface import TextualUI
from functools import partial

# --- NEW: Define the Command Provider ---
class AgentCommandProvider(Provider):
    """Provides the agent's slash commands to the palette."""
    
    async def search(self, query: str):
        matcher = self.matcher(query)
        
        # These match the commands in your agent/command_dispatcher.py
        commands = [
            ("/clear", "Clear context history", "action_clear_chat"),
            ("/quit", "Exit application", "action_quit"),
            ("/help", "Show help message", "action_help"),
            ("/model", "Switch model", "action_switch_model"),
        ]

        for name, description, action_name in commands:
            score = matcher.match(name)
            if score > 0:
                # We use a lambda/partial to send the text input directly
                yield Hit(
                    score,
                    matcher.highlight(name),
                    partial(self.app.handle_user_input, name),
                    help=description,
                )

    async def discover(self):
        """Show these commands by default when palette opens."""
        for name, description, _ in [("/clear", "Clear history", ""), ("/quit", "Exit", "")]:
            yield DiscoveryHit(
                name,
                partial(self.app.handle_user_input, name),
                help=description
            )

class ProtocolMonkApp(App):
    """
    Main Textual Application for Protocol Monk.
    """

    CSS_PATH = "styles.tcss"
    BINDINGS = [
        ("ctrl+q", "quit", "Quit"),
        ("ctrl+d", "toggle_dark", "Toggle Dark Mode"),
    ]
    
    # --- NEW: Register the Provider ---
    COMMANDS = App.COMMANDS | {AgentCommandProvider}

    # We will inject the controller (TextualUI) after instantiation
    controller: "TextualUI" = None

    def on_mount(self) -> None:
        self.push_screen(ChatScreen())

    def handle_user_input(self, text: str) -> None:
        if self.controller:
            self.controller.input_queue.put_nowait(text)
        else:
            self.notify("Error: Controller not connected", severity="error")

    def action_toggle_dark(self) -> None:
        self.dark = not self.dark
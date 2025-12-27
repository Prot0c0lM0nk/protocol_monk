"""
ui/textual/commands.py
Adapts Protocol Monk commands for the Textual Command Palette.
"""
from textual.command import Provider, Hit
from textual.app import App

class MonkCommandProvider(Provider):
    """
    Exposes slash commands to the Command Palette (Ctrl+P).
    """
    
    async def search(self, query: str):
        matcher = self.matcher(query)
        
        # Map friendly names to the actual slash commands
        # The key is what the user types/sees in the palette
        commands = {
            "Switch AI Model": "/model",
            "Switch Provider": "/provider",
            "Clear History": "/clear",
            "System Status": "/status",
            "Upload File": "/file",
            "Help": "/help",
            "Quit Application": "/quit"
        }

        for name, slash_cmd in commands.items():
            # Match against the friendly name (e.g. "Switch")
            score = matcher.match(name)
            
            if score > 0:
                yield Hit(
                    score,
                    matcher.highlight(name),
                    # The callback runs when selected.
                    # We pass the slash command string back to the App.
                    lambda c=slash_cmd: self.app.trigger_slash_command(c),
                    help=f"Run {slash_cmd}"
                )
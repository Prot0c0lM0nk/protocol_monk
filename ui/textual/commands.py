# ui/textual/commands.py
from textual.command import Provider, Hit, Hits

class ProtocolMonkProvider(Provider):
    """Command provider for Protocol Monk"""
    
    async def search(self, query: str) -> Hits:
        """Search for commands."""
        # Placeholder for now
        matcher = self.matcher(query)
        commands = [
            ("Model: Switch", "Switch the active AI model"),
            ("Provider: Switch", "Switch the backend provider"),
            ("Context: Clear", "Clear the conversation history"),
        ]

        for command, help_text in commands:
            score = matcher.match(command)
            if score > 0:
                yield Hit(
                    score=score,
                    value=matcher.highlight(command),
                    callback=lambda: self.app.notify(f"Executed: {command}"),
                    help=help_text
                )
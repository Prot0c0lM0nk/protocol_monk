"""Run the Textual MVP against a local mock agent."""

from protocol_monk.protocol.bus import EventBus
from protocol_monk.ui.textual.app import ProtocolMonkTextualApp
from protocol_monk.ui.textual.bridge import TextualEventBridge
from protocol_monk.ui.textual.mock_agent import MockAgentService


def run() -> None:
    bus = EventBus()
    mock_agent = MockAgentService(bus)
    app = ProtocolMonkTextualApp(bus=bus)
    bridge = TextualEventBridge(app=app, bus=bus)

    app.mock_agent = mock_agent
    app.bridge = bridge
    app.run()


if __name__ == "__main__":
    run()

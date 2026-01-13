# tui_runner.py
import sys
from pathlib import Path

# Add project root to path so imports work
sys.path.insert(0, str(Path(__file__).parent))

from ui.textual.app import ProtocolMonkApp
from agent.events import get_event_bus
from agent.mock_event_agent import MockEventAgent

def create_dev_app():
    """
    Factory function for 'textual run'.
    Sets up the App with a Mock Agent for UI development.
    """
    # 1. Setup the Event Bus and Mock Agent
    event_bus = get_event_bus()
    agent = MockEventAgent(event_bus)
    
    # 2. Create the App
    app = ProtocolMonkApp()
    
    # 3. Inject the Agent (This uses the method we just added)
    app.set_agent(agent)
    
    return app

# Expose the app variable for Textual to find
app = create_dev_app()

if __name__ == "__main__":
    app.run()
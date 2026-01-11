"""
ui_playground.py
Standalone runner for Protocol Monk TUI.
Mocks the backend so we can polish the UI without 'main.py' interference.
"""
import sys
import asyncio
from typing import Dict, Any
from unittest.mock import MagicMock

# --- 1. MOCK THE BACKEND DEPENDENCIES ---
# We must do this BEFORE importing the UI app

# Mock Event Bus
mock_bus = MagicMock()

# Mock AgentEvents Enum
class MockEnum:
    def __init__(self, value): self.value = value
    
class MockAgentEvents:
    STREAM_CHUNK = MockEnum("stream_chunk")
    RESPONSE_COMPLETE = MockEnum("response_complete")
    TOOL_RESULT = MockEnum("tool_result")
    ERROR = MockEnum("error")
    WARNING = MockEnum("warning")
    INFO = MockEnum("info")
    THINKING_STARTED = MockEnum("thinking_started")
    THINKING_STOPPED = MockEnum("thinking_stopped")
    TOOL_CONFIRMATION_REQUESTED = MockEnum("tool_confirmation_requested")

# Inject Mocks into sys.modules
mock_events_module = MagicMock()
mock_events_module.get_event_bus.return_value = mock_bus
mock_events_module.AgentEvents = MockAgentEvents
sys.modules["agent.events"] = mock_events_module

# --- 2. IMPORT THE APP ---
# Now it's safe to import, it will use our mocks
from ui.textual.app import TextualUI

# --- 3. DUMMY AGENT ---
class DummyAgent:
    """A fake agent that just echoes text back to test the UI"""
    def __init__(self, ui_app):
        self.ui_app = ui_app

    async def process_request(self, user_input: str):
        # Simulate Network Delay
        await self.ui_app.start_thinking()
        await asyncio.sleep(1.0)
        await self.ui_app.stop_thinking()

        # Simulate Streaming Response
        response = f"Echoing your input: {user_input}"
        for char in response:
            await asyncio.sleep(0.05) # Typewriter effect
            # Manually trigger the event handler in the UI
            await self.ui_app._on_stream_chunk({"chunk": char})
        
        # Finish
        await self.ui_app._on_response_complete({})

# --- 4. RUNNER ---
if __name__ == "__main__":
    # Instantiate App
    app = TextualUI()
    
    # Attach Dummy Agent
    dummy_agent = DummyAgent(app)
    app.set_agent(dummy_agent)
    
    # Run
    app.run()
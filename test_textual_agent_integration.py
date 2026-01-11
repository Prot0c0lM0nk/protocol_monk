#!/usr/bin/env python3
"""
Test Textual UI with agent integration (simulating main.py)
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ui.textual.app import TextualUI


async def test_agent_integration():
    """Test that TextualUI can be initialized with agent"""
    print("Testing Textual UI with agent integration...")

    # Create TextualUI instance
    ui = TextualUI()

    # Verify it has the required methods
    assert hasattr(ui, 'get_input'), "Missing get_input method"
    assert hasattr(ui, 'confirm_tool_execution'), "Missing confirm_tool_execution method"
    assert hasattr(ui, 'print_stream'), "Missing print_stream method"
    assert hasattr(ui, 'print_error'), "Missing print_error method"
    assert hasattr(ui, 'print_info'), "Missing print_info method"
    assert hasattr(ui, 'start_thinking'), "Missing start_thinking method"
    assert hasattr(ui, 'stop_thinking'), "Missing stop_thinking method"
    assert hasattr(ui, 'run_async'), "Missing run_async method"
    assert hasattr(ui, 'set_agent'), "Missing set_agent method"

    # Verify event bus is connected
    assert ui._event_bus is not None, "Event bus not connected"

    print("✓ TextualUI initialized successfully")
    print("✓ All UI interface methods present")
    print("✓ Event bus connected")

    # Test setting agent (mock)
    class MockAgent:
        async def process_request(self, user_input):
            pass

    ui.set_agent(MockAgent())
    assert ui._agent is not None, "Agent not set"

    print("✓ Agent can be set")
    print("\nAll tests passed! TextualUI is ready for agent integration.")


if __name__ == "__main__":
    asyncio.run(test_agent_integration())
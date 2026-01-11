#!/usr/bin/env python3
"""
Test agent event bus integration with Textual UI
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.events import get_event_bus, AgentEvents


async def test_event_bus():
    """Test that event bus works and UI can subscribe"""
    event_bus = get_event_bus()

    received_events = []

    async def on_stream_chunk(data):
        received_events.append(("stream_chunk", data))

    async def on_tool_result(data):
        received_events.append(("tool_result", data))

    # Subscribe to events
    event_bus.subscribe(AgentEvents.STREAM_CHUNK.value, on_stream_chunk)
    event_bus.subscribe(AgentEvents.TOOL_RESULT.value, on_tool_result)

    # Emit test events
    await event_bus.emit(AgentEvents.STREAM_CHUNK.value, {"chunk": "Hello"})
    await event_bus.emit(AgentEvents.TOOL_RESULT.value, {"tool_name": "test", "result": "OK"})

    # Wait a bit for processing
    await asyncio.sleep(0.1)

    # Verify events received
    assert len(received_events) == 2
    assert received_events[0][0] == "stream_chunk"
    assert received_events[0][1]["chunk"] == "Hello"
    assert received_events[1][0] == "tool_result"
    assert received_events[1][1]["tool_name"] == "test"

    print("✓ Event bus integration working correctly")
    print(f"  - Received {len(received_events)} events")
    print(f"  - Stream chunk: {received_events[0][1]}")
    print(f"  - Tool result: {received_events[1][1]}")


if __name__ == "__main__":
    asyncio.run(test_event_bus())
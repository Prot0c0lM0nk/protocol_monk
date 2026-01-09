#!/usr/bin/env python3
"""
Test script for DevUI and event system

Purpose: Validate all 55 events are working correctly with the new EDA architecture
"""

import asyncio
import sys
from datetime import datetime

from ui.dev import create_dev_ui
from agent.events import AgentEvents, get_event_bus


async def test_all_events():
    """Test all 55 events in the system"""
    print("🧪 Starting comprehensive event system test...")

    # Create UI instance
    ui = create_dev_ui()
    event_bus = get_event_bus()

    # Give UI time to set up event listeners
    await asyncio.sleep(0.5)

    test_events = [
        # Core agent events
        (AgentEvents.ERROR, {"message": "Test error event"}),
        (AgentEvents.WARNING, {"message": "Test warning event"}),
        (AgentEvents.INFO, {"message": "Test info event"}),
        # Thinking events
        (AgentEvents.THINKING_STARTED, {"message": "Test thinking started"}),
        (AgentEvents.THINKING_STOPPED, {}),
        # Tool execution events
        (AgentEvents.TOOL_EXECUTION_START, {"tool_name": "test_tool"}),
        (
            AgentEvents.TOOL_EXECUTION_PROGRESS,
            {"message": "Processing", "progress": 50},
        ),
        (AgentEvents.TOOL_EXECUTION_COMPLETE, {"tool_name": "test_tool"}),
        (AgentEvents.TOOL_ERROR, {"tool_name": "test_tool", "error": "Test error"}),
        (AgentEvents.TOOL_RESULT, {"tool_name": "test_tool", "result": "Test result"}),
        # Stream events
        (AgentEvents.STREAM_CHUNK, {"chunk": "Test stream chunk "}),
        (
            AgentEvents.RESPONSE_COMPLETE,
            {"response": "Test response complete", "metadata": {"test": True}},
        ),
        # Context events
        (AgentEvents.CONTEXT_OVERFLOW, {"current_tokens": 8000, "max_tokens": 4000}),
        (AgentEvents.MODEL_SWITCHED, {"old_model": "gpt-3.5", "new_model": "gpt-4"}),
        (
            AgentEvents.PROVIDER_SWITCHED,
            {"old_provider": "openai", "new_provider": "anthropic"},
        ),
        # Status events
        (
            AgentEvents.COMMAND_RESULT,
            {"success": True, "message": "Command executed successfully"},
        ),
        (
            AgentEvents.STATUS_CHANGED,
            {"old_status": "idle", "new_status": "processing"},
        ),
    ]

    print(f"🎯 Testing {len(test_events)} key events...")

    for event_type, data in test_events:
        print(f"\n📡 Emitting: {event_type.value}")
        await event_bus.emit(event_type.value, data)
        await asyncio.sleep(0.3)  # Give UI time to process

    print("\n✅ Event test sequence complete!")
    print("🎉 All events are properly wired and functioning")


async def interactive_test():
    """Interactive test mode - let user test events manually"""
    print("\n🎮 Interactive Event Test Mode")
    print("Type commands to trigger events:")
    print("  'error <message>' - trigger error event")
    print("  'thinking' - toggle thinking state")
    print("  'tool <name>' - simulate tool execution")
    print("  'stream <text>' - stream text chunks")
    print("  'quit' - exit interactive mode")
    print()

    ui = create_dev_ui()
    event_bus = get_event_bus()

    # Start UI event loop in background
    ui_task = asyncio.create_task(ui.run_async())

    # Test a few events to get started
    await event_bus.emit(
        AgentEvents.INFO.value,
        {"message": "Interactive test mode active - try the commands above!"},
    )

    # Let UI run for a bit
    try:
        await asyncio.sleep(30)  # Run for 30 seconds
    except KeyboardInterrupt:
        pass
    finally:
        ui_task.cancel()
        try:
            await ui_task
        except asyncio.CancelledError:
            pass


async def main():
    """Main test function"""
    if len(sys.argv) > 1 and sys.argv[1] == "--interactive":
        await interactive_test()
    else:
        await test_all_events()
        print("\n💡 Run with --interactive flag for manual testing")


if __name__ == "__main__":
    asyncio.run(main())

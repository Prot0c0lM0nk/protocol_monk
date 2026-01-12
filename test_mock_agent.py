#!/usr/bin/env python3
"""
Quick test script to verify MockEventAgent emits all events including slash commands.
"""

import asyncio
from agent.events import get_event_bus, AgentEvents
from agent.mock_event_agent import MockEventAgent


async def test_mock_agent():
    """Test the mock agent and count all events emitted."""
    print("=" * 70)
    print("TESTING MOCK EVENT AGENT")
    print("=" * 70)

    event_bus = get_event_bus()
    event_counts = {}

    # Track all events
    def track_event(data):
        event_type = data.get("_event_type", "unknown")
        event_counts[event_type] = event_counts.get(event_type, 0) + 1
        print(f"  ✓ {event_type}")

    # Subscribe to all event types
    for event in AgentEvents:
        event_bus.subscribe(event.value, lambda d, e=event.value: track_event({**d, "_event_type": e}))

    # Create and run mock agent
    agent = MockEventAgent(event_bus)

    print("\n[TEST] Running full event sequence...")
    print("-" * 70)
    await agent.emit_all_events()

    print("\n" + "=" * 70)
    print("EVENT SUMMARY")
    print("=" * 70)
    print(f"\nTotal unique event types emitted: {len(event_counts)}")
    print(f"Total events emitted: {sum(event_counts.values())}")

    print("\nEvent breakdown:")
    for event_type, count in sorted(event_counts.items()):
        print(f"  {event_type}: {count}")

    print("\n" + "=" * 70)
    print(f"Expected event types in AgentEvents: {len(AgentEvents)}")
    print(f"Actual event types emitted: {len(event_counts)}")

    if len(event_counts) == len(AgentEvents):
        print("\n✅ SUCCESS: All event types were emitted!")
    else:
        print("\n⚠️  WARNING: Some event types may be missing")
        missing = set(e.value for e in AgentEvents) - set(event_counts.keys())
        if missing:
            print(f"Missing: {missing}")

    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(test_mock_agent())
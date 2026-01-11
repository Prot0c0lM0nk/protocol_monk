#!/usr/bin/env python3
"""
Quick test of TextualUI with actual agent
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ui.textual.app import TextualUI


async def test():
    """Test TextualUI with agent"""
    print("Creating TextualUI...")
    ui = TextualUI()
    
    # Mock agent
    class MockAgent:
        async def process_request(self, user_input):
            print(f"Agent received: {user_input}")
    
    ui.set_agent(MockAgent())
    print("✓ Agent set")
    
    # Try to run the UI briefly
    print("Attempting to run UI...")
    try:
        # We'll create a task to run it and cancel it after 1 second
        task = asyncio.create_task(ui.run_async())
        await asyncio.sleep(1)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        print("✓ UI ran successfully (cancelled after 1s)")
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True


if __name__ == "__main__":
    result = asyncio.run(test())
    if result:
        print("\n✓ All tests passed!")
    else:
        print("\n✗ Tests failed")
        sys.exit(1)
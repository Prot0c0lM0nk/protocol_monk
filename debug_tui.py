#!/usr/bin/env python3
"""
Debug Textual TUI - Test minimal connection
"""

import asyncio
import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from ui.textual.app import ProtocolMonkApp
from agent.mock_event_agent import MockEventAgent
from agent.events import get_event_bus


async def debug_test():
    """Test the TUI connection with debugging"""
    print("=== TEXTUAL TUI DEBUG TEST ===")
    
    try:
        # Create event bus and mock agent
        print("1. Creating event bus and mock agent...")
        event_bus = get_event_bus()
        mock_agent = MockEventAgent(event_bus)
        print(f"   Event bus: {event_bus}")
        print(f"   Mock agent: {mock_agent}")
        
        # Create app
        print("2. Creating ProtocolMonkApp...")
        app = ProtocolMonkApp()
        print(f"   App created: {app}")
        
        # Connect agent
        print("3. Connecting agent to app...")
        app.set_agent(mock_agent)
        print(f"   UI bridge: {app.textual_ui}")
        print(f"   Agent connected: {hasattr(app, 'agent') and app.agent is not None}")
        
        # Test input handling
        print("4. Testing input handling...")
        try:
            app.call_from_child_submit("Hello test")
            print("   Input submission successful")
        except Exception as e:
            print(f"   Input submission failed: {e}")
            import traceback
            traceback.print_exc()
        
        print("5. Debug test complete")
        
    except Exception as e:
        print(f"Debug test failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(debug_test())
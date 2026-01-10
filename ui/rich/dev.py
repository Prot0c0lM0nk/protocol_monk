"""
ui/rich/dev.py
Visual Audit Tool for the Orthodox Matrix Theme.
Run this to verify colors/animations without loading the full Agent.
"""

import asyncio
from agent.events import AgentEvents, get_event_bus
from ui.rich.interface import RichUI
from ui.base import ToolResult


async def run_visual_audit():
    # 1. Setup
    print("Initializing RichUI for Visual Audit...")
    bus = get_event_bus()

    ui = RichUI()

    # 2. Test: Thinking Spinner (Look for Purple/Gold)
    print("\n--- TEST 1: THINKING ---")
    await bus.emit(AgentEvents.THINKING_STARTED.value, {})
    await asyncio.sleep(2.5)
    await bus.emit(AgentEvents.THINKING_STOPPED.value, {})

    # 3. Test: Streaming Text (Look for Chartreuse Green)
    print("\n--- TEST 2: STREAMING ---")
    msg = "The **Matrix** is a system, Neo. That system is our [i]enemy[/i]."
    for word in msg.split():
        await bus.emit(AgentEvents.STREAM_CHUNK.value, {"chunk": word + " "})
        await asyncio.sleep(0.15)
    await bus.emit(AgentEvents.RESPONSE_COMPLETE.value, {})

    # 4. Test: Tool Confirmation (Look for Turquoise/Grey)
    print("\n--- TEST 3: TOOL CONFIRMATION ---")
    print("(Please type 'y' or 'n' when prompted to test the input color)")

    tool_data = {
        "tool_name": "list_files",
        "parameters": {
            "path": "./secret_bunker",
            "recursive": True,
            "complex_logic": "def hack_matrix():\n    return 'Access Granted'",
        },
    }
    await ui.confirm_tool_execution(tool_data)

    # 5. Test: Tool Result (Look for Green/Red panels)
    print("\n--- TEST 4: TOOL RESULT ---")
    res = ToolResult(
        success=True,
        output="File list retrieved.\nFound: agent.py",
        tool_name="list_files",
    )
    await bus.emit(
        AgentEvents.TOOL_RESULT.value, {"tool_name": "list_files", "result": res}
    )

    print("\n--- AUDIT COMPLETE ---")


if __name__ == "__main__":
    asyncio.run(run_visual_audit())

"""
Example integration of async input system with Protocol Monk.

This demonstrates how to use the new async input system to replace
blocking input calls in the agent.
"""

import asyncio
import sys
from typing import Optional

# Import the async main loop
from agent.async_main_loop import run_async_main_loop, create_main_loop
from agent.monk import ProtocolAgent
from ui.async_input_manager import AsyncInputManager
from events.base import get_event_bus

# Import UI-specific async input implementations
from ui.plain.async_input import PlainAsyncInputWithHistory, PlainUIAsyncAdapter
from ui.rich.async_input import RichAsyncInputWithPromptToolkit, RichUIAsyncAdapter
from ui.textual.async_input import TextualAsyncInput, TextualUIAsyncAdapter


async def run_with_async_input(
    model_name: str = None, provider: str = None, ui_type: str = "plain"
):
    """
    Run Protocol Monk with async input system.

    Args:
        model_name: The model to use (e.g., "claude-3-5-sonnet-20241022")
        provider: The provider (e.g., "anthropic", "ollama")
        ui_type: The UI type ("plain", "rich", "textual")
    """
    print(f"Starting Protocol Monk with async input (UI: {ui_type})...")

    # Create event bus
    event_bus = get_event_bus()

    # Create the agent
    agent = ProtocolAgent(
        model_name=model_name or "claude-3-5-sonnet-20241022",
        provider=provider or "anthropic",
        event_bus=event_bus,
    )

    # Create UI based on type
    if ui_type == "plain":
        from ui.plain.app import PlainUI

        ui = PlainUI()
        # Create async adapter
        async_adapter = PlainUIAsyncAdapter(ui.input_manager)
        # This would need to be integrated into the PlainUI class
        ui._async_adapter = async_adapter

    elif ui_type == "rich":
        from ui.rich.app import RichUI

        ui = RichUI()
        # Create async adapter
        async_adapter = RichUIAsyncAdapter(ui)
        # This would need to be integrated into the RichUI class
        ui._async_adapter = async_adapter

    elif ui_type == "textual":
        from ui.textual.app import ProtocolMonkChat

        ui = ProtocolMonkChat()
        # Create async adapter
        async_adapter = TextualUIAsyncAdapter(ui)
        # This would need to be integrated into the ProtocolMonkChat class
        ui._async_adapter = async_adapter

    else:
        raise ValueError(f"Unknown UI type: {ui_type}")

    # Set UI on agent
    agent.ui = ui

    # Run with async main loop
    try:
        await run_async_main_loop(agent)
    except KeyboardInterrupt:
        print("\nShutting down gracefully...")
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)


# Modified MonkAgent class with async input support
class AsyncMonkAgent(ProtocolAgent):
    """
    Extended ProtocolAgent with async input support.

    This class demonstrates how to extend the existing agent to use
    the async input system while maintaining backward compatibility.
    """

    def __init__(self, *args, use_async_input: bool = True, **kwargs):
        super().__init__(*args, **kwargs)
        self.use_async_input = use_async_input
        self._async_main_loop = None

    async def run(self) -> None:
        """Run the agent with async or blocking input."""
        if self.use_async_input:
            await self._run_async()
        else:
            await self._run_blocking()

    async def _run_async(self) -> None:
        """Run with async input system."""
        print("Running with async input system...")

        # Create async main loop
        self._async_main_loop = create_main_loop(self, use_async=True)

        # Start the loop
        await self._async_main_loop.start()

        # Keep running until stopped
        while self._async_main_loop.is_running:
            await asyncio.sleep(0.1)

    async def _run_blocking(self) -> None:
        """Run with original blocking input (fallback)."""
        print("Running with blocking input system...")

        # Use the original implementation
        # This would call the original run() method from ProtocolAgent
        # For now, just demonstrate the pattern
        await super().run()

    async def stop(self) -> None:
        """Stop the agent."""
        if self._async_main_loop:
            await self._async_main_loop.stop()


# Example: Running multiple agents in parallel
async def run_multiple_agents():
    """Demonstrate running multiple agents in parallel."""
    print("Starting multiple agents in parallel...")

    # Create agents
    agents = [
        AsyncMonkAgent(
            model_name="claude-3-5-sonnet-20241022",
            provider="anthropic",
            name=f"Agent-{i}",
        )
        for i in range(3)
    ]

    # Create tasks for each agent
    tasks = [asyncio.create_task(agent.run()) for agent in agents]

    # Wait for all agents to complete
    try:
        await asyncio.gather(*tasks)
    except KeyboardInterrupt:
        # Stop all agents
        for agent in agents:
            await agent.stop()


# Migration guide for existing code
"""
Migration Guide: From Blocking to Async Input
=============================================

1. UI Classes:
   - Add async input adapter as a member
   - Implement get_input_async() method
   - Keep get_input() for backward compatibility

2. Agent Class:
   - Add use_async_input flag
   - Create async main loop if flag is True
   - Maintain original run() method as fallback

3. Event Handling:
   - Subscribe to USER_INPUT_SUBMITTED events
   - Process commands through existing dispatcher
   - Emit RESPONSE_COMPLETE when done

4. Testing:
   - Test async input with all three UI types
   - Verify backward compatibility
   - Check performance and responsiveness

Example migration for PlainUI:

class PlainUI:
    def __init__(self):
        self.input_manager = InputManager()
        self._async_adapter = PlainUIAsyncAdapter(self.input_manager)

    async def get_input(self) -> str:
        # New async implementation
        if hasattr(self, '_use_async') and self._use_async:
            return await self._async_adapter.get_input_async()

        # Original blocking implementation
        return await self.input_manager.read_input(is_main_loop=True)

Example migration for MonkAgent:

class MonkAgent:
    async def run(self):
        if self.use_async_input:
            await self._run_async_loop()
        else:
            await self._run_blocking_loop()

    async def _run_async_loop(self):
        # Use event-driven main loop
        main_loop = AsyncMainLoop(self, self.event_bus, self.input_manager)
        await main_loop.start()

    async def _run_blocking_loop(self):
        # Original implementation
        while True:
            text = await self.ui.get_input()
            # ... rest of original code
"""


if __name__ == "__main__":
    # Example usage
    import argparse

    parser = argparse.ArgumentParser(description="Run Protocol Monk with async input")
    parser.add_argument("--model", help="Model name")
    parser.add_argument("--provider", help="Provider name")
    parser.add_argument(
        "--ui", choices=["plain", "rich", "textual"], default="plain", help="UI type"
    )
    parser.add_argument("--multi", action="store_true", help="Run multiple agents")

    args = parser.parse_args()

    if args.multi:
        # Run multiple agents
        asyncio.run(run_multiple_agents())
    else:
        # Run single agent
        asyncio.run(
            run_with_async_input(
                model_name=args.model, provider=args.provider, ui_type=args.ui
            )
        )

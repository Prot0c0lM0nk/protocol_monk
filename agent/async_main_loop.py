"""
Async main loop implementation for the Monk Agent.

This module provides an event-driven main loop that doesn't block on input,
enabling true multi-agent parallel processing.
"""

import asyncio
from typing import Optional, Dict, Any
import time

from .service import AgentService
from agent.events import EventBus, AgentEvents, get_event_bus
from events.input_events import create_input_event
from ui.async_input_interface import AsyncInputManager


class AsyncMainLoop:
    """Event-driven main loop for the Agent Service."""

    def __init__(self, agent_service: AgentService, event_bus: EventBus, input_manager: AsyncInputManager):
        self.agent_service = agent_service
        self.event_bus = event_bus
        self.input_manager = input_manager
        self._running = False
        self._input_handler_task: Optional[asyncio.Task] = None
        self._event_handlers = {}
        self._setup_event_handlers()

    def _setup_event_handlers(self) -> None:
        """Set up event handlers for the main loop."""
        # No direct event handlers needed - events are processed through input manager
        pass

    async def start(self) -> None:
        """Start the async main loop."""
        self._running = True

        # Start input capture
        ui_type = 'plain'  # Default UI type
        await self.input_manager.start_capture(ui_type)

        # Start input handler task
        self._input_handler_task = asyncio.create_task(self._handle_input_events())

        # Emit startup events
        await self._emit_startup_events()

    async def stop(self) -> None:
        """Stop the async main loop."""
        self._running = False

        # Stop input capture
        await self.input_manager.stop_all_captures()

        # Cancel input handler task
        if self._input_handler_task:
            self._input_handler_task.cancel()
            try:
                await self._input_handler_task
            except asyncio.CancelledError:
                pass

    async def _handle_input_events(self) -> None:
        """Handle input events asynchronously."""
        try:
            async for input_event in self.input_manager.get_current_events():
                if not self._running:
                    break

                # Create proper event from input
                from events.input_events import create_input_event
                event = create_input_event(
                    input_event.data,
                    getattr(self.agent.ui, 'ui_type', 'plain')
                )

                # Emit the event for the system
                await self.event_bus.emit(event.type, event.data)

        except Exception as e:
            await self.event_bus.emit(
                AgentEvents.ERROR.value,
                {"message": f"Error handling input events: {e}", "context": "input_handler"}
            )

    async def _process_user_input(self, text: str) -> None:
        """Process user input text."""
        if not text:
            return

        try:
            # Use command dispatcher to handle input
            result = await self.agent_service.command_dispatcher.dispatch(text)

            if result is False:  # Quit command
                await self.stop()
                return

            # Not a command, process as chat
            if result is None:
                # Process through agent service
                success = await self.agent_service.process_chat_request(text)

                # Tell the UI the turn is over
                await self.event_bus.emit(AgentEvents.RESPONSE_COMPLETE.value, {})

        except Exception as e:
            await self.event_bus.emit(
                AgentEvents.ERROR.value,
                {"message": f"Error processing input: {e}", "context": "input_processing"}
            )

    async def _process_user_command(self, command: str) -> None:
        """Process user command."""
        # Commands are already handled by command dispatcher
        # This method is for command-specific event handling
        pass


    async def _emit_startup_events(self) -> None:
        """Emit startup information events."""
        # Model info
        await self.event_bus.emit(
            AgentEvents.INFO.value,
            {
                "message": f"Model: {self.agent.current_model} ({self.agent.current_provider})",
                "context": "startup",
            },
        )

        # Help message
        await self.event_bus.emit(
            AgentEvents.INFO.value,
            {
                "message": "Type '/help' for commands, '/quit' to exit.",
                "context": "startup",
            },
        )

    @property
    def is_running(self) -> bool:
        """Check if the main loop is running."""
        return self._running


# Integration with AgentService
async def run_async_main_loop(agent_service: AgentService) -> None:
    """
    Run the Agent Service with async main loop.

    This is the entry point for the async version of the agent.
    """
    # Create input manager
    input_manager = AsyncInputManager()

    # Register UI-specific input captures
    from ui.plain.async_input import PlainAsyncInput
    # from ui.rich.async_input import RichAsyncInput  # Will create this next
    # from ui.textual.async_input import TextualAsyncInput  # Will create this next

    input_manager.register_capture("plain", PlainAsyncInput())
    # input_manager.register_capture("rich", RichAsyncInput())
    # input_manager.register_capture("textual", TextualAsyncInput())

    # Create async main loop
    main_loop = AsyncMainLoop(agent_service, get_event_bus(), input_manager)

    try:
        # Start main loop
        await main_loop.start()

        # Keep running until stopped
        while main_loop.is_running:
            await asyncio.sleep(0.1)

    except KeyboardInterrupt:
        await agent_service.event_bus.emit(
            AgentEvents.INFO.value,
            {
                "message": "\nShutting down gracefully...",
                "context": "shutdown",
            },
        )
    except Exception as e:
        await agent_service.event_bus.emit(
            AgentEvents.ERROR.value,
            {"message": f"Fatal error: {e}", "context": "fatal_error"}
        )
    finally:
        # Ensure cleanup
        await main_loop.stop()


# Factory function to create appropriate main loop
def create_main_loop(agent_service: AgentService, use_async: bool = True) -> Any:
    """Create main loop based on configuration."""
    if use_async:
        return AsyncMainLoop(agent_service, get_event_bus(), AsyncInputManager())
    else:
        # Return None to use the original blocking loop
        return None
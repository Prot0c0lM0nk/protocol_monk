import logging
from typing import Dict, List, Callable, Any, Awaitable

from protocol_monk.exceptions.bus import EventBusError
from .events import EventTypes

# Type definition for event handlers
EventHandler = Callable[[Any], Awaitable[None]]


class EventBus:
    """
    Asynchronous Event Bus.

    Design Philosophy:
    - No business logic.
    - Fail-soft: One crashing listener should not crash the whole bus.
    - Async/Await: All handlers must be async.
    """

    def __init__(self):
        self._subscribers: Dict[EventTypes, List[EventHandler]] = {}
        self._logger = logging.getLogger("EventBus")

    def subscribe(self, event_type: EventTypes, handler: EventHandler) -> None:
        """
        Register a callback for a specific event type.
        """
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(handler)

    async def emit(self, event_type: EventTypes, data: Any = None) -> None:
        """
        Emit an event to all subscribers.

        We await handlers sequentially to ensure state consistency (e.g.,
        context must be updated before the next step runs).
        """
        if event_type not in self._subscribers:
            return

        for handler in self._subscribers[event_type]:
            try:
                await handler(data)
            except Exception as e:
                # We log the error but do NOT re-raise it,
                # ensuring other listeners still receive the event.
                self._logger.error(
                    f"Error in handler for {event_type.value}: {e}", exc_info=True
                )
                # Note: Critical system failures should be handled by the AgentService
                # emitting an ERROR event, not by crashing the bus.

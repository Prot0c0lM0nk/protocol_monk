import logging
import asyncio
from typing import Dict, List, Callable, Any, Awaitable

from protocol_monk.exceptions.bus import EventBusError
from .events import EventTypes

# Type definition for event handlers
EventHandler = Callable[[Any], Awaitable[None]]


class EventBus:
    """
    Asynchronous Event Bus.

    Design Philosophy:
    - Thread-Safe: Uses locks for subscriber registration.
    - Snapshot Execution: Iterates over a copy of handlers to allow
      dynamic subscription changes without crashing.
    - Sequential Consistency: Handlers run in order to preserve state integrity.
    """

    def __init__(self):
        # - Recommended Fix #1 (Add Lock)
        self._lock = asyncio.Lock()
        self._subscribers: Dict[EventTypes, List[EventHandler]] = {}
        self._logger = logging.getLogger("EventBus")

    async def subscribe(self, event_type: EventTypes, handler: EventHandler) -> None:
        """
        Register a callback for a specific event type safely.
        """
        # We lock here so two parts of the code can't modify the list at the exact same time
        async with self._lock:
            if event_type not in self._subscribers:
                self._subscribers[event_type] = []
            self._subscribers[event_type].append(handler)

    async def emit(self, event_type: EventTypes, data: Any = None) -> None:
        """
        Emit an event to all subscribers.
        """
        # 1. SNAPSHOT PHASE
        # We verify if subscribers exist without locking first to save time
        if event_type not in self._subscribers:
            return

        # Lock briefly to copy the list.
        async with self._lock:
            handlers_snapshot = list(self._subscribers.get(event_type, []))

        # 2. EXECUTION PHASE
        for handler in handlers_snapshot:
            # --- NEW: THE DOUBLE-CHECK ---
            # Before running, we quickly verify the handler is STILL in the live list.
            # This prevents the "Ghost Notification" if it was unsubscribed 
            # while the previous handler was running.
            async with self._lock:
                current_list = self._subscribers.get(event_type, [])
                if handler not in current_list:
                    continue  # Skip! It was removed.
            # -----------------------------

            try:
                # We keep this sequential as per your requirement for order.
                await handler(data)
            except Exception as e:
                # Log error but keep the bus alive (Fail-soft)
                self._logger.error(
                    f"Error in handler for {event_type.value}: {e}", exc_info=True
                )
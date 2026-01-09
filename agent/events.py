#!/usr/bin/env python3
"""
Event System for Protocol Monk
Replaces direct UI calls with event-driven architecture
"""

import asyncio
from typing import Dict, List, Callable, Any, Optional
from dataclasses import dataclass
from enum import Enum


class AgentEvents(Enum):
    """All events that the agent can emit"""

    ERROR = "agent.error"
    WARNING = "agent.warning"
    INFO = "agent.info"

    THINKING_STARTED = "agent.thinking_started"
    THINKING_STOPPED = "agent.thinking_stopped"

    TOOL_EXECUTION_START = "agent.tool_execution_start"
    TOOL_EXECUTION_PROGRESS = "agent.tool_execution_progress"
    TOOL_EXECUTION_COMPLETE = "agent.tool_execution_complete"
    TOOL_ERROR = "agent.tool_error"
    TOOL_RESULT = "agent.tool_result"

    # --- NEW: Critical Tool Events (Fixed Crash) ---
    TOOL_CONFIRMATION_REQUESTED = "agent.tool_confirmation_requested"
    TOOL_REJECTED = "agent.tool_rejected"
    TOOL_MODIFIED = "agent.tool_modified"
    TASK_COMPLETE = "agent.task_complete"
    AUTO_CONFIRM_CHANGED = "agent.auto_confirm_changed"
    # -----------------------------------------------

    STREAM_CHUNK = "agent.stream_chunk"
    RESPONSE_COMPLETE = "agent.response_complete"

    CONTEXT_OVERFLOW = "agent.context_overflow"
    MODEL_SWITCHED = "agent.model_switched"
    PROVIDER_SWITCHED = "agent.provider_switched"

    COMMAND_RESULT = "agent.command_result"
    STATUS_CHANGED = "agent.status_changed"


@dataclass
class Event:
    """Event data container"""

    type: str
    data: Dict[str, Any]
    timestamp: float


class EventBus:
    """Central event bus for agent-UI communication"""

    def __init__(self):
        self._listeners: Dict[str, List[Callable]] = {}
        self._lock = asyncio.Lock()

    def subscribe(self, event_type: str, callback: Callable) -> None:
        """Subscribe to a specific event type"""
        if event_type not in self._listeners:
            self._listeners[event_type] = []
        self._listeners[event_type].append(callback)

    def unsubscribe(self, event_type: str, callback: Callable) -> None:
        """Unsubscribe from a specific event type"""
        if event_type in self._listeners:
            if callback in self._listeners[event_type]:
                self._listeners[event_type].remove(callback)

    async def emit(self, event_type: str, data: Dict[str, Any]) -> None:
        """Emit an event to all subscribers"""
        async with self._lock:
            if event_type in self._listeners:
                # Create event object
                event = Event(
                    type=event_type,
                    data=data,
                    timestamp=asyncio.get_event_loop().time(),
                )

                # Call all subscribers
                tasks = []
                for callback in self._listeners[event_type]:
                    try:
                        # Handle both sync and async callbacks
                        if asyncio.iscoroutinefunction(callback):
                            tasks.append(callback(event.data))
                        else:
                            callback(event.data)
                    except Exception as e:
                        print(f"Error in event callback: {e}")

                # Wait for all async callbacks to complete
                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)
    async def emit_batch(self, events: List[tuple]) -> None:
        """Emit multiple events atomically"""
        async with self._lock:
            for event_type, data in events:
                await self.emit(event_type, data)


# Global event bus instance
_global_event_bus: Optional[EventBus] = None


def get_event_bus() -> EventBus:
    """Get the global event bus instance"""
    global _global_event_bus
    if _global_event_bus is None:
        _global_event_bus = EventBus()
    return _global_event_bus

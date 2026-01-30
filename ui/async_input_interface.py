"""
Async input interface for non-blocking user input across all UI systems.
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import AsyncIterator, Optional, Dict, Any
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class InputEventType(Enum):
    """Types of input events."""
    TEXT_SUBMITTED = "text_submitted"
    INTERRUPT = "interrupt"
    EOF = "eof"
    
    # keys required by AsyncPrompts
    CHARACTER = "character" 
    SPECIAL_KEY = "special_key"
    KEY = "key"


@dataclass
class InputEvent:
    """Represents a user input event."""
    type: InputEventType # Renamed from event_type to match AsyncPrompts usage often seen
    data: str
    timestamp: float
    metadata: Optional[Dict[str, Any]] = None


class AsyncInputInterface(ABC):
    """Abstract interface for async input handling."""

    def __init__(self):
        self._running = False
        self._event_queue = asyncio.Queue()

    @abstractmethod
    async def start_capture(self) -> None:
        pass

    @abstractmethod
    async def stop_capture(self) -> None:
        pass

    @abstractmethod
    async def display_prompt(self) -> None:
        pass

    async def get_input_events(self) -> AsyncIterator[InputEvent]:
        """Get input events as they occur."""
        while self._running:
            try:
                # Wait for event
                event = await asyncio.wait_for(
                    self._event_queue.get(),
                    timeout=0.1
                )
                yield event
            except asyncio.TimeoutError:
                continue

    async def _emit_event(self, event: InputEvent) -> None:
        await self._event_queue.put(event)

    @property
    def is_running(self) -> bool:
        return self._running


class AsyncInputManager:
    """Manager for coordinating async input across UI systems."""

    def __init__(self):
        self._captures: Dict[str, AsyncInputInterface] = {}
        self._current_capture: Optional[AsyncInputInterface] = None

    def register_capture(self, name: str, capture: AsyncInputInterface) -> None:
        self._captures[name] = capture

    async def start_capture(self, name: str) -> None:
        if name not in self._captures:
            raise ValueError(f"Unknown capture: {name}")

        if self._current_capture and self._current_capture != self._captures[name]:
            await self._current_capture.stop_capture()

        self._current_capture = self._captures[name]
        if not self._current_capture.is_running:
            await self._current_capture.start_capture()

    async def stop_all_captures(self) -> None:
        for capture in self._captures.values():
            if capture.is_running:
                await capture.stop_capture()
        self._current_capture = None

    async def get_current_events(self) -> AsyncIterator[InputEvent]:
        if not self._current_capture:
            # If no capture is active, we can't yield events.
            # Returning immediately stops the async for loop gracefully.
            return 
            
        async for event in self._current_capture.get_input_events():
            yield event
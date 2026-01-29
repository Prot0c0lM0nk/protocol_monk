"""
Async input interface for non-blocking user input across all UI systems.
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import AsyncIterator, Optional, Dict, Any
from dataclasses import dataclass
from enum import Enum
import time

logger = logging.getLogger(__name__)


class InputEventType(Enum):
    """Types of input events."""
    TEXT_SUBMITTED = "text_submitted"
    INTERRUPT = "interrupt"
    EOF = "eof"
    SPECIAL_KEY = "special_key"


@dataclass
class InputEvent:
    """Represents a user input event."""
    event_type: InputEventType
    data: str
    timestamp: float
    metadata: Optional[Dict[str, Any]] = None


class AsyncInputInterface(ABC):
    """Abstract interface for async input handling."""

    def __init__(self):
        self._running = False
        self._event_queue = asyncio.Queue()
        self._capture_task: Optional[asyncio.Task] = None

    @abstractmethod
    async def start_capture(self) -> None:
        """Start capturing input events."""
        pass

    @abstractmethod
    async def stop_capture(self) -> None:
        """Stop capturing input events."""
        pass

    @abstractmethod
    def display_prompt(self) -> None:
        """Display or redisplay the input prompt."""
        pass

    async def get_input_events(self) -> AsyncIterator[InputEvent]:
        """Get input events as they occur."""
        while self._running:
            try:
                event = await asyncio.wait_for(
                    self._event_queue.get(),
                    timeout=0.1
                )
                yield event
            except asyncio.TimeoutError:
                continue

    async def _emit_event(self, event: InputEvent) -> None:
        """Emit an input event."""
        await self._event_queue.put(event)

    @property
    def is_running(self) -> bool:
        """Check if input capture is running."""
        return self._running


class AsyncInputManager:
    """Manager for coordinating async input across UI systems."""

    def __init__(self):
        self._captures: Dict[str, AsyncInputInterface] = {}
        self._current_capture: Optional[AsyncInputInterface] = None

    def register_capture(self, name: str, capture: AsyncInputInterface) -> None:
        """Register an async input capture implementation."""
        self._captures[name] = capture

    async def start_capture(self, name: str) -> None:
        """Start a specific input capture."""
        logger.debug(f"AsyncInputManager.start_capture: name={name}, current_capture={self._current_capture}")
        if name not in self._captures:
            raise ValueError(f"Unknown capture: {name}")

        # Stop current capture if running
        if self._current_capture:
            logger.debug("AsyncInputManager.start_capture: Stopping current capture")
            await self._current_capture.stop_capture()

        # Start new capture
        self._current_capture = self._captures[name]
        logger.debug("AsyncInputManager.start_capture: Starting new capture")
        await self._current_capture.start_capture()

    def display_current_prompt(self) -> None:
        """Display the prompt for the currently active capture."""
        if self._current_capture:
            self._current_capture.display_prompt()

    async def stop_all_captures(self) -> None:
        """Stop all input captures."""
        for capture in self._captures.values():
            if capture.is_running:
                await capture.stop_capture()

        self._current_capture = None

    async def get_current_events(self) -> AsyncIterator[InputEvent]:
        """Get events from current capture."""
        if not self._current_capture:
            raise RuntimeError("No capture is currently active")

        async for event in self._current_capture.get_input_events():
            yield event
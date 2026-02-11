"""Regression tests for Textual selection cancel behavior."""

import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent.events import AgentEvents, EventBus
from ui.textual.interface import TextualUI


class _DummyApp:
    def __init__(self):
        self.messages = []

    def post_message(self, message) -> None:
        self.messages.append(message)

    async def push_screen_wait(self, screen):
        # Simulate user pressing cancel/escape in SelectionModal.
        return None


@pytest.mark.asyncio
async def test_selection_cancel_emits_empty_input_response():
    bus = EventBus()
    app = _DummyApp()
    ui = TextualUI(app, event_bus=bus)

    ui._pending_title = "Available Models"
    ui._pending_options = ["model-a", "model-b"]

    waiter = asyncio.create_task(
        bus.wait_for(AgentEvents.INPUT_RESPONSE.value, timeout=1.0)
    )
    await asyncio.sleep(0)

    await ui._on_input_requested({"prompt": "Select a model"})
    payload = await waiter

    assert payload.get("input") == ""

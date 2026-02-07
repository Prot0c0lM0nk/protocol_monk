"""
ui/textual/command_provider.py
The Command Bridge: Exposes Agent Actions and Debug Tests to the Palette.
"""

import asyncio

from textual.command import Provider, Hit, Hits, DiscoveryHit
from agent.events import AgentEvents, get_event_bus


class AgentCommandProvider(Provider):
    """
    Protocol Monk Command Palette Provider.
    """

    # === THE COMMAND DEFINITIONS ===
    # We define them in one place so both search and discover can see them.
    # Format: (Display Name, Callback, Help Text)
    DATA = [
        # -- Real Agent Actions --
        ("Quit Protocol Monk", "action_quit", "Exit the application gracefully"),
        ("Clear Context", "action_clear", "Reset conversation memory"),
        ("Switch Model", "action_model", "Switch the AI model"),
        ("Switch Provider", "action_provider", "Switch between Ollama/OpenRouter"),
        # -- UI Stress Tests (Manual Verification) --
        ("Test: Error Toast", "test_error", "[DEBUG] Fire a fake error event"),
        ("Test: Info Toast", "test_info", "[DEBUG] Fire a fake info event"),
        (
            "Test: Thinking On",
            "test_thinking_on",
            "[DEBUG] Force thinking indicator ON",
        ),
        (
            "Test: Thinking Off",
            "test_thinking_off",
            "[DEBUG] Force thinking indicator OFF",
        ),
        (
            "Test: Tool Confirmation",
            "test_tool_confirm",
            "[DEBUG] Pop the tool confirmation modal",
        ),
    ]

    async def discover(self) -> Hits:
        """Called when the palette is opened with NO text."""
        for name, callback_name, help_text in self.DATA:
            # We use DiscoveryHit for the initial list
            yield DiscoveryHit(
                display=name, command=getattr(self, callback_name), help=help_text
            )

    async def search(self, query: str) -> Hits:
        """Called when the user starts TYPING."""
        matcher = self.matcher(query)

        for name, callback_name, help_text in self.DATA:
            score = matcher.match(name)
            if score > 0:
                yield Hit(
                    score=score,
                    match_display=matcher.highlight(name),
                    action=getattr(self, callback_name),
                    help=help_text,
                )

    # --- 1. REAL COMMANDS (Internal Injection) ---

    async def _inject_command(self, command_str: str):
        """Send slash commands via pending prompt future or event bus."""
        bus = getattr(self.app, "event_bus", None) or get_event_bus()

        # If the agent loop is waiting on a direct prompt, satisfy that first.
        if hasattr(self.app, "_input_future") and self.app._input_future:
            if not self.app._input_future.done():
                self.app._input_future.set_result(command_str)
                self.app.notify(f"Command Sent: {command_str}")
                return

        # Otherwise treat it like normal user input and emit to the shared bus.
        if bus:
            asyncio.create_task(
                bus.emit(AgentEvents.USER_INPUT.value, {"input": command_str})
            )
            self.app.notify(f"Command Sent: {command_str}")
        else:
            self.app.notify("No event bus available for command.", severity="error")

    async def action_quit(self):
        await self.app.action_quit()

    async def action_clear(self):
        await self._inject_command("/clear")

    async def action_model(self):
        await self._inject_command("/model")

    async def action_provider(self):
        await self._inject_command("/provider")

    # --- 2. DEBUG TESTS (Event Emission) ---

    async def test_error(self):
        bus = getattr(self.app, "event_bus", None) or get_event_bus()
        await bus.emit(
            AgentEvents.ERROR.value,
            {
                "message": "Manual Test: Critical Reactor Failure detected!",
                "context": "test_suite",
            },
        )

    async def test_info(self):
        bus = getattr(self.app, "event_bus", None) or get_event_bus()
        await bus.emit(
            AgentEvents.INFO.value,
            {
                "message": "Manual Test: Systems operating within normal parameters.",
                "context": "test_suite",
            },
        )

    async def test_thinking_on(self):
        bus = getattr(self.app, "event_bus", None) or get_event_bus()
        await bus.emit(AgentEvents.THINKING_STARTED.value, {})

    async def test_thinking_off(self):
        bus = getattr(self.app, "event_bus", None) or get_event_bus()
        await bus.emit(AgentEvents.THINKING_STOPPED.value, {})

    async def test_tool_confirm(self):
        from ui.textual.screens.modals.tool_confirm import ToolConfirmModal

        dummy_data = {
            "tool": "Orbital_Laser_Strike",
            "args": {"target": "Moon", "intensity": "Maximum"},
        }
        self.app.push_screen(ToolConfirmModal(dummy_data))

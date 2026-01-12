#!/usr/bin/env python3
"""
Mock Event-Emitting Agent for Protocol Monk
===========================================
A complete mock agent that emits ALL events from the AgentEvents enum.
This is designed for testing the Textual UI event handling without
requiring actual model calls or tool execution.

Usage:
    python -m agent.mock_event_agent
"""

import asyncio
import time
import random
from typing import Dict, Any, Optional
from agent.events import EventBus, AgentEvents, get_event_bus


class MockEventAgent:
    """
    A mock agent that emits all events defined in AgentEvents.
    Simulates realistic agent behavior patterns for UI testing.
    """

    def __init__(self, event_bus: Optional[EventBus] = None):
        self.event_bus = event_bus or get_event_bus()
        self.running = False
        self.current_model = "mock-model"
        self.current_provider = "mock-provider"

    async def emit_all_events(self) -> None:
        """
        Emit ALL events in a realistic sequence simulating a full agent workflow.
        This covers every event type in AgentEvents enum.
        """
        self.running = True

        # 1. Startup events
        await self._emit_startup_events()

        # 2. Simulate a full conversation cycle
        await self._simulate_conversation_cycle()

        # 3. Simulate tool execution with all tool-related events
        await self._simulate_tool_execution()

        # 4. Simulate error scenarios
        await self._simulate_error_scenarios()

        # 5. Simulate status changes
        await self._simulate_status_changes()

        # 6. Simulate model/provider switching
        await self._simulate_model_switching()

        # 7. Simulate ALL slash commands (for command palette testing)
        await self._simulate_all_commands()

        # 8. Final task completion
        await self._emit_task_complete()
        self.running = False

    async def _emit_startup_events(self) -> None:
        """Emit startup sequence events."""
        await self._emit_event(
            AgentEvents.INFO,
            {
                "message": "✠ Mock Event Agent started",
                "context": "startup"
            }
        )
        await asyncio.sleep(0.2)

        await self._emit_event(
            AgentEvents.INFO,
            {
                "message": f"Model: {self.current_model} ({self.current_provider})",
                "context": "startup"
            }
        )
        await asyncio.sleep(0.2)

        await self._emit_event(
            AgentEvents.STATUS_CHANGED,
            {
                "status": "ready",
                "message": "Agent ready for input"
            }
        )

    async def _simulate_all_commands(self) -> None:
        """
        Simulate ALL slash commands from CommandDispatcher.
        This is critical for testing the command palette in Textual UI.
        """
        await asyncio.sleep(0.5)
        await self._emit_event(
            AgentEvents.INFO,
            {
                "message": "[MOCK] Simulating all slash commands...",
                "context": "command_simulation"
            }
        )

        # 1. /help command
        await self._simulate_help_command()
        await asyncio.sleep(0.5)

        # 2. /status command
        await self._simulate_status_command()
        await asyncio.sleep(0.5)

        # 3. /model command (with model selection list)
        await self._simulate_model_command()
        await asyncio.sleep(0.5)

        # 4. /provider command (with provider selection list)
        await self._simulate_provider_command()
        await asyncio.sleep(0.5)

        # 5. /file command (file ingest)
        await self._simulate_file_command()
        await asyncio.sleep(0.5)

        # 6. /clear command
        await self._simulate_clear_command()
        await asyncio.sleep(0.5)

        # 7. Unknown command (error case)
        await self._simulate_unknown_command()

    async def _simulate_help_command(self) -> None:
        """Simulate /help command output."""
        help_text = """The Protocol Commands:
/help     - Display this wisdom
/status   - View current state
/model    - Switch to a different model
/provider - Switch to a different provider
/clear    - Clear conversation history
/file     - Load a file into context (Context Injection)
/quit     - Exit with blessing"""

        await self._emit_event(
            AgentEvents.COMMAND_RESULT,
            {
                "command": "/help",
                "success": True,
                "message": help_text
            }
        )

    async def _simulate_status_command(self) -> None:
        """Simulate /status command output."""
        status_text = f"""Current State:
Model: {self.current_model}
Provider: {self.current_provider}
Working Directory: /mock/workspace
   /mock/workspace

Conversation: 5 messages
Tokens: 1,234 / 8,192"""

        await self._emit_event(
            AgentEvents.COMMAND_RESULT,
            {
                "command": "/status",
                "success": True,
                "message": status_text
            }
        )

    async def _simulate_model_command(self) -> None:
        """
        Simulate /model command with model selection list.
        This tests the UI's ability to display selectable lists.
        """
        # First, emit the model list (this is what PlainUI renders as a blue list)
        mock_models = [
            {"name": "llama3-8b", "context_window": 8192, "provider": "ollama"},
            {"name": "llama3-70b", "context_window": 128000, "provider": "ollama"},
            {"name": "mistral-7b", "context_window": 32768, "provider": "ollama"},
            {"name": "gpt-4", "context_window": 128000, "provider": "openrouter"},
            {"name": "claude-3-opus", "context_window": 200000, "provider": "openrouter"},
        ]

        await self._emit_event(
            AgentEvents.INFO,
            {
                "message": "Available Models",
                "data": mock_models,
                "context": "model_selection"
            }
        )

        # Simulate user selecting model 2 (llama3-70b)
        await asyncio.sleep(0.3)
        old_model = self.current_model
        self.current_model = "llama3-70b"

        await self._emit_event(
            AgentEvents.MODEL_SWITCHED,
            {
                "old_model": old_model,
                "new_model": self.current_model,
                "context_window": 128000
            }
        )

        await self._emit_event(
            AgentEvents.COMMAND_RESULT,
            {
                "command": "/model",
                "success": True,
                "message": f"✔️ Switched to {self.current_model}"
            }
        )

    async def _simulate_provider_command(self) -> None:
        """
        Simulate /provider command with provider selection list.
        This also triggers model selection after provider switch.
        """
        # Emit provider list
        providers = ["ollama", "openrouter"]

        await self._emit_event(
            AgentEvents.INFO,
            {
                "message": "Available Providers",
                "data": providers,
                "context": "provider_selection"
            }
        )

        # Simulate user selecting provider 2 (openrouter)
        await asyncio.sleep(0.3)
        old_provider = self.current_provider
        self.current_provider = "openrouter"

        await self._emit_event(
            AgentEvents.PROVIDER_SWITCHED,
            {
                "old_provider": old_provider,
                "new_provider": self.current_provider
            }
        )

        await self._emit_event(
            AgentEvents.COMMAND_RESULT,
            {
                "command": "/provider",
                "success": True,
                "message": f"Switched to {self.current_provider}"
            }
        )

        # After provider switch, automatically trigger model selection
        await asyncio.sleep(0.3)
        await self._emit_event(
            AgentEvents.INFO,
            {
                "message": f"Please select a {self.current_provider} model:",
                "context": "model_selection_after_provider"
            }
        )

    async def _simulate_file_command(self) -> None:
        """
        Simulate /file command (file ingest).
        Tests UI's file handling and context injection.
        """
        # Simulate successful file read and ingest
        filename = "example.py"
        content = "# Example file content\nprint('Hello, world!')\n"

        await self._emit_event(
            AgentEvents.INFO,
            {
                "message": f"Ingested '{filename}' ({len(content)} chars) into context."
            }
        )

        await self._emit_event(
            AgentEvents.COMMAND_RESULT,
            {
                "command": "/file",
                "success": True,
                "message": f"✓ File '{filename}' loaded into context",
                "data": {
                    "filename": filename,
                    "size": len(content),
                    "lines": 3
                }
            }
        )

    async def _simulate_clear_command(self) -> None:
        """Simulate /clear command."""
        await self._emit_event(
            AgentEvents.INFO,
            {
                "message": "✓ Cleared.",
                "context": "context_cleared"
            }
        )

        await self._emit_event(
            AgentEvents.COMMAND_RESULT,
            {
                "command": "/clear",
                "success": True,
                "message": "Conversation context cleared"
            }
        )

    async def _simulate_unknown_command(self) -> None:
        """Simulate unknown command (error case for UI testing)."""
        await self._emit_event(
            AgentEvents.ERROR,
            {
                "message": "Unknown command: /bogus",
                "context": "command_error"
            }
        )

    async def _simulate_conversation_cycle(self) -> None:
        """Simulate a full conversation with streaming response."""
        # User input would trigger this
        await self._emit_event(
            AgentEvents.INFO,
            {
                "message": "User: Hello, mock agent!",
                "context": "user_input"
            }
        )

        # Thinking starts
        await self._emit_event(
            AgentEvents.THINKING_STARTED,
            {}
        )
        await asyncio.sleep(0.5)

        # Simulate thinking content
        await self._emit_event(
            AgentEvents.STREAM_CHUNK,
            {
                "thinking": "Analyzing user request..."
            }
        )
        await asyncio.sleep(0.3)

        # Simulate streaming text response
        response_text = "Hello! I am the mock event agent. I emit all events for testing the Textual UI."
        for char in response_text:
            await self._emit_event(
                AgentEvents.STREAM_CHUNK,
                {
                    "chunk": char
                }
            )
            await asyncio.sleep(0.02)  # Simulate streaming speed

        # Thinking stops
        await self._emit_event(
            AgentEvents.THINKING_STOPPED,
            {}
        )

        # Response complete
        await self._emit_event(
            AgentEvents.RESPONSE_COMPLETE,
            {
                "content": response_text,
                "tokens": len(response_text.split())
            }
        )

    async def _simulate_tool_execution(self) -> None:
        """Simulate complete tool execution lifecycle."""
        # Tool execution starts
        await self._emit_event(
            AgentEvents.TOOL_EXECUTION_START,
            {
                "tool_name": "read_file",
                "parameters": {"filepath": "test.py"},
                "tool_call_id": "call_123",
                "requires_confirmation": True
            }
        )
        await asyncio.sleep(0.3)

        # Confirmation requested
        await self._emit_event(
            AgentEvents.TOOL_CONFIRMATION_REQUESTED,
            {
                "tool_name": "read_file",
                "parameters": {"filepath": "test.py"},
                "tool_call_id": "call_123",
                "reason": "Reading file content"
            }
        )
        await asyncio.sleep(0.5)

        # Simulate user approving the tool
        await self._emit_event(
            AgentEvents.INFO,
            {
                "message": "✓ Tool approved by user",
                "context": "tool_confirmation"
            }
        )

        # Tool execution progress
        for i in range(1, 4):
            await self._emit_event(
                AgentEvents.TOOL_EXECUTION_PROGRESS,
                {
                    "tool_name": "read_file",
                    "progress": i * 33,
                    "message": f"Reading file... {i * 33}%"
                }
            )
            await asyncio.sleep(0.3)

        # Tool result
        await self._emit_event(
            AgentEvents.TOOL_RESULT,
            {
                "tool_name": "read_file",
                "tool_call_id": "call_123",
                "output": "# Mock file content\nprint('Hello, world!')",
                "success": True
            }
        )
        await asyncio.sleep(0.2)

        # Tool execution complete
        await self._emit_event(
            AgentEvents.TOOL_EXECUTION_COMPLETE,
            {
                "tool_name": "read_file",
                "tool_call_id": "call_123",
                "success": True,
                "duration": 1.2
            }
        )

        # Simulate tool rejection scenario
        await asyncio.sleep(0.5)
        await self._emit_event(
            AgentEvents.TOOL_EXECUTION_START,
            {
                "tool_name": "delete_file",
                "parameters": {"filepath": "important.py"},
                "tool_call_id": "call_456",
                "requires_confirmation": True
            }
        )
        await asyncio.sleep(0.3)

        await self._emit_event(
            AgentEvents.TOOL_REJECTED,
            {
                "tool_name": "delete_file",
                "tool_call_id": "call_456",
                "reason": "User rejected dangerous operation"
            }
        )

        # Simulate tool modification scenario
        await asyncio.sleep(0.5)
        await self._emit_event(
            AgentEvents.TOOL_EXECUTION_START,
            {
                "tool_name": "execute_command",
                "parameters": {"command": "rm -rf /"},
                "tool_call_id": "call_789",
                "requires_confirmation": True
            }
        )
        await asyncio.sleep(0.3)

        await self._emit_event(
            AgentEvents.TOOL_MODIFIED,
            {
                "tool_name": "execute_command",
                "tool_call_id": "call_789",
                "original_parameters": {"command": "rm -rf /"},
                "modified_parameters": {"command": "echo 'safe command'"},
                "reason": "Modified dangerous command for safety"
            }
        )

        # Auto-confirm changed
        await asyncio.sleep(0.5)
        await self._emit_event(
            AgentEvents.AUTO_CONFIRM_CHANGED,
            {
                "auto_confirm": True,
                "message": "Auto-confirm enabled for trusted tools"
            }
        )

    async def _simulate_error_scenarios(self) -> None:
        """Simulate various error events."""
        await asyncio.sleep(0.5)

        # Tool error
        await self._emit_event(
            AgentEvents.TOOL_ERROR,
            {
                "tool_name": "read_file",
                "error": "File not found: nonexistent.py",
                "tool_call_id": "call_error_1"
            }
        )
        await asyncio.sleep(0.3)

        # General warning
        await self._emit_event(
            AgentEvents.WARNING,
            {
                "message": "Context approaching token limit (85% full)",
                "context": "context_management"
            }
        )
        await asyncio.sleep(0.3)

        # Context overflow
        await self._emit_event(
            AgentEvents.CONTEXT_OVERFLOW,
            {
                "message": "Context overflow detected. Pruning old messages...",
                "tokens_before": 8000,
                "tokens_after": 4000,
                "messages_pruned": 15
            }
        )
        await asyncio.sleep(0.3)

        # General error
        await self._emit_event(
            AgentEvents.ERROR,
            {
                "message": "Connection timeout. Retrying...",
                "context": "network",
                "retry_after": 5
            }
        )

    async def _simulate_status_changes(self) -> None:
        """Simulate status change events."""
        await asyncio.sleep(0.5)

        statuses = [
            ("thinking", "Processing request..."),
            ("executing", "Running tools..."),
            ("idle", "Waiting for input"),
            ("busy", "Working on complex task...")
        ]

        for status, message in statuses:
            await self._emit_event(
                AgentEvents.STATUS_CHANGED,
                {
                    "status": status,
                    "message": message
                }
            )
            await asyncio.sleep(0.3)

    async def _simulate_model_switching(self) -> None:
        """Simulate model and provider switching events."""
        await asyncio.sleep(0.5)

        # Model switched
        await self._emit_event(
            AgentEvents.MODEL_SWITCHED,
            {
                "old_model": self.current_model,
                "new_model": "llama3-70b",
                "context_window": 8192
            }
        )
        self.current_model = "llama3-70b"
        await asyncio.sleep(0.3)

        # Provider switched
        await self._emit_event(
            AgentEvents.PROVIDER_SWITCHED,
            {
                "old_provider": self.current_provider,
                "new_provider": "openrouter"
            }
        )
        self.current_provider = "openrouter"
        await asyncio.sleep(0.3)

        # Command result (simulating /model command)
        await self._emit_event(
            AgentEvents.COMMAND_RESULT,
            {
                "command": "/model",
                "success": True,
                "message": f"Switched to {self.current_model}"
            }
        )

    async def _emit_task_complete(self) -> None:
        """Emit final task completion event."""
        await asyncio.sleep(0.5)

        await self._emit_event(
            AgentEvents.TASK_COMPLETE,
            {
                "message": "All mock events emitted successfully!",
                "total_events": len(AgentEvents),
                "duration": 10.0
            }
        )

        await self._emit_event(
            AgentEvents.INFO,
            {
                "message": "Mock agent finished. Check your UI for all events.",
                "context": "completion"
            }
        )

    async def _emit_event(self, event_type: AgentEvents, data: Dict[str, Any]) -> None:
        """
        Helper method to emit an event with logging.

        Args:
            event_type: The AgentEvent enum value
            data: Event data dictionary
        """
        print(f"[MOCK AGENT] Emitting: {event_type.value}")
        await self.event_bus.emit(event_type.value, data)

    async def run_interactive(self) -> None:
        """
        Run the mock agent in interactive mode.
        Continuously emits random events for stress testing.
        """
        self.running = True
        print("[MOCK AGENT] Running in INTERACTIVE mode (Ctrl+C to stop)")
        print("[MOCK AGENT] Emitting random events...")

        try:
            while self.running:
                # Pick a random event
                event_type = random.choice(list(AgentEvents))

                # Generate appropriate mock data
                data = self._generate_random_event_data(event_type)

                # Emit the event
                await self._emit_event(event_type, data)

                # Random delay between events
                await asyncio.sleep(random.uniform(0.1, 1.0))

        except KeyboardInterrupt:
            print("\n[MOCK AGENT] Stopping...")
            self.running = False

    def _generate_random_event_data(self, event_type: AgentEvents) -> Dict[str, Any]:
        """Generate appropriate mock data for each event type."""
        base_data = {
            "timestamp": time.time(),
            "mock": True
        }

        if event_type == AgentEvents.STREAM_CHUNK:
            return {
                **base_data,
                "chunk": random.choice(["Hello", "world", "testing", "events"]),
                "thinking": None
            }

        elif event_type == AgentEvents.TOOL_EXECUTION_START:
            tools = ["read_file", "write_file", "execute_command", "search"]
            return {
                **base_data,
                "tool_name": random.choice(tools),
                "parameters": {"mock_param": "value"},
                "tool_call_id": f"call_{random.randint(1000, 9999)}",
                "requires_confirmation": random.choice([True, False])
            }

        elif event_type == AgentEvents.TOOL_EXECUTION_PROGRESS:
            return {
                **base_data,
                "tool_name": "mock_tool",
                "progress": random.randint(1, 100),
                "message": f"Progress: {random.randint(1, 100)}%"
            }

        elif event_type == AgentEvents.TOOL_RESULT:
            return {
                **base_data,
                "tool_name": "mock_tool",
                "tool_call_id": f"call_{random.randint(1000, 9999)}",
                "output": "Mock tool output",
                "success": random.choice([True, False])
            }

        elif event_type == AgentEvents.ERROR:
            errors = [
                "Connection timeout",
                "Rate limit exceeded",
                "Invalid API key",
                "Service unavailable"
            ]
            return {
                **base_data,
                "message": random.choice(errors),
                "context": "mock_error"
            }

        elif event_type == AgentEvents.WARNING:
            warnings = [
                "Context nearly full",
                "Slow response detected",
                "Token limit approaching"
            ]
            return {
                **base_data,
                "message": random.choice(warnings),
                "context": "mock_warning"
            }

        elif event_type == AgentEvents.INFO:
            messages = [
                "Processing request",
                "Tool executed successfully",
                "Model response received"
            ]
            return {
                **base_data,
                "message": random.choice(messages),
                "context": "mock_info"
            }

        elif event_type == AgentEvents.STATUS_CHANGED:
            statuses = ["thinking", "idle", "executing", "busy"]
            return {
                **base_data,
                "status": random.choice(statuses),
                "message": f"Status changed to {random.choice(statuses)}"
            }

        else:
            return {
                **base_data,
                "message": f"Mock data for {event_type.value}"
            }


async def main():
    """Main entry point for running the mock agent."""
    print("=" * 60)
    print("MOCK EVENT AGENT FOR PROTOCOL MONK")
    print("=" * 60)
    print("\nThis agent emits ALL events from AgentEvents enum.")
    print("Use it to test your Textual UI event handling.\n")

    agent = MockEventAgent()

    print("Choose mode:")
    print("1. Full sequence (emits all events in order)")
    print("2. Interactive (random events continuously)")
    print("3. Both (sequence first, then interactive)")

    choice = input("\nEnter choice (1/2/3) [default: 1]: ").strip() or "1"

    if choice == "1":
        print("\n[MOCK AGENT] Running full sequence mode...")
        await agent.emit_all_events()

    elif choice == "2":
        print("\n[MOCK AGENT] Running interactive mode...")
        await agent.run_interactive()

    elif choice == "3":
        print("\n[MOCK AGENT] Running full sequence first...")
        await agent.emit_all_events()
        print("\n[MOCK AGENT] Now switching to interactive mode...")
        await agent.run_interactive()

    else:
        print("Invalid choice. Running full sequence...")
        await agent.emit_all_events()

    print("\n[MOCK AGENT] Done!")


if __name__ == "__main__":
    asyncio.run(main())
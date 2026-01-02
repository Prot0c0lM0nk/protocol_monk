#!/usr/bin/env python3
"""
Command Dispatcher for Protocol Monk
Handles slash commands with event-driven architecture.
"""
import logging
import os
from typing import Optional, Dict, List, Any

from agent.events import AgentEvents

# Define blessing constant locally if not imported
BLESSING = "☦ Go in peace. May your code compile without warning. ☦"


class CommandDispatcher:
    """Centralized dispatcher for slash commands."""

    def __init__(self, agent):
        self.agent = agent
        self.logger = logging.getLogger(__name__)
        self.event_bus = agent.event_bus

    async def dispatch(self, user_input: str) -> Optional[bool]:
        """Process slash commands."""
        if not user_input.startswith("/"):
            return None

        cmd = user_input.strip().lower()

        # Handle Commands
        if cmd == "/quit":
            await self.event_bus.emit(
                AgentEvents.INFO.value, {"message": BLESSING, "context": "shutdown"}
            )
            return False

        if cmd == "/help":
            await self._handle_help()
            return True

        if cmd == "/status":
            await self._handle_status()
            return True

        if cmd == "/clear":
            await self.agent.clear_conversation()
            return True

        if cmd.startswith("/file"):
            await self._handle_file_ingest()  # Renamed to reflect true purpose
            return True

        if cmd.startswith("/model"):
            await self._handle_model_switch()
            return True

        if cmd.startswith("/provider"):
            await self._handle_provider_switch()
            return True

        # Unknown command
        await self.event_bus.emit(
            AgentEvents.ERROR.value,
            {"message": f"Unknown command: {cmd}", "context": "command_error"},
        )
        return True

    # --- Command Handlers ---

    async def _handle_help(self):
        help_text = """The Protocol Commands:
/help     - Display this wisdom
/status   - View current state
/model    - Switch to a different model
/provider - Switch to a different provider
/clear    - Clear conversation history
/file     - Load a file into context (Context Injection)
/quit     - Exit with blessing"""

        await self.event_bus.emit(
            AgentEvents.INFO.value, {"message": help_text, "context": "help"}
        )

    async def _handle_status(self):
        stats = await self.agent.get_status()
        working_dir = self.agent.working_dir

        status_text = f"""Current State:
Model: {stats.get('current_model', 'Unknown')}
Provider: {stats.get('provider', 'Unknown')}
Working Directory: {working_dir.name}
   {working_dir}
   
Conversation: {stats.get('conversation_length', 0)} messages
Tokens: {stats.get('estimated_tokens', 0):,} / {stats.get('token_limit', 0):,}"""

        await self.event_bus.emit(
            AgentEvents.INFO.value, {"message": status_text, "context": "status"}
        )

    async def _handle_file_ingest(self):
        """Read a file and inject its content into the context window."""
        # 1. Prompt for path (without redundant INFO messages)
        file_path = await self._prompt_user("File path to read")

        if not file_path:
            return

        file_path = file_path.strip()

        # 2. Validate existence
        if not os.path.exists(file_path):
            await self.event_bus.emit(
                AgentEvents.ERROR.value, {"message": f"File not found: {file_path}"}
            )
            return

        if not os.path.isfile(file_path):
            await self.event_bus.emit(
                AgentEvents.ERROR.value, {"message": f"Not a file: {file_path}"}
            )
            return

        # 3. Read and Inject
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            filename = os.path.basename(file_path)

            # Inject as a user message with explicit system-like wrapper
            ingest_message = f"--- BEGIN FILE CONTENT: {filename} ---\n{content}\n--- END FILE CONTENT ---"

            # Use the context manager to add it directly
            self.agent.context_manager.add_message("user", ingest_message)

            await self.event_bus.emit(
                AgentEvents.INFO.value,
                {
                    "message": f"Ingested '{filename}' ({len(content)} chars) into context."
                },
            )

        except Exception as e:
            await self.event_bus.emit(
                AgentEvents.ERROR.value, {"message": f"Failed to read file: {e}"}
            )

    async def _handle_model_switch(self):
        """Switch models using the UI list display."""
        available = self.agent.model_manager.get_available_models()

        # 1. Send the data payload so PlainUI renders the blue list
        await self.event_bus.emit(
            AgentEvents.INFO.value,
            {
                "message": "Available Models",
                "data": list(available.values()),  # Send full list of model objects
                "context": "model_selection",
            },
        )

        # 2. Prompt for selection
        choice = await self._prompt_user("Select a model (number or name)")
        if not choice:
            return

        # 3. Resolve selection
        selected_model = self._resolve_selection(choice, list(available.keys()))

        if selected_model:
            await self.agent.set_model(selected_model)
            await self.event_bus.emit(
                AgentEvents.INFO.value, {"message": f"✔️ Switched to {selected_model}"}
            )
        else:
            await self.event_bus.emit(
                AgentEvents.ERROR.value, {"message": "Invalid model selection"}
            )

    async def _handle_provider_switch(self):
        """Switch providers and immediately trigger model selection."""
        # Hardcoded provider list (Phase 1)
        providers = ["ollama", "openrouter"]

        # 1. Display list
        await self.event_bus.emit(
            AgentEvents.INFO.value,
            {
                "message": "Available Providers",
                "data": providers,
                "context": "provider_selection",
            },
        )

        # 2. Prompt
        choice = await self._prompt_user("Select a provider")
        if not choice:
            return

        # 3. Resolve
        selected = self._resolve_selection(choice, providers)

        if selected:
            # Update the agent's state
            self.agent.current_provider = selected
            self.agent.model_manager.provider = selected

            await self.event_bus.emit(
                AgentEvents.INFO.value,
                {"message": f"Switched provider to {selected}"},
            )

            # 4. CHAINING: Automatically trigger model switch for the new provider
            # This ensures the user isn't stuck with an invalid model
            await self.event_bus.emit(
                AgentEvents.INFO.value,
                {"message": f"Please select a {selected} model:"},
            )
            await self._handle_model_switch()

        else:
            await self.event_bus.emit(
                AgentEvents.ERROR.value, {"message": "Invalid provider selection"}
            )

    # --- Helpers ---

    async def _prompt_user(self, prompt_text: str) -> str:
        """Helper to prompt via the agent's UI if available."""
        if self.agent.ui:
            return await self.agent.ui.prompt_user(prompt_text)
        return ""

    def _resolve_selection(self, choice: str, options: List[str]) -> Optional[str]:
        """Resolve a number (1-based) or string match to a valid option."""
        choice = choice.strip()
        if not choice:
            return None

        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(options):
                return options[idx]

        if choice in options:
            return choice

        return None

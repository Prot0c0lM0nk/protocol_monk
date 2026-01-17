#!/usr/bin/env python3
"""
Command Dispatcher for Protocol Monk
Handles slash commands with event-driven architecture.
"""
import logging
import os
import asyncio
from typing import Optional, Dict, List, Any

from agent.events import AgentEvents

# DEPRECATED: The model handles this now.
# BLESSING = "☦ Go in peace. May your code compile without warning. ☦"


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
            # Feature Upgrade: Deliberate Model Farewell
            await self._handle_quit_protocol()
            return True  # Handled (prevents service.py from double-processing)

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
            await self._handle_file_ingest()
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

    async def _handle_quit_protocol(self):
        """
        Orchestrates a graceful, model-driven shutdown.
        1. Prompts model for farewell.
        2. Waits for response.
        3. Signals UI to die.
        """
        # 1. Inject the "Director's Note" (Invisible to user, instruction to model)
        # We assume the user just typed "/quit", so we translate that intent.
        farewell_prompt = (
            "The user has issued the /quit command to disconnect. "
            "Please provide a brief, formal, and thematic monastic farewell/blessing "
            "before the connection is severed."
        )
        
        # We add this directly to context without triggering a UI event for the input
        await self.agent.context_manager.add_message("user", farewell_prompt)
        
        # 2. Trigger the Agent's Brain manually
        # This ensures the response is generated/streamed BEFORE we kill the app.
        try:
            await self.agent._run_cognitive_loop()
        except Exception as e:
            self.logger.error(f"Error during farewell generation: {e}")

        # 3. NOW we kill it.
        # This event tells RichUI to set running=False
        await self.event_bus.emit(
            AgentEvents.INFO.value, 
            {"message": "Connection Terminated.", "context": "shutdown"}
        )

    async def _handle_help(self):
        help_text = """The Protocol Commands:
/help     - Display this wisdom
/status   - View current state
/model    - Switch to a different model
/provider - Switch to a different provider
/clear    - Clear conversation history
/file     - Load a file into context
/quit     - Receive final blessing and exit"""
        await self.event_bus.emit(AgentEvents.INFO.value, {"message": help_text, "context": "help"})

    async def _handle_status(self):
        stats = await self.agent.get_status()
        working_dir = self.agent.working_dir
        status_text = f"""Current State:
Model: {stats.get('current_model', 'Unknown')}
Provider: {stats.get('provider', 'Unknown')}
Working Directory: {working_dir}
Conversation: {stats.get('conversation_length', 0)} messages
Tokens: {stats.get('estimated_tokens', 0):,} / {stats.get('token_limit', 0):,}"""
        await self.event_bus.emit(AgentEvents.INFO.value, {"message": status_text, "context": "status"})

    async def _handle_file_ingest(self):
        """Read a file and inject its content."""
        file_path = await self._prompt_user("File path to read")
        if not file_path: return

        file_path = file_path.strip()
        if not os.path.exists(file_path):
            await self.event_bus.emit(AgentEvents.ERROR.value, {"message": f"File not found: {file_path}"})
            return

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            filename = os.path.basename(file_path)
            ingest_message = f"--- BEGIN FILE CONTENT: {filename} ---\n{content}\n--- END FILE CONTENT ---"
            
            # Using Context Manager directly via Service
            await self.agent.context_manager.add_message("user", ingest_message)
            await self.event_bus.emit(AgentEvents.INFO.value, {"message": f"Ingested '{filename}' ({len(content)} chars)."})
        except Exception as e:
            await self.event_bus.emit(AgentEvents.ERROR.value, {"message": f"Failed to read file: {e}"})

    async def _handle_model_switch(self):
        available = self.agent.model_manager.get_available_models()
        await self.event_bus.emit(
            AgentEvents.INFO.value,
            {"message": "Available Models", "data": list(available.values()), "context": "model_selection"},
        )
        choice = await self._prompt_user("Select a model (number or name)")
        if not choice: return

        selected_model = self._resolve_selection(choice, list(available.keys()))
        if not selected_model:
            await self.event_bus.emit(AgentEvents.ERROR.value, {"message": "Invalid model selection"})
            return

        # Context Check
        model_info = available.get(selected_model)
        if model_info:
            stats = await self.agent.context_manager.get_stats()
            current_usage = stats.get("total_tokens", 0)
            report = self.agent.model_manager.assess_switch(current_usage, selected_model)

            if not report.safe:
                await self.event_bus.emit(AgentEvents.WARNING.value, {"message": f"⚠️ {report.message}"})
                await self.event_bus.emit(AgentEvents.INFO.value, {"message": "Options:\n1. Continue\n2. Cancel\n3. Clear Context"})
                action = await self._prompt_user("Choose action (1-3)")
                if action == "2": return
                elif action == "3": await self.agent.clear_conversation()
        
        await self.agent.set_model(selected_model)
        await self.event_bus.emit(
            AgentEvents.MODEL_SWITCHED.value,
            {"old_model": self.agent.current_model, "new_model": selected_model},
        )

    async def _handle_provider_switch(self):
        providers = ["ollama", "openrouter"]
        await self.event_bus.emit(
            AgentEvents.INFO.value,
            {"message": "Available Providers", "data": providers, "context": "provider_selection"},
        )
        choice = await self._prompt_user("Select a provider")
        if not choice: return

        selected = self._resolve_selection(choice, providers)
        if selected:
            old_provider = self.agent.current_provider
            
            # Switch Logic (Through Service)
            self.agent.model_manager.switch_provider(selected)
            self.agent.model_client.switch_provider(selected)
            self.agent.current_provider = selected
            
            await self.event_bus.emit(
                AgentEvents.PROVIDER_SWITCHED.value,
                {"old_provider": old_provider, "new_provider": selected},
            )
            # Chain model switch
            await self.event_bus.emit(AgentEvents.INFO.value, {"message": f"Please select a {selected} model:"})
            await self._handle_model_switch()
        else:
            await self.event_bus.emit(AgentEvents.ERROR.value, {"message": "Invalid provider"})

    # --- Helpers ---

    async def _prompt_user(self, prompt_text: str) -> str:
        """Event-driven prompt that waits for a response."""
        # 1. START LISTENING NOW (Before asking)
        response_future = asyncio.create_task(
            self.event_bus.wait_for(
                AgentEvents.INPUT_RESPONSE.value,
                timeout=None
            )
        )
        
        # 2. Emit Request
        await self.event_bus.emit(
            AgentEvents.INPUT_REQUESTED.value, 
            {"prompt": prompt_text}
        )
        
        # 3. Wait for the response
        try:
            response_data = await response_future
            return response_data.get("input", "")
        except asyncio.TimeoutError:
            return ""

    def _resolve_selection(self, choice: str, options: List[str]) -> Optional[str]:
        choice = choice.strip()
        if not choice: return None
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(options): return options[idx]
        if choice in options: return choice
        return None
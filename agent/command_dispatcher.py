#!/usr/bin/env python3
"""
Command Dispatcher Module

Centralized handling of slash commands to clean up main.py
"""

import logging
from typing import Dict, Optional

from agent.model_manager import RuntimeModelManager
from agent.monk import ProtocolAgent
from config.session import get_active_session

# Reuse the blessing from main.py
BLESSING = """☦ Go in peace. May your code compile without warning. ☦"""


class CommandDispatcher:
    """Centralized dispatcher for slash commands."""

    def __init__(self, agent: ProtocolAgent):
        self.agent = agent
        self.ui = agent.ui
        self.logger = logging.getLogger(__name__)

    async def dispatch(self, user_input: str) -> Optional[bool]:
        """Process slash commands and return appropriate signals."""
        if not user_input.startswith("/"):
            return None

        cmd = user_input.strip().lower()

        if cmd == "/quit":
            await self.ui.print_info(BLESSING)
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

        if cmd.startswith("/model"):
            await self._handle_model_switch()
            return True

        await self.ui.print_error("Unknown command")
        return True

    async def _handle_help(self):
        """Display help information."""
        help_text = """The Protocol Commands:

/help     - Display this wisdom
/status   - View current state
/model    - Switch to a different model
/clear    - Clear conversation history
/quit     - Exit with blessing
"""
        await self.ui.print_info(help_text)

    async def _handle_status(self):
        """Display agent status."""
        stats = await self.agent.get_status()
        session = get_active_session()

        env_info = "system"
        if session.preferred_env:
            env_info = f"conda: {session.preferred_env}"
        elif session.venv_path:
            env_info = f"venv: {session.venv_path}"
        elif session.is_python_project:
            env_info = "system Python"
        else:
            env_info = "general directory"

        status_text = f"""Current State:

🤖 Model: {stats['current_model']}
🔌 Provider: {stats['provider']}
📁 Working Directory: {session.directory_name}
   {stats['working_dir']}
🐍 Environment: {env_info}

💬 Conversation Length: {stats['conversation_length']} messages
🧮 Token Usage: {stats['estimated_tokens']:,} / {stats['token_limit']:,} ({(stats['estimated_tokens']/stats['token_limit']*100):.1f}%)
"""
        await self.ui.print_info(status_text)

    async def _display_model_list(self, available_models: Dict):
        """Print the list of available models."""
        await self.ui.print_info("Available Models:")
        for i, model_name in enumerate(available_models.keys(), 1):
            m = available_models[model_name]
            # Handle both object and dict access safely
            prov = getattr(
                m,
                "provider",
                m.get("provider", "unknown") if isinstance(m, dict) else "unknown",
            )
            ctx = getattr(
                m,
                "context_window",
                m.get("context_window", 0) if isinstance(m, dict) else 0,
            )
            await self.ui.print_info(f"  {i}. {model_name} ({prov}, {ctx:,} tokens)")

    async def _get_model_choice(self, available_models: Dict) -> Optional[str]:
        """Prompt user and parse selection."""
        try:
            choice = await self.ui.prompt_user(
                "\nSelect a model (enter number or name): "
            )
            choice = choice.strip()
            model_list = list(available_models.keys())

            if choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(model_list):
                    return model_list[idx]
                await self.ui.print_error("Invalid selection.")
                return None

            if choice in available_models:
                return choice

            await self.ui.print_error(f"Model '{choice}' not found.")
            return None

        except ValueError as e:
            await self.ui.print_error(f"Invalid model selection: {e}")
            return None

    async def _handle_guardrails(
        self, selected_model: str, model_manager: RuntimeModelManager
    ) -> bool:
        """Check token limits and prune if necessary. Returns True if switch succeeds."""
        current_tokens = self.agent.context_manager.get_total_tokens()
        switch_report = model_manager.assess_switch(current_tokens, selected_model)

        if switch_report.safe:
            await self.agent.set_model(selected_model)
            await self.ui.print_info(f"✅ Model switched to: {selected_model}")
            return True

        # Handle Unsafe Switch
        await self.ui.print_warning(f"⚠️  Context Warning: {switch_report.message}")
        await self.ui.print_warning(f"Current tokens: {switch_report.current_tokens:,}")
        await self.ui.print_warning(f"Target limit: {switch_report.target_limit:,}")

        action = await self.ui.prompt_user("Prune, Archive, or Cancel? (p/a/c): ")
        action = action.strip().lower()

        if action in ["p", "prune"]:
            self.agent.context_manager.prune_context(
                "strict", switch_report.target_limit
            )
            await self.agent.set_model(selected_model)
            await self.ui.print_info(
                f"✅ Context pruned and model switched to: {selected_model}"
            )
            return True

        if action in ["a", "archive"]:
            self.agent.context_manager.prune_context(
                "archive", switch_report.target_limit
            )
            await self.agent.set_model(selected_model)
            await self.ui.print_info(
                f"✅ Context archived and model switched to: {selected_model}"
            )
            return True

        await self.ui.print_info("Model switch cancelled.")
        return False

    async def _handle_model_switch(self):
        """Handle the model switch command with guardrail workflow."""
        try:
            model_manager = RuntimeModelManager()
            available_models = model_manager.get_available_models()

            await self._display_model_list(available_models)
            target_model = await self._get_model_choice(available_models)

            if target_model:
                await self._handle_guardrails(target_model, model_manager)

        except KeyError as e:
            await self.ui.print_error(f"Model configuration error: {e}")
        except RuntimeError as e:
            await self.ui.print_error(f"Runtime error during model switch: {e}")
        except Exception as e:  # pylint: disable=broad-exception-caught
            await self.ui.print_error(f"Unexpected error during model switch: {e}")
            self.logger.error("Unexpected error in model switch: %s", e, exc_info=True)

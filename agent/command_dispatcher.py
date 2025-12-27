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

from exceptions import ModelConfigurationError

# Reuse the blessing from main.py
BLESSING = """☦ Go in peace. May your code compile without warning. ☦"""


class CommandDispatcher:
    """Centralized dispatcher for slash commands."""

    def __init__(self, agent: ProtocolAgent):
        self.agent = agent
        self.ui = agent.ui
        self.logger = logging.getLogger(__name__)

    async def dispatch(self, user_input: str) -> Optional[bool]:
        """
        Process slash commands and return appropriate signals.

        Args:
            user_input: The user's input string

        Returns:
            Optional[bool]: True if command was handled, None if not a command
        """
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

        if cmd.startswith("/file"):
            await self._handle_file_upload()
            return True

        if cmd.startswith("/model"):
            await self._handle_model_switch()
            return True

        if cmd.startswith("/provider"):
            await self._handle_provider_switch()
            return True
        await self.ui.print_error("Unknown command")
        return True

    async def _handle_help(self):
        """Display help information."""
        help_text = """The Protocol Commands:

/help     - Display this wisdom
/status   - View current state
/model    - Switch to a different model
/provider - Switch to a different provider (ollama/openrouter)
/clear    - Clear conversation history
/file     - Upload a file to the workspace
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

        token_percentage = stats["estimated_tokens"] / stats["token_limit"] * 100

        status_text = f"""Current State:

🤖 Model: {stats['current_model']}
🔌 Provider: {stats['provider']}
📁 Working Directory: {session.directory_name}
   {stats['working_dir']}
🐍 Environment: {env_info}

💬 Conversation Length: {stats['conversation_length']} messages
🧮 Token Usage: {stats['estimated_tokens']:,} / {stats['token_limit']:,} \
            ({token_percentage:.1f}%)
"""
        await self.ui.print_info(status_text)

    async def _display_model_list(self, available_models: Dict):
        models_list = list(available_models.values())
        # Use the generic method
        await self.ui.display_selection_list("Available Models", models_list)

    async def _get_model_choice(self, available_models: Dict) -> Optional[str]:
        """
        Prompt user and parse selection.

        Args:
            available_models: Dictionary of available models

        Returns:
            Optional[str]: Selected model name or None if invalid
        """
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
        """
        Check token limits and prune if necessary. Returns True if switch succeeds.

        Args:
            selected_model: Name of the selected model
            model_manager: Runtime model manager instance

        Returns:
            bool: True if switch succeeds, False otherwise
        """
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

    async def _handle_file_upload(self):
        """Handle file upload command with user interaction."""
        await self.ui.print_info("📁 File Upload Protocol")
        await self.ui.print_info("Enter the path to the file you want to upload:")

        file_path = await self.ui.prompt_user("File path: ")
        file_path = file_path.strip()

        if not file_path:
            await self.ui.print_error("No file path provided.")
            return

        # Import here to avoid circular imports
        import os
        import shutil
        from pathlib import Path

        # Check if file exists
        if not os.path.exists(file_path):
            await self.ui.print_error(f"File not found: {file_path}")
            return

        if not os.path.isfile(file_path):
            await self.ui.print_error(f"Path is not a file: {file_path}")
            return

        # Get workspace directory from session
        session = get_active_session()
        workspace_dir = str(session.working_dir)

        # Create filename and destination path
        filename = os.path.basename(file_path)
        destination = os.path.join(workspace_dir, filename)

        # Check if file already exists
        if os.path.exists(destination):
            overwrite = await self.ui.prompt_user(
                f"File '{filename}' already exists. Overwrite? (y/n): "
            )
            if overwrite.strip().lower() != "y":
                await self.ui.print_info("File upload cancelled.")
                return

        try:
            # Copy the file to workspace
            shutil.copy2(file_path, destination)

            # Get file size for confirmation
            file_size = os.path.getsize(destination)
            size_str = f"{file_size:,} bytes"
            if file_size > 1024:
                size_str = f"{file_size / 1024:.1f} KB"
            if file_size > 1024 * 1024:
                size_str = f"{file_size / (1024 * 1024):.1f} MB"

            # Success messages
            await self.ui.print_info("✅ File uploaded successfully!")
            await self.ui.print_info(f"📄 {filename} ({size_str})")
            await self.ui.print_info(f"📍 Location: {destination}")

            # Add file content to conversation
            try:
                with open(destination, "r", encoding="utf-8") as f:
                    file_content = f.read()

                # Add file content to conversation with appropriate formatting
                file_info = f"File uploaded: {filename}\n```\n{file_content}\n```"
                await self.agent.context_manager.add_user_message(
                    file_info, importance=4
                )
                await self.ui.print_info(
                    "📖 File content added to conversation context"
                )

            except UnicodeDecodeError:
                # Handle binary files gracefully
                file_info = (
                    f"File uploaded: {filename} (binary file, content not displayed)"
                )
                await self.agent.context_manager.add_user_message(
                    file_info, importance=4
                )
                await self.ui.print_info(
                    "📎 Binary file uploaded (content not displayed)"
                )
            except Exception as e:
                self.logger.warning(f"Could not add file content to conversation: {e}")
                # Still report success since file was uploaded

            # Log the file upload
            self.logger.info(
                f"File uploaded: {filename} ({file_size} bytes) to {destination}"
            )

        except PermissionError:
            await self.ui.print_error("Permission denied. Check file access rights.")
        except shutil.SameFileError:
            await self.ui.print_info("File is already in the workspace.")
        except Exception as ex:
            await self.ui.print_error(f"File upload failed: {str(ex)}")
            self.logger.error("File upload error: %s", ex, exc_info=True)

    async def _handle_model_switch(self):
        """Handle the model switch command with guardrail workflow."""
        try:
            model_manager = RuntimeModelManager(provider=self.agent.current_provider)
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

    async def _handle_provider_switch(self):
        """Handle provider switching with user interaction and validation."""
        try:
            # 1. Display Available Providers
            available_providers = ["ollama", "openrouter"]
            current_provider = (
                self.agent.model_client.current_provider
                if self.agent.model_client
                else "unknown"
            )

            # Use the unified display method
            await self.ui.display_selection_list("Available Providers", available_providers)

            # The prompt will auto-fill from the TUI modal selection
            choice = await self.ui.prompt_user("Select a provider (enter number or name): ")

            # 2. Get User Provider Choice
            choice = await self.ui.prompt_user(
                "\nSelect a provider (enter number or name): "
            )
            choice = choice.strip().lower()

            selected_provider = None
            if choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(available_providers):
                    selected_provider = available_providers[idx]
                else:
                    await self.ui.print_error("Invalid selection.")
                    return
            elif choice in available_providers:
                selected_provider = choice
            else:
                await self.ui.print_error(f"Provider '{choice}' not found.")
                return

            if selected_provider == current_provider:
                await self.ui.print_info(f"Already using provider: {selected_provider}")
                return

            # 3. Validate Provider Requirements (e.g., API Keys)
            if selected_provider == "openrouter":
                from config.static import settings
                if not settings.environment.openrouter_api_key:
                    await self.ui.print_error(
                        "OpenRouter API key not configured. Set OPENROUTER_API_KEY environment variable."
                    )
                    return

            # 4. Show Models for the New Provider
            target_model_manager = RuntimeModelManager(provider=selected_provider)
            target_models = target_model_manager.get_available_models()

            if not target_models:
                await self.ui.print_warning(
                    f"No models available for {selected_provider}. Staying with current provider."
                )
                return

            await self.ui.print_info(f"\nAvailable models for {selected_provider}:")
            await self._display_model_list(target_models, current_provider=selected_provider)

            # 5. Optional Model Selection Flow (Simplified)
            select_model_prompt = await self.ui.prompt_user(
                f"Select a specific model for {selected_provider} now? (Y/n): "
            )
            
            selected_model = None
            if select_model_prompt.strip().lower() not in ["n", "no"]:
                # User wants to pick a specific model
                model_choice = await self.ui.prompt_user(
                    f"\nSelect a model (enter number or name): "
                )
                model_choice = model_choice.strip()

                model_list = list(target_models.keys())
                if model_choice.isdigit():
                    idx = int(model_choice) - 1
                    if 0 <= idx < len(model_list):
                        selected_model = model_list[idx]
                elif model_choice in target_models:
                    selected_model = model_choice
                
                if not selected_model:
                    await self.ui.print_error("Invalid model selection. Staying with current provider.")
                    return
            else:
                # User skipped selection; use the first available model as a default
                selected_model = list(target_models.keys())[0]
                await self.ui.print_info(f"Using default model for {selected_provider}: {selected_model}")

            # 6. Perform the Switch
            await self.ui.print_info(f"Switching to {selected_provider} with model {selected_model}...")
            
            # Update agent's model attribute before calling set_provider
            self.agent.current_model = selected_model

            try:
                success = await self.agent.set_provider(selected_provider)
                if success:
                    await self.ui.print_info(f"✅ Provider switched to: {selected_provider}")
                    await self.ui.print_info(f"   Model: {self.agent.current_model}")
            except Exception as e:
                await self.ui.print_error(f"Provider switch failed: {str(e)}")
                self.logger.error("Provider switch error: %s", str(e), exc_info=True)

        except Exception as e:
            await self.ui.print_error(f"Unexpected error during provider switch: {str(e)}")
            self.logger.error("Provider switch unexpected error: %s", str(e), exc_info=True)

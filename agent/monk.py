#!/usr/bin/env python3
"""
Protocol Monk Core Agent
========================
The central nervous system of the application.
Orchestrates the Model, the Tools, and the Context via TAOR Loop.
"""
import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

# Agent Components
from agent.context import ContextManager
from exceptions import ContextValidationError, ModelConfigurationError
from exceptions import ModelResponseParseError, ModelRateLimitError
from exceptions import ModelConfigurationError
from agent.model_client import ModelClient
from agent.model_manager import RuntimeModelManager
from agent.scratch_manager import ScratchManager
from agent.taor_loop import TAORLoop
from agent.tool_executor import ExecutionSummary, ToolExecutor
from config.static import settings
from ui.base import UI
from ui.plain import PlainUI
from utils.enhanced_logger import EnhancedLogger
from utils.proper_tool_calling import ProperToolCalling


class ProtocolAgent:
    """Core agent that handles the main interaction loop."""

    def __init__(
        self,
        working_dir: str = ".",
        model_name: str = settings.model.default_model,
        provider: str = "ollama",
        tool_registry=None,
        ui: Optional[UI] = None,
    ):
        """
        Initialize the core agent with configuration options.

        Args:
            working_dir: Working directory for file operations (default: ".")
            model_name: LLM model to use (default: from settings)
            provider: LLM provider to use (default: "ollama")
            tool_registry: Tool registry instance (optional)
            ui: User interface instance (optional)
            ModelConfigurationError: If model client initialization fails
        """
        self.working_dir = Path(working_dir).resolve()
        self.current_model = model_name
        self.current_provider = provider
        self.ui = ui or PlainUI()
        self.logger = logging.getLogger(__name__)

        self.enhanced_logger = EnhancedLogger(self.working_dir)

        # 1. Components
        self.context_manager = ContextManager(
            max_tokens=settings.model.context_window,
            working_dir=self.working_dir,
            tool_registry=tool_registry,
        )
        self.proper_tool_caller = (
            ProperToolCalling(tool_registry) if tool_registry else None
        )

        # Wiring
        if tool_registry:
            tool_registry.context_manager = self.context_manager

        self.model_manager = RuntimeModelManager()

        # 2. Scratch Manager (Fixes Infinite Writes)
        self.scratch_manager = ScratchManager(self.working_dir)

        try:
            self.model_client = ModelClient(model_name=model_name, provider=provider)
        except ModelConfigurationError as e:
            print(f"Error: Failed to initialize model client: {e.message}")
            raise

        self.tool_executor = ToolExecutor(
            tool_registry=tool_registry,
            working_dir=self.working_dir,
            auto_confirm=False,
            ui_callback=self._handle_ui_event,
        )

        # 3. TAOR Loop (The Immutable Orchestrator)
        self.taor_loop = TAORLoop(self)

    async def async_initialize(self):
        """
        Initialize async components like tool registry and context manager.
        """
        if hasattr(self.tool_executor.tool_registry, "async_initialize"):
            await self.tool_executor.tool_registry.async_initialize()
        await self.context_manager.async_initialize()

    async def _handle_ui_event(self, event: str, data: Dict[str, Any]) -> Any:
        """
        Handle UI events triggered by tool execution.

        Args:
            event: Type of UI event (confirm, progress, result, etc.)
            data: Event data dictionary

        Returns:
            Any: Response based on event type (None for most events)
        """
        # Pass-through to UI
        if event == "confirm":
            return await self.ui.confirm_tool_call(
                data["tool_call"], data["auto_confirm"]
            )

        # Events that do not return a value
        if event == "execution_start":
            await self.ui.display_execution_start(data["count"])
        elif event == "progress":
            await self.ui.display_progress(data["current"], data["total"])
        elif event == "tool_error":
            await self.ui.print_error(data["error"])
        elif event == "tool_rejected":
            await self.ui.print_info("Action rejected by user")
        elif event == "tool_modified":
            await self.ui.print_info("Tool parameters modified by user")
        elif event == "result":
            await self.ui.display_tool_result(data["result"], data["tool_name"])
        elif event == "task_complete":
            await self.ui.display_task_complete(data.get("summary", ""))
        elif event == "auto_confirm_changed":
            await self.ui.set_auto_confirm(data["value"])
        return None

    async def process_request(self, user_input: str) -> bool:
        """
        Delegate to TAOR Loop.

        Args:
            user_input: User's input string

        Returns:
            bool: Result from TAOR loop execution
        """
        return await self.taor_loop.run_loop(user_input)

    # --- Helpers called by TAOR Loop ---

    async def _prepare_context(self) -> Optional[List[Dict]]:
        """
        Retrieve and log the current context for the model.

        Returns:
            Optional[List[Dict]]: Context for model, None if error
        """
        try:
            context = await self.context_manager.get_context(self.current_model)

            # Remove duplicate system messages (keep only the first one)
            seen_system = False
            filtered = []
            for msg in context:
                if msg.get("role") == "system":
                    if seen_system:
                        continue  # skip duplicates
                    seen_system = True
                filtered.append(msg)
            context = filtered

            self.logger.error("FILTERED MESSAGES: %s", json.dumps(filtered, indent=2))

            self.enhanced_logger.log_context_snapshot(context)
            return context
        except ContextValidationError as e:
            await self.ui.print_error(f"Context validation error: {e}")
            await self.ui.print_error(
                "Please clear the context with '/clear' command and try again."
            )
            return None
        except Exception as e:
            await self.ui.print_error(f"Error getting context: {e}")
            return None

    async def _get_model_response(self, context: List[Dict]):
        """
        Stream the model response and handle errors with fallback logic.

        Args:
            context: Conversation context for the model

        Returns:
            str: Full response text, None if interrupted, False if error
        """
        await self.ui.start_thinking()
        full_response = ""
        try:
            # Get tool schemas if available
            tools = None
            if self.proper_tool_caller:
                tools = self.proper_tool_caller.get_tools_schema()

            async for chunk in self.model_client.get_response_async(
                context, stream=True, tools=tools
            ):
                # Handle both text and dict responses
                if isinstance(chunk, str):
                    full_response += chunk
                    await self.ui.print_stream(chunk)
                elif isinstance(chunk, dict):
                    # Store tool call response for parsing
                    full_response = chunk  # This will be processed by _parse_response

            # Save Assistant thought
            if full_response:
                await self.context_manager.add_message(
                    "assistant",
                    (
                        full_response
                        if isinstance(full_response, str)
                        else "Tool calls requested"
                    ),
                )
            return full_response
        except ModelRateLimitError as e:
            e.log_error()
            await self.ui.print_warning(e.user_hint)
            await asyncio.sleep(e.retry_after)
            return await self._get_model_response(context)  # Retry
        except ModelResponseParseError as e:
            e.log_error()
            await self.ui.print_error(
                "Model returned invalid data. Using fallback response."
            )
            fallback_response = "Fallback: I encountered an error processing your request. Please try again."
            await self.context_manager.add_message("assistant", fallback_response)
            return fallback_response
        except Exception as e:  # pylint: disable=broad-exception-caught
            self.logger.exception("Model unavailable. Using fallback response.")
            await self.ui.print_error("Model unavailable. Using fallback response.")
            fallback_response = (
                "Fallback: The model is currently unavailable. Please try again later."
            )
            await self.context_manager.add_message("assistant", fallback_response)
            return fallback_response
        except KeyboardInterrupt:
            await self.ui.print_warning("\n🛑 Interrupted.")
            return None
        finally:
            # Ensure thinking spinner is always stopped
            await self.ui.stop_thinking()

    def _parse_response(
        self, response_data: Union[str, Dict]
    ) -> Tuple[List[Dict], bool]:
        """
        Parse response and return (actions, has_json_content).
        Handles both text responses and API tool calls.

        Args:
            response_data: Response text or API response dict

        Returns:
            Tuple[List[Dict], bool]: Actions list and JSON content flag
        """
        # Handle API tool calls (new path)
        print(f"[DEBUG] _parse_response received: {type(response_data)}")
        if isinstance(response_data, dict):
            print(f"[DEBUG] Dict keys: {list(response_data.keys())}")
            if "tool_calls" in response_data:
                print(f"[DEBUG] Found tool_calls: {response_data['tool_calls']}")
        if isinstance(response_data, dict):
            tool_calls = self.proper_tool_caller.extract_tool_calls(response_data)
            actions = []
            for tool_call in tool_calls:
                action = {
                    "action": tool_call.action,
                    "parameters": tool_call.parameters,
                    "reasoning": tool_call.reasoning,
                }
                actions.append(action)
            return actions, len(actions) > 0

        # Handle text responses (existing path for compatibility)

        # No text fallback - we only use API tool calling now
        return [], False

    async def _record_results(self, summary: ExecutionSummary) -> bool:
        """
        Record results and return True if any failures occurred.

        Args:
            summary: Execution summary with tool results

        Returns:
            bool: True if any failures occurred, False otherwise
        """
        had_failure = False
        for result in summary.results:
            await self.context_manager.add_message("tool", result.output, importance=5)

            if not result.success:
                had_failure = True
        return had_failure

    # --- Legacy Support Methods ---
    async def clear_conversation(self):
        """
        Reset the context manager and UI.
        """
        await self.context_manager.clear()
        await self.ui.print_info("✓ Cleared.")

    async def get_status(self) -> Dict:
        """
        Return the current status of the agent, context, and model.

        Returns:
            Dict: Status information including working directory, model, tokens, etc.
        """
        context_stats = await self.context_manager.get_stats()
        return {
            "working_dir": str(self.working_dir),
            "current_model": self.current_model,
            "conversation_length": context_stats["total_messages"],
            "estimated_tokens": context_stats["total_tokens"],
            "token_limit": self.context_manager.max_tokens,
            "provider": self.model_client.current_provider,
        }

    async def set_model(self, model_name: str):
        """
        Switch the current model and update context limits.

        Args:
            model_name: Name of the model to switch to
        """
        self.current_model = model_name
        self.model_client.set_model(model_name)
        model_manager = RuntimeModelManager()
        model_info = model_manager.get_available_models().get(model_name)
        if model_info:
            self.context_manager.accountant.max_tokens = model_info.context_window
            self.context_manager.pruner.max_tokens = model_info.context_window

    async def set_provider(self, provider: str) -> bool:
        """
        Switch the current provider while maintaining the same model.

        Args:
            provider: Name of the provider to switch to ("ollama" or "openrouter")

        Returns:
            bool: True if switch was successful, False otherwise

        Raises:
            ProviderConfigurationError: If provider is not available or misconfigured
        """
        try:
            # Validate provider
            if provider not in ["ollama", "openrouter"]:
                raise ModelConfigurationError(
                    f"Unknown provider: {provider}. Available: ollama, openrouter",
                    details={"requested_provider": provider},
                )

            # Check provider requirements
            if provider == "openrouter":
                if not settings.environment.openrouter_api_key:
                    raise ModelConfigurationError(
                        "OpenRouter API key not configured. Set OPENROUTER_API_KEY environment variable.",
                        details={"provider": provider},
                    )

            # Get current model before switching
            current_model = self.current_model

            # Switch provider using model client's switch_provider method
            self.model_client.switch_provider(provider)

            # Re-initialize the model with new provider
            await self.set_model(current_model)

            self.logger.info(
                f"Provider switched to: {provider} with model: {current_model}"
            )
            return True

        except Exception as e:
            self.logger.error(f"Provider switch failed: {e}")
            if isinstance(e, ModelConfigurationError):
                raise
            else:
                raise ModelConfigurationError(
                    f"Failed to switch provider to {provider}: {e}",
                    details={"provider": provider, "original_error": str(e)},
                ) from e

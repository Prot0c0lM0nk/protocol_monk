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
from agent.events import EventBus, AgentEvents, get_event_bus
from agent.interfaces import (
    AgentInterface,
    AgentResponse,
    CommandResult,
    ToolExecutionRequest,
    ToolExecutionResult,
    UserInputRequest,
    UserInputResponse,
)
from utils.enhanced_logger import EnhancedLogger
from utils.proper_tool_calling import ProperToolCalling


class ProtocolAgent(AgentInterface):
    """Core agent that handles the main interaction loop without UI dependencies."""

    def __init__(
        self,
        working_dir: str = ".",
        model_name: str = settings.model.default_model,
        provider: str = "ollama",
        tool_registry=None,
        event_bus: Optional[EventBus] = None,
        ui=None,
    ):
        self.working_dir = Path(working_dir).resolve()
        self.current_model = model_name
        self.current_provider = provider
        self.event_bus = event_bus or get_event_bus()
        self.ui = ui
        self.logger = logging.getLogger(__name__)
        self.enhanced_logger = EnhancedLogger(self.working_dir)

        self.model_manager = RuntimeModelManager(provider=provider)
        model_info = self.model_manager.get_available_models().get(model_name)
        model_context_window = (
            model_info.context_window if model_info else settings.model.context_window
        )

        self.context_manager = ContextManager(
            max_tokens=model_context_window,
            working_dir=self.working_dir,
            tool_registry=tool_registry,
        )

        self.proper_tool_caller = (
            ProperToolCalling(tool_registry) if tool_registry else None
        )
        if tool_registry:
            tool_registry.context_manager = self.context_manager

        self.scratch_manager = ScratchManager(self.working_dir)
        self.model_client = ModelClient(model_name=model_name, provider=provider)

        # NEW: PASS UI TO EXECUTOR
        self.tool_executor = ToolExecutor(
            tool_registry=tool_registry,
            working_dir=self.working_dir,
            auto_confirm=False,
            event_bus=self.event_bus,
            ui=self.ui,
        )

        self.taor_loop = TAORLoop(self)

    async def async_initialize(self):
        """
        Initialize async components like tool registry and context manager.
        """
        if hasattr(self.tool_executor.tool_registry, "async_initialize"):
            await self.tool_executor.tool_registry.async_initialize()
        await self.context_manager.async_initialize()

    async def _handle_agent_event(self, event: str, data: Dict[str, Any]) -> Any:
        """
        Handle agent events by emitting them to the event bus.

        Args:
            event: Type of agent event (confirm, progress, result, etc.)
            data: Event data dictionary

        Returns:
            Any: Response based on event type (None for most events)
        """
        # Map tool executor events to agent events
        if event == "confirm":
            # This requires UI interaction, will be handled by event bus subscribers
            tool_request = ToolExecutionRequest(
                tool_name=data["tool_call"]["name"],
                parameters=data["tool_call"]["arguments"],
                tool_call_id=data["tool_call"].get("id"),
            )
            # Emit confirmation request and wait for response
            # For now, we'll use the event bus to handle this
            return await self._request_tool_confirmation(tool_request)

        # Events that emit but don't return values
        event_mapping = {
            "execution_start": AgentEvents.TOOL_EXECUTION_START,
            "progress": AgentEvents.TOOL_EXECUTION_PROGRESS,
            "tool_error": AgentEvents.ERROR,
            "tool_rejected": AgentEvents.INFO,
            "tool_modified": AgentEvents.INFO,
            "result": AgentEvents.TOOL_RESULT,
            "task_complete": AgentEvents.TOOL_EXECUTION_COMPLETE,
            "auto_confirm_changed": AgentEvents.STATUS_CHANGED,
        }

    async def execute_command(
        self, command: str, args: Dict[str, Any]
    ) -> CommandResult:
        """Execute a slash command via the command dispatcher."""
        # Build the command string from command name and args
        cmd_string = f"/{command}"
        if args:
            # Format args as space-separated key=value pairs
            arg_parts = []
            for key, value in args.items():
                if isinstance(value, str) and " " in value:
                    arg_parts.append(f'{key}="{value}"')
                else:
                    arg_parts.append(f"{key}={value}")
            cmd_string += " " + " ".join(arg_parts)

        # Dispatch the command
        result = await self.command_dispatcher.dispatch(cmd_string)

        # Convert result to CommandResult
        success = result is not None
        message = (
            "Command executed successfully"
            if success
            else f"Unknown command: {command}"
        )
        return CommandResult(success=success, message=message)

    async def execute_tool(
        self, tool_request: ToolExecutionRequest
    ) -> ToolExecutionResult:
        """Execute a single tool with user approval via the tool executor."""
        # Use the tool executor to handle the tool request
        result = await self.tool_executor.execute_tool(tool_request)
        return result

        if event in event_mapping:
            agent_event = event_mapping[event]
            await self.event_bus.emit(agent_event.value, data)

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
            # FIX: Pass provider to get_context
            context = await self.context_manager.get_context(
                self.current_model, self.current_provider
            )

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

            self.logger.debug("FILTERED MESSAGES: %s", json.dumps(filtered, indent=2))

            self.enhanced_logger.log_context_snapshot(filtered)
            return filtered
        except ContextValidationError as e:
            await self.event_bus.emit(
                AgentEvents.ERROR.value,
                {
                    "message": f"Context validation error: {e}",
                    "context": "context_validation",
                },
            )
            await self.event_bus.emit(
                AgentEvents.ERROR.value,
                {
                    "message": "Please clear the context with '/clear' command and try again.",
                    "context": "context_validation",
                },
            )
            return None
        except Exception as e:
            await self.event_bus.emit(
                AgentEvents.ERROR.value,
                {
                    "message": f"Error getting context: {e}",
                    "context": "context_retrieval",
                },
            )
            return None

    async def _get_model_response(self, context: List[Dict]):
        """
        Stream the model response and handle errors with fallback logic.
        """
        await self.event_bus.emit(AgentEvents.THINKING_STARTED.value, {})
        accumulated_text = ""
        tool_calls_accumulator = None
        try:
            # Get tool schemas if available
            tools = None
            if self.proper_tool_caller:
                tools = self.proper_tool_caller.get_tools_schema()

            async for chunk in self.model_client.get_response_async(
                context, stream=True, tools=tools
            ):
                # Handle Thinking Packets First
                if isinstance(chunk, dict) and chunk.get("type") == "thinking":
                    await self.event_bus.emit(
                        AgentEvents.STREAM_CHUNK.value, {"thinking": chunk["content"]}
                    )
                    continue

                # Handle both text and dict responses
                if isinstance(chunk, str):
                    accumulated_text += chunk
                    await self.event_bus.emit(
                        AgentEvents.STREAM_CHUNK.value, {"chunk": chunk}
                    )
                elif isinstance(chunk, dict):
                    # Check for tool calls and accumulate separately
                    if "tool_calls" in chunk:
                        self.logger.info(f"Received tool call chunk (dict): {chunk}")
                        # Merge tool call chunks instead of overwriting
                        if tool_calls_accumulator is None:
                            tool_calls_accumulator = {"tool_calls": []}

                        if "tool_calls" not in tool_calls_accumulator:
                            tool_calls_accumulator["tool_calls"] = []

                        # Merge each tool call by index
                        for i, new_tc in enumerate(chunk["tool_calls"]):
                            if i < len(tool_calls_accumulator["tool_calls"]):
                                # Merge with existing tool call
                                existing_tc = tool_calls_accumulator["tool_calls"][i]
                                if new_tc.get("id"):
                                    existing_tc["id"] = new_tc["id"]
                                if new_tc.get("type"):
                                    existing_tc["type"] = new_tc["type"]
                                if new_tc.get("function"):
                                    if "function" not in existing_tc:
                                        existing_tc["function"] = {}
                                    if new_tc["function"].get("name"):
                                        existing_tc["function"]["name"] = new_tc[
                                            "function"
                                        ]["name"]
                                    if new_tc["function"].get("arguments"):
                                        # Append arguments (streaming format)
                                        existing_args = existing_tc["function"].get(
                                            "arguments", ""
                                        )
                                        new_args = new_tc["function"]["arguments"]
                                        existing_tc["function"]["arguments"] = (
                                            existing_args + new_args
                                        )
                            else:
                                # Add new tool call
                                tool_calls_accumulator["tool_calls"].append(new_tc)

                        self.logger.info(
                            f"Merged tool_calls_accumulator: {tool_calls_accumulator}"
                        )
                    else:
                        self.logger.debug(
                            f"Received dict chunk (not tool call): {chunk}"
                        )
                        accumulated_text = str(chunk)
                elif isinstance(chunk, list):
                    # Handle list responses (tool calls in list format)
                    self.logger.info(f"Received list tool call chunk: {chunk}")
                    tool_calls_accumulator = chunk
                elif hasattr(chunk, "message"):
                    self.logger.info(
                        f"Received Ollama response object with message: {chunk.message}"
                    )
                    if (
                        hasattr(chunk.message, "tool_calls")
                        and chunk.message.tool_calls
                    ):
                        self.logger.info(
                            f"Ollama response has tool_calls: {chunk.message.tool_calls}"
                        )
                        tool_calls_accumulator = chunk
                    elif hasattr(chunk.message, "content") and chunk.message.content:
                        self.logger.debug(
                            f"Ollama response has content: {chunk.message.content}"
                        )
                        accumulated_text += chunk.message.content
                    else:
                        self.logger.warning(
                            f"Ollama response has no tool_calls or content"
                        )
                else:
                    self.logger.warning(
                        f"Received unknown chunk type: {type(chunk)}, content: {chunk}"
                    )
            # Return tool calls if present, otherwise text
            if tool_calls_accumulator:
                self.logger.info(
                    f"Processing tool calls accumulator: {tool_calls_accumulator}"
                )
                # Normalize tool calls from different formats
                tool_calls = []
                if isinstance(tool_calls_accumulator, list):
                    tool_calls = tool_calls_accumulator
                elif isinstance(tool_calls_accumulator, dict):
                    # Check OpenAI/OpenRouter format: choices[0].message.tool_calls
                    if (
                        "choices" in tool_calls_accumulator
                        and tool_calls_accumulator["choices"]
                    ):
                        message = tool_calls_accumulator["choices"][0].get(
                            "message", {}
                        )
                        if "tool_calls" in message:
                            tool_calls = message["tool_calls"]
                    # Check Ollama format: message.tool_calls
                    elif (
                        "message" in tool_calls_accumulator
                        and "tool_calls" in tool_calls_accumulator["message"]
                    ):
                        tool_calls = tool_calls_accumulator["message"]["tool_calls"]
                    # Check top-level (fallback)
                    elif "tool_calls" in tool_calls_accumulator:
                        tool_calls = tool_calls_accumulator["tool_calls"]
                elif hasattr(tool_calls_accumulator, "message"):
                    # Handle Ollama response objects
                    if hasattr(tool_calls_accumulator.message, "tool_calls"):
                        tool_calls = tool_calls_accumulator.message.tool_calls
                        self.logger.info(
                            f"Extracted tool calls from Ollama object: {tool_calls}"
                        )

                self.logger.info(f"Extracted tool_calls: {tool_calls}")
                # Add to context and return
                if tool_calls:
                    await self.context_manager.add_tool_call_message(tool_calls)
                    self.logger.info(f"Returning tool calls to TAOR loop")
                    return tool_calls_accumulator
                else:
                    self.logger.warning(
                        f"tool_calls_accumulator present but no tool_calls extracted"
                    )

            # Handle as text response
            if accumulated_text:
                self.logger.info(
                    f"No tool calls found, returning text response ({len(accumulated_text)} chars)"
                )
                await self.context_manager.add_assistant_message(accumulated_text)
                return accumulated_text

            self.logger.warning("No accumulated_text and no tool_calls_accumulator")
            return accumulated_text

        except ModelRateLimitError as e:
            e.log_error()
            await self.event_bus.emit(
                AgentEvents.WARNING.value,
                {"message": e.user_hint, "context": "rate_limit"},
            )
            await asyncio.sleep(e.retry_after)
            return await self._get_model_response(context)  # Retry
        except ModelResponseParseError as e:
            e.log_error()
            await self.event_bus.emit(
                AgentEvents.ERROR.value,
                {"message": "Model returned invalid data.", "context": "parse_error"},
            )
            return "Fallback error."
        except Exception as e:
            self.logger.exception("Model unavailable.")
            await self.event_bus.emit(
                AgentEvents.ERROR.value,
                {"message": "Model unavailable.", "context": "model_unavailable"},
            )
            return "Fallback error."
        finally:
            await self.event_bus.emit(AgentEvents.THINKING_STOPPED.value, {})

    def _parse_response(
        self, response_data: Union[str, Dict]
    ) -> Tuple[List[Dict], bool]:
        """
        Parse response and return (actions, has_json_content).
        Handles both text responses and API tool calls.
        """
        actions = []

        # CASE 0: Response is an Ollama ChatResponse object
        if hasattr(response_data, "message"):
            self.logger.info(f"Parsing Ollama ChatResponse object")
            if (
                hasattr(response_data.message, "tool_calls")
                and response_data.message.tool_calls
            ):
                for tool_call in response_data.message.tool_calls:
                    self.logger.info(f"Parsing Ollama tool_call: {tool_call}")
                    func = tool_call.function

                    # Extract ID if present (safe access)
                    call_id = getattr(tool_call, "id", None)

                    actions.append(
                        {
                            "action": func.name,
                            "parameters": (
                                json.loads(func.arguments)
                                if isinstance(func.arguments, str)
                                else func.arguments
                            ),
                            "id": call_id,  # <--- CRITICAL FIX: Pass ID
                        }
                    )
                self.logger.info(
                    f"Extracted {len(actions)} actions from Ollama response"
                )
                return actions, len(actions) > 0

        # CASE 1: Response is already a Dictionary (Structured API Call)
        if isinstance(response_data, dict):
            self.logger.info(f"Parsing dict response")
            # 1. Try your primary utility
            tool_calls = self.proper_tool_caller.extract_tool_calls(response_data)
            for tool_call in tool_calls:
                actions.append(
                    {
                        "action": tool_call.action,
                        "parameters": tool_call.parameters,
                        "reasoning": getattr(tool_call, "reasoning", None),
                        "id": getattr(tool_call, "id", None),  # <--- CRITICAL FIX
                    }
                )

            # 2. Backup: Manual extraction if utility returned nothing
            if not actions:
                # Check for standard 'tool_calls' array (OpenAI/OpenRouter style)
                if "tool_calls" in response_data:
                    for tc in response_data["tool_calls"]:
                        func = tc.get("function", {})
                        actions.append(
                            {
                                "action": func.get("name"),
                                "parameters": (
                                    json.loads(func.get("arguments", "{}"))
                                    if isinstance(func.get("arguments"), str)
                                    else func.get("arguments")
                                ),
                                "id": tc.get("id"),  # <--- CRITICAL FIX
                            }
                        )
                # Check for direct action/parameters (Custom/Ollama style)
                elif "action" in response_data and "parameters" in response_data:
                    actions.append(response_data)

            return actions, len(actions) > 0

        # CASE 2: Response is a String (Text-based or "Ghost" Tool)
        self.logger.info(f"Response is string, no tool calls extracted")
        return [], False

    async def _record_results(self, summary: ExecutionSummary) -> bool:
        """
        Record results using Native Tool protocol.
        Extracts file paths from read_file results to trigger 'Smart Invalidation'.
        """
        had_failure = False
        for result in summary.results:

            # Detect if this was a file read (for invalidation)
            file_path = None
            if result.tool_name == "read_file" and result.success:
                # Extract path from data payload if available
                if hasattr(result, "data") and result.data:
                    file_path = result.data.get("filepath")

            # NEW: Add via specific method
            await self.context_manager.add_tool_result_message(
                tool_name=result.tool_name or "unknown_tool",
                tool_call_id=getattr(result, "tool_call_id", None),
                content=result.output,
                file_path=file_path,
            )

            if not result.success:
                had_failure = True
        return had_failure

    # --- Legacy Support Methods ---
    async def clear_conversation(self):
        """
        Reset the context manager and UI.
        """
        await self.context_manager.clear()
        await self.event_bus.emit(
            AgentEvents.INFO.value,
            {"message": "✓ Cleared.", "context": "context_cleared"},
        )

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
        """Switch the current model and update context limits."""
        self.current_model = model_name
        self.model_client.set_model(model_name)

        # FIX: Pass current_provider to RuntimeModelManager
        model_manager = RuntimeModelManager(provider=self.current_provider)
        model_info = model_manager.get_available_models().get(model_name)

        if model_info:
            # Update context window using the new update_max_tokens method
            await self.context_manager.update_max_tokens(model_info.context_window)
            self.logger.info(
                f"Updated context window to {model_info.context_window:,} tokens for model {model_name}"
            )
            self.logger.warning(
                f"Model '{model_name}' not found in {self.current_provider} model map. "
                "Context window limits not updated."
            )

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

    async def run(self):
        """Main agent loop - now handles its own UI and interaction."""
        try:
            # Ensure UI is available
            if not self.ui:
                raise RuntimeError("UI not initialized. Please inject a UI instance.")

            # Initialize command dispatcher
            from agent.command_dispatcher import CommandDispatcher

            self.command_dispatcher = CommandDispatcher(self)
            await self.event_bus.emit(
                AgentEvents.INFO.value,
                {
                    "message": f"✠ Protocol Monk started in {self.working_dir}",
                    "context": "startup",
                },
            )
            await self.event_bus.emit(
                AgentEvents.INFO.value,
                {
                    "message": f"Model: {self.current_model} ({self.current_provider})",
                    "context": "startup",
                },
            )
            await self.event_bus.emit(
                AgentEvents.INFO.value,
                {
                    "message": "Type '/help' for commands, '/quit' to exit.",
                    "context": "startup",
                },
            )

            while True:
                try:
                    # --- CHANGED: Direct Blocking UI Call (No Loops) ---
                    # We wait here forever until the user types something.
                    text = await self.ui.get_input()

                    if not text:
                        continue

                    # Use command dispatcher to handle input
                    result = await self.command_dispatcher.dispatch(text)

                    if result is False:  # Quit command
                        break  # EXIT THE LOOP

                    # Not a command, process as chat - but only if it wasn't handled
                    if result is None:
                        success = await self.process_request(text)

                        # Tell the UI the turn is over!
                        await self.event_bus.emit(AgentEvents.RESPONSE_COMPLETE.value, {})

                except KeyboardInterrupt:
                    await self.event_bus.emit(
                        AgentEvents.INFO.value,
                        {
                            "message": "\nUse 'quit' to exit.",
                            "context": "user_interrupt",
                        },
                    )
                except Exception as e:
                    await self.event_bus.emit(
                        AgentEvents.ERROR.value,
                        {"message": f"Error: {e}", "context": "runtime_error"},
                    )
        except Exception as e:
            self.logger.error(f"Agent run loop failed: {e}")
            raise

    async def _request_tool_confirmation(
        self, tool_request: ToolExecutionRequest
    ) -> bool:
        """Request tool execution confirmation through event system."""
        # This is kept for compatibility with _handle_agent_event,
        # though ToolExecutor now mostly handles this directly.
        await self.event_bus.emit(
            AgentEvents.TOOL_EXECUTION_START.value,
            {
                "tool_name": tool_request.tool_name,
                "parameters": tool_request.parameters,
                "tool_call_id": tool_request.tool_call_id,
                "requires_confirmation": True,
            },
        )
        return True

    async def get_user_input(self, request: UserInputRequest) -> UserInputResponse:
        """Get user input - temporary implementation for backward compatibility"""
        # For now, delegate to UI for input
        if not hasattr(self, "ui") or self.ui is None:
            from ui.plain import PlainUI

            self.ui = PlainUI()

        text = await self.ui.get_input()
        return UserInputResponse(text=text, cancelled=False)

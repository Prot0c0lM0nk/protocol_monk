"""
Protocol Monk Agent Service
===========================
The reactive core of the application.
Strictly Event-Driven. No UI coupling.
"""

import asyncio
import logging
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from agent.context.manager_v2 import ContextManagerV2 as ContextManager
from agent.model_client import ModelClient
from agent.model_manager import RuntimeModelManager
from agent.scratch_manager import ScratchManager
from agent.tool_executor import ToolExecutor
from agent.command_dispatcher import CommandDispatcher
from agent.logic.parsers import ToolCallExtractor
from agent.logic.streaming import ResponseStreamHandler
from agent.events import EventBus, AgentEvents, get_event_bus
from agent.context import model_error_prompts
from config.static import settings
from exceptions import ContextValidationError
from utils.enhanced_logger import EnhancedLogger
from utils.proper_tool_calling import ProperToolCalling


class AgentService:
    """
    Background service that processes INPUT events and emits RESPONSE events.
    Replaces ProtocolAgent.
    """

    def __init__(
        self,
        working_dir: str = ".",
        model_name: str = settings.model.default_model,
        provider: str = "ollama",
        tool_registry=None,
        event_bus: Optional[EventBus] = None,
    ):
        self.working_dir = Path(working_dir).resolve()
        self.current_model = model_name
        self.current_provider = provider
        self.event_bus = event_bus or get_event_bus()
        self.logger = logging.getLogger(__name__)
        self.enhanced_logger = EnhancedLogger(self.working_dir)

        # Components
        self.model_manager = RuntimeModelManager(provider=provider)
        self.model_client = ModelClient(model_name=model_name, provider=provider)

        model_info = self.model_manager.get_available_models().get(model_name)
        window = (
            model_info.context_window if model_info else settings.model.context_window
        )

        self.context_manager = ContextManager(
            max_tokens=window,
            working_dir=self.working_dir,
            tool_registry=tool_registry,
        )

        self.scratch_manager = ScratchManager(self.working_dir)
        self.proper_tool_caller = (
            ProperToolCalling(tool_registry) if tool_registry else None
        )

        # NOTE: ToolExecutor is initialized WITHOUT UI
        self.tool_executor = ToolExecutor(
            tool_registry=tool_registry,
            working_dir=self.working_dir,
            auto_confirm=False,
            event_bus=self.event_bus,
            ui=None,  # Explicitly None
        )

        self.command_dispatcher = CommandDispatcher(self)
        self.stream_handler = ResponseStreamHandler(self.event_bus)

        # State
        self._running = False
        self._tool_retry_counts: Dict[str, int] = {}
        self._turn_lock = asyncio.Lock()

    async def async_initialize(self):
        """Subscribe to events and init subsytems."""
        if hasattr(self.tool_executor.tool_registry, "async_initialize"):
            await self.tool_executor.tool_registry.async_initialize()
        await self.context_manager.async_initialize()

        # Subscribe to INPUT
        self.event_bus.subscribe(AgentEvents.USER_INPUT.value, self.on_user_input)
        self._running = True
        self.logger.info("AgentService initialized and listening.")

    async def shutdown(self):
        self._running = False
        if hasattr(self.context_manager, "stop"):
            await self.context_manager.stop()

    # --- Event Handlers ---

    async def on_user_input(self, event_data: Dict[str, Any]):
        """
        Main reactive entry point.
        event_data: {"input": str}
        """
        user_input = event_data.get("input", "")
        if not user_input:
            return

        async with self._turn_lock:
            try:
                # 1. Check Commands
                handled = await self.command_dispatcher.dispatch(user_input)
                if handled:
                    return  # Command dispatcher handles its own completion events

                # 2. Process Chat (The Loop)
                await self.context_manager.add_message("user", user_input)
                await self._run_cognitive_loop()

            except Exception as e:
                # CRITICAL: Catch crashes so we can unlock the UI
                self.logger.exception("Fatal error in AgentService")
                await self.event_bus.emit(
                    AgentEvents.ERROR.value,
                    {"message": f"Agent crashed: {e}", "context": "service_crash"},
                )
            finally:
                # 3. Finish (Always unlock the UI)
                await self.event_bus.emit(AgentEvents.RESPONSE_COMPLETE.value, {})

    async def _run_cognitive_loop(self):
        """
        The internal Think-Act loop (formerly TAORLoop).
        Runs until the agent decides to stop.
        """
        self.logger.debug("--- STARTING COGNITIVE LOOP ---")
        loop_count = 0
        while True:
            loop_count += 1
            self.logger.debug(f"Loop iteration: {loop_count}")

            # A. Prepare Context
            self.logger.debug("Getting context...")
            context = await self._get_clean_context()
            if not context:
                self.logger.error("Context retrieval failed")
                break
            self.enhanced_logger.log_context_snapshot(context)

            # B. Get Response (Stream)
            self.logger.debug("Streaming response from model...")
            tools_schema = (
                self.proper_tool_caller.get_tools_schema()
                if self.proper_tool_caller
                else None
            )

            try:
                # Add explicit debug log here
                self.logger.debug(
                    f"Calling stream handler with {len(context)} messages"
                )
                response_obj = await self.stream_handler.stream(
                    self.model_client, context, tools_schema
                )
                self.logger.debug(
                    f"Stream complete. Response type: {type(response_obj)}"
                )
            except Exception as e:
                self.logger.exception("Streaming failed!")
                break

            # C. Parse
            actions, has_actions = ToolCallExtractor.extract(response_obj)

            # Use the new safe logger method
            if hasattr(self.enhanced_logger, "log_turn"):
                self.enhanced_logger.log_turn(
                    turn_number=loop_count,
                    model_input=context,
                    model_output=response_obj,
                    parsed_actions=actions,
                )

            # D. Record Assistant Message
            if has_actions:
                # FIX: Extract ONLY the tool_calls list, not the full object
                tool_calls_payload = []

                if isinstance(response_obj, dict) and "message" in response_obj:
                    # Standard Ollama/OpenAI API dict format
                    tool_calls_payload = response_obj["message"].get("tool_calls", [])
                elif hasattr(response_obj, "tool_calls"):
                    # Pydantic object format
                    tool_calls_payload = response_obj.tool_calls
                elif isinstance(response_obj, dict) and "tool_calls" in response_obj:
                    # Flattened dict format
                    tool_calls_payload = response_obj["tool_calls"]
                else:
                    # Fallback: trust the extractor or empty
                    tool_calls_payload = actions if isinstance(actions, list) else []

                await self.context_manager.add_tool_call_message(tool_calls_payload)
            else:
                # Just text
                if isinstance(response_obj, str) and response_obj.strip():
                    await self.context_manager.add_assistant_message(response_obj)
                else:
                    # Fallback if response_obj was complex but yielded no actions (rare)
                    pass

            if not has_actions:
                # Agent is done talking
                break

            # E. Execute Tools (The Act Phase)
            # ToolExecutor handles the "Tool Confirmation" via events internally now
            if self._has_git_commit(actions):
                await self.context_manager.add_temporary_system_prompt(
                    model_error_prompts.git_commit_signoff_prompt()
                )
            summary = await self.tool_executor.execute_tool_calls(actions)

            # F. Record Results
            for result in summary.results:
                kind = model_error_prompts.classify_tool_error(result)
                if kind is None:
                    continue

                if model_error_prompts.should_stop(kind):
                    summary.should_finish = True
                    continue

                if model_error_prompts.should_retry(kind):
                    retry_key = f"{getattr(result, 'tool_name', 'unknown')}:{kind.value}"
                    retry_count = self._tool_retry_counts.get(retry_key, 0)
                    if retry_count == 0:
                        self._tool_retry_counts[retry_key] = 1
                        await self.context_manager.add_temporary_system_prompt(
                            model_error_prompts.build_tool_error_prompt(
                                getattr(result, "tool_name", "unknown"),
                                result,
                                None,
                            )
                        )
                    else:
                        summary.should_finish = True

            for result in summary.results:
                await self.context_manager.add_tool_result_message(
                    tool_name=result.tool_name,
                    tool_call_id=result.tool_call_id,
                    content=result.output,
                )

            # Check if we should stop
            if summary.should_finish:
                break

            # Loop continues to reflect on tool results...

    async def _get_clean_context(self):
        try:
            return await self.context_manager.get_context(
                self.current_model, self.current_provider
            )
        except Exception as e:
            await self.event_bus.emit(
                AgentEvents.ERROR.value, {"message": f"Context Error: {e}"}
            )
            return None

    def _has_git_commit(self, actions: List[Dict[str, Any]]) -> bool:
        for action in actions:
            if action.get("action") != "git_operation":
                continue
            params = action.get("parameters") or {}
            if params.get("operation") == "commit":
                return True
        return False

    # --- Support Methods for CommandDispatcher ---
    async def clear_conversation(self):
        await self.context_manager.clear()
        await self.event_bus.emit(
            AgentEvents.INFO.value, {"message": "Context cleared."}
        )

    async def get_status(self) -> Dict:
        stats = await self.context_manager.get_stats()
        return {
            "current_model": self.current_model,
            "provider": self.current_provider,
            "conversation_length": stats["total_messages"],
            "estimated_tokens": stats["total_tokens"],
            "token_limit": self.context_manager.max_tokens,
        }

    async def set_model(self, model_name: str):
        self.current_model = model_name
        self.model_client.set_model(model_name)
        # Update context window logic...
        model_info = self.model_manager.get_available_models().get(model_name)
        if model_info:
            await self.context_manager.update_max_tokens(model_info.context_window)

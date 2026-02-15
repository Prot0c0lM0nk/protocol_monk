"""
Protocol Monk Agent Service
===========================
The reactive core of the application.
Strictly Event-Driven. No UI coupling.
"""

import asyncio
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from agent.context.manager_v2 import ContextManagerV2 as ContextManager
from agent.model_client import ModelClient
from agent.model_manager import RuntimeModelManager
from agent.scratch_manager import ScratchManager
from agent.tool_executor import ToolExecutor
from agent.command_dispatcher import CommandDispatcher
from agent.logic.streaming import ResponseStreamHandler
from agent.events import EventBus, AgentEvents, get_event_bus
from agent.tool_pipeline.manager import ToolPipelineManager
from agent.neuralsym import NeuralSymBridge
from agent.tool_pipeline.types import ToolPipelineMode
from agent.context import model_error_prompts
from config.static import settings
from exceptions import ModelError, ModelTimeoutError
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

        # Initialize NeuralSym bridge for learned guidance
        self.neuralsym: Optional[NeuralSymBridge] = None
        if settings.neuralsym.enabled:
            try:
                self.neuralsym = NeuralSymBridge(
                    project_path=settings.filesystem.working_dir,
                    lfm_model=settings.neuralsym.lfm_model,
                    lfm_provider=settings.neuralsym.lfm_provider,
                    enabled=True,
                )
                # Connect to tool executor for learning
                self.tool_executor.neuralsym = self.neuralsym
                self.logger.info("NeuralSym bridge initialized")
            except Exception as e:
                self.logger.warning(f"Failed to initialize NeuralSym: {e}")
                self.neuralsym = None

        self.command_dispatcher = CommandDispatcher(self)
        self.stream_handler = ResponseStreamHandler(self.event_bus)
        self.pipeline_manager = ToolPipelineManager(
            tool_registry=tool_registry,
            proper_tool_caller=self.proper_tool_caller,
        )
        self.pipeline_manager.set_mode(ToolPipelineMode.NATIVE.value)
        self._tool_pipeline_mode = ToolPipelineMode.NATIVE.value
        self._pending_tool_pipeline_mode: Optional[str] = None
        self._latest_user_input: str = ""
        self._mode_lock = asyncio.Lock()

        # State
        self._running = False
        self._tool_retry_counts: Dict[str, int] = {}
        self._turn_lock = asyncio.Lock()

    async def async_initialize(self):
        """Subscribe to events and init subsytems."""
        if hasattr(self.tool_executor.tool_registry, "async_initialize"):
            await self.tool_executor.tool_registry.async_initialize()
        await self.context_manager.async_initialize()
        initial_mode = settings.tool_pipeline.mode
        if initial_mode != ToolPipelineMode.NATIVE.value:
            result = await self._apply_tool_pipeline_mode(initial_mode, source="startup")
            if not result.get("success"):
                self.logger.warning(
                    "Failed to activate startup pipeline mode '%s': %s",
                    initial_mode,
                    result.get("message"),
                )

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
        self._latest_user_input = str(user_input)

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
                if self._pending_tool_pipeline_mode:
                    pending = self._pending_tool_pipeline_mode
                    self._pending_tool_pipeline_mode = None
                    await self._apply_tool_pipeline_mode(pending, source="deferred")

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
            
            # Generate and inject NeuralSym guidance before each turn
            if self.neuralsym and self.neuralsym.guidance_context.has_guidance:
                guidance_msg = self.neuralsym.get_guidance_message()
                if guidance_msg:
                    await self.context_manager.add_temporary_system_prompt(
                        guidance_msg["content"]
                    )

            # FunctionGemma mode injects tool-list wrappers every turn.
            if self._tool_pipeline_mode == ToolPipelineMode.FUNCTIONGEMMA.value:
                await self.context_manager.add_temporary_system_prompt(
                    self.pipeline_manager.build_tool_list_prompt()
                )

            # A. Prepare Context
            self.logger.debug("Getting context...")
            context = await self._get_clean_context()
            if not context:
                self.logger.error("Context retrieval failed")
                break
            self.enhanced_logger.log_context_snapshot(context)

            # B. Get Response (Stream)
            self.logger.debug("Streaming response from model...")
            tools_schema = self.pipeline_manager.get_main_model_tools_schema()

            try:
                # Add explicit debug log here
                self.logger.debug(
                    f"Calling stream handler with {len(context)} messages"
                )
                response_obj = await self.stream_handler.stream(
                    self.model_client,
                    context,
                    tools_schema,
                    hide_tool_wrappers=(
                        self._tool_pipeline_mode == ToolPipelineMode.FUNCTIONGEMMA.value
                    ),
                )
                self.logger.debug(
                    f"Stream complete. Response type: {type(response_obj)}"
                )
            except Exception as e:
                should_continue = await self._handle_stream_failure(e)
                if should_continue:
                    continue
                break

            # C. Parse
            parsed = await self.pipeline_manager.parse_response(
                response_obj,
                latest_user_text=self._latest_user_input,
            )
            if parsed.error:
                self.logger.error("Tool pipeline parse error: %s", parsed.error)
                await self.event_bus.emit(
                    AgentEvents.ERROR.value,
                    {
                        "message": f"Tool pipeline parse error: {parsed.error}",
                        "context": "tool_pipeline",
                    },
                )
                break
            actions = parsed.actions
            has_actions = parsed.has_actions

            # Use the new safe logger method
            if hasattr(self.enhanced_logger, "log_turn"):
                self.enhanced_logger.log_turn(
                    turn_number=loop_count,
                    model_input=context,
                    model_output=response_obj,
                    parsed_actions=actions,
                )

            # D. Record Assistant Message
            await self._record_assistant_output(parsed, len(actions))

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
                result_content = result.output
                if self._tool_pipeline_mode == ToolPipelineMode.FUNCTIONGEMMA.value:
                    result_content = self.pipeline_manager.wrap_tool_result(
                        result.tool_name,
                        result.success,
                        result.tool_call_id,
                        result.output,
                    )
                await self.context_manager.add_tool_result_message(
                    tool_name=result.tool_name,
                    tool_call_id=result.tool_call_id,
                    content=result_content,
                )

            # Check if we should stop
            if summary.should_finish:
                break

            # Loop continues to reflect on tool results...

    async def _record_assistant_output(self, parsed, actions_count: int) -> None:
        """Record assistant output and optional tool-call history."""
        if parsed.has_actions:
            if parsed.assistant_text.strip():
                await self.context_manager.add_assistant_message(parsed.assistant_text)
            if parsed.persist_tool_call_message:
                await self.context_manager.add_tool_call_message(parsed.tool_calls_payload)
            else:
                self.logger.debug(
                    "PIPELINE_DIAG skip_tool_call_persist mode=%s actions=%d",
                    self._tool_pipeline_mode,
                    actions_count,
                )
        elif parsed.assistant_text.strip():
            await self.context_manager.add_assistant_message(parsed.assistant_text)

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
            "tool_pipeline_mode": self._tool_pipeline_mode,
        }

    async def set_model(self, model_name: str):
        self.current_model = model_name
        self.model_client.set_model(model_name)
        # Update context window logic...
        model_info = self.model_manager.get_available_models().get(model_name)
        if model_info:
            await self.context_manager.update_max_tokens(model_info.context_window)

    def get_tool_pipeline_mode(self) -> str:
        return self._tool_pipeline_mode

    async def request_tool_pipeline_mode(
        self, mode: str, source: str = "ui"
    ) -> Dict[str, Any]:
        """
        Runtime mode switch request. If a turn is active, queue for next idle state.
        """
        normalized = self.pipeline_manager.normalize(mode).value
        if (
            normalized == ToolPipelineMode.FUNCTIONGEMMA.value
            and self.current_provider == "mlx_lm"
        ):
            message = (
                "FunctionGemma tool mode is disabled while provider is 'mlx_lm'. "
                "Use /toolmode off or switch provider first."
            )
            await self.event_bus.emit(
                AgentEvents.WARNING.value,
                {"message": message, "context": "tool_pipeline"},
            )
            await self.event_bus.emit(
                AgentEvents.INFO.value,
                {
                    "message": f"Tool pipeline mode remains '{self._tool_pipeline_mode}'.",
                    "context": "tool_pipeline",
                },
            )
            return {
                "success": False,
                "queued": False,
                "applied": False,
                "active_mode": self._tool_pipeline_mode,
                "message": message,
            }

        ok, reason = self.pipeline_manager.validate_mode_preconditions(normalized)
        if not ok:
            return {
                "success": False,
                "queued": False,
                "applied": False,
                "active_mode": self._tool_pipeline_mode,
                "message": reason,
            }

        if self._turn_lock.locked():
            self._pending_tool_pipeline_mode = normalized
            return {
                "success": True,
                "queued": True,
                "applied": False,
                "active_mode": self._tool_pipeline_mode,
                "pending_mode": self._pending_tool_pipeline_mode,
                "message": f"Queued tool pipeline mode '{normalized}' from {source}.",
            }

        return await self._apply_tool_pipeline_mode(normalized, source=source)

    async def _apply_tool_pipeline_mode(self, mode: str, source: str) -> Dict[str, Any]:
        """
        Apply runtime pipeline mode immediately (idle path).
        """
        async with self._mode_lock:
            normalized = self.pipeline_manager.normalize(mode).value
            if (
                normalized == ToolPipelineMode.FUNCTIONGEMMA.value
                and self.current_provider == "mlx_lm"
            ):
                return {
                    "success": False,
                    "queued": False,
                    "applied": False,
                    "active_mode": self._tool_pipeline_mode,
                    "message": (
                        "FunctionGemma tool mode is disabled while provider is 'mlx_lm'."
                    ),
                }
            if normalized == self._tool_pipeline_mode:
                return {
                    "success": True,
                    "queued": False,
                    "applied": True,
                    "active_mode": self._tool_pipeline_mode,
                    "message": f"Tool pipeline already '{normalized}'.",
                }

            ok, reason = self.pipeline_manager.validate_mode_preconditions(normalized)
            if not ok:
                return {
                    "success": False,
                    "queued": False,
                    "applied": False,
                    "active_mode": self._tool_pipeline_mode,
                    "message": reason,
                }

            prompt_file = self.pipeline_manager.get_prompt_file_for_mode(normalized)
            switched, switch_msg = await self.context_manager.set_base_system_prompt_file(
                prompt_file
            )
            if not switched:
                return {
                    "success": False,
                    "queued": False,
                    "applied": False,
                    "active_mode": self._tool_pipeline_mode,
                    "message": switch_msg,
                }

            self.pipeline_manager.set_mode(normalized)
            self._tool_pipeline_mode = normalized
            self.logger.info(
                "Tool pipeline switched to '%s' (source=%s)", normalized, source
            )
            await self.event_bus.emit(
                AgentEvents.INFO.value,
                {
                    "message": f"Tool pipeline mode: {normalized}",
                    "context": "tool_pipeline",
                },
            )
            return {
                "success": True,
                "queued": False,
                "applied": True,
                "active_mode": self._tool_pipeline_mode,
                "message": f"Switched tool pipeline to '{normalized}'.",
            }

    async def _handle_stream_failure(self, error: Exception) -> bool:
        """
        Handle stream errors and decide whether the turn should retry.
        Returns True to retry loop, False to stop current turn.
        """
        self.logger.exception("Streaming failed")
        if not self._is_mlx_stream_error(error):
            await self.event_bus.emit(
                AgentEvents.ERROR.value,
                {
                    "message": f"Model stream failed: {error}",
                    "context": "stream_error",
                },
            )
            return False

        await self.event_bus.emit(
            AgentEvents.WARNING.value,
            {
                "message": (
                    "MLX server request failed. Choose retry, switch provider, or abort."
                ),
                "context": "mlx_server",
            },
        )
        choice = await self._prompt_mlx_failure_action()
        if choice == "retry":
            await self.event_bus.emit(
                AgentEvents.INFO.value,
                {"message": "Retrying MLX server request.", "context": "mlx_server"},
            )
            return True

        if choice == "switch":
            switched = await self._switch_to_fallback_provider()
            if switched:
                await self.event_bus.emit(
                    AgentEvents.INFO.value,
                    {
                        "message": "Switched provider. Retrying current turn.",
                        "context": "mlx_server",
                    },
                )
                return True

            await self.event_bus.emit(
                AgentEvents.WARNING.value,
                {
                    "message": "No fallback provider available. Aborting current turn.",
                    "context": "mlx_server",
                },
            )
            return False

        await self.event_bus.emit(
            AgentEvents.INFO.value,
            {"message": "Aborted current turn.", "context": "mlx_server"},
        )
        return False

    def _is_mlx_stream_error(self, error: Exception) -> bool:
        if self.current_provider != "mlx_lm":
            return False
        if isinstance(error, (ModelError, ModelTimeoutError)):
            return True
        text = str(error).lower()
        return "mlx" in text and "server" in text

    async def _prompt_mlx_failure_action(self) -> str:
        prompt = (
            "MLX server request failed. Choose action: "
            "1) retry  2) switch provider  3) abort"
        )
        await self.event_bus.emit(
            AgentEvents.INPUT_REQUESTED.value,
            {
                "prompt": prompt,
                "data": ["retry", "switch provider", "abort"],
            },
        )
        try:
            response = await self.event_bus.wait_for(
                AgentEvents.INPUT_RESPONSE.value,
                timeout=60.0,
            )
        except asyncio.TimeoutError:
            return "abort"

        raw = str(response.get("input", "")).strip().lower()
        if raw in {"1", "retry", "r"}:
            return "retry"
        if raw in {"2", "switch", "switch provider", "s"}:
            return "switch"
        return "abort"

    async def _switch_to_fallback_provider(self) -> bool:
        chain = [p.strip() for p in settings.api.provider_chain if str(p).strip()]
        alternatives = [p for p in chain if p and p != self.current_provider]
        if not alternatives:
            return False

        target_provider = alternatives[0]
        old_provider = self.current_provider
        try:
            self.model_manager.switch_provider(target_provider)
            self.model_client.switch_provider(target_provider)
            self.current_provider = target_provider
            await self.event_bus.emit(
                AgentEvents.PROVIDER_SWITCHED.value,
                {
                    "old_provider": old_provider,
                    "new_provider": target_provider,
                },
            )
            return True
        except Exception as exc:  # pylint: disable=broad-exception-caught
            await self.event_bus.emit(
                AgentEvents.ERROR.value,
                {
                    "message": f"Failed to switch provider from '{old_provider}' to '{target_provider}': {exc}",
                    "context": "mlx_server",
                },
            )
            return False

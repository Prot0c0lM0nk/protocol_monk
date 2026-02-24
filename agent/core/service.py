import logging
import asyncio
import json
import time
import uuid
from typing import Any, Dict, List, Tuple

from protocol_monk.protocol.bus import EventBus
from protocol_monk.protocol.events import EventTypes
from protocol_monk.agent.structs import (
    AgentResponse,
    UserRequest,
    AgentStatus,
    ConfirmationResponse,
    ToolResult,
    ToolRequest,
    Message,
    ContextStats,
)
from protocol_monk.agent.context.coordinator import ContextCoordinator
from protocol_monk.agent.core.state_machine import StateMachine, AgentState
from protocol_monk.tools.registry import ToolRegistry
from protocol_monk.config.settings import Settings

# [NEW] Import Execution components
from protocol_monk.agent.core.execution import ToolExecutor
from protocol_monk.agent.loops import run_thinking_loop, run_action_loop


class AgentService:
    """
    The Main Agent Loop.

    Responsibility:
    1. Listen for USER_INPUT.
    2. Manage Agent State (Idle -> Thinking -> Acting).
    3. Update Context (via Coordinator).
    4. Call LLM (Thinking Loop).
    5. Execute Tools (Action Loop).
    """

    def __init__(
        self,
        bus: EventBus,
        coordinator: ContextCoordinator,
        registry: ToolRegistry,
        provider: Any,
        settings: Settings,
    ):
        self._bus = bus
        self._context = coordinator
        self._registry = registry
        self._provider = provider
        self._settings = settings
        self._state = StateMachine()
        self._logger = logging.getLogger("AgentService")

        # [FIX] Initialize the Executor (The Hands)
        self._executor = ToolExecutor(timeout_seconds=settings.tool_timeout)

        # Track pending confirmation futures by tool_call_id.
        self._pending_confirmations: Dict[str, asyncio.Future] = {}
        self._auto_confirm = bool(getattr(settings, "auto_confirm", False))
        self._request_lock = asyncio.Lock()

    async def start(self) -> None:
        """
        Bootstraps the agent listeners.
        """
        await self._bus.subscribe(
            EventTypes.USER_INPUT_SUBMITTED, self._handle_user_input
        )
        await self._bus.subscribe(
            EventTypes.TOOL_CONFIRMATION_SUBMITTED, self._handle_tool_confirmation
        )
        await self._bus.subscribe(
            EventTypes.SYSTEM_COMMAND_ISSUED, self._handle_system_command
        )
        self._logger.info("Agent Service started and listening.")

    def _assistant_tool_call_payload(self, req: ToolRequest) -> Dict[str, Any]:
        return {
            "id": req.call_id,
            "type": "function",
            "function": {
                "name": req.name,
                "arguments": req.parameters,
            },
        }

    async def _persist_assistant_response(
        self,
        response: AgentResponse,
        *,
        turn_id: str,
        round_index: int,
    ) -> ContextStats:
        valid_tool_calls, malformed_tool_calls = self._split_tool_calls(
            list(response.tool_calls or [])
        )
        if malformed_tool_calls:
            await self._emit_malformed_tool_call_warning(
                turn_id=turn_id,
                pass_id=response.pass_id,
                round_index=round_index,
                malformed_tool_calls=malformed_tool_calls,
                stage="context_persist_filter",
            )
        stats = await self._context.add_assistant_pass(
            content=response.content,
            thinking=response.thinking,
            pass_id=response.pass_id,
            tokens=response.tokens,
            tool_call_count=len(valid_tool_calls),
            tool_calls=[
                self._assistant_tool_call_payload(req) for req in valid_tool_calls
            ],
        )
        await self._emit_context_update(
            stats,
            turn_id=turn_id,
            pass_id=response.pass_id,
            round_index=round_index,
        )
        return stats

    @staticmethod
    def _split_tool_calls(
        tool_calls: List[ToolRequest],
    ) -> Tuple[List[ToolRequest], List[ToolRequest]]:
        valid: List[ToolRequest] = []
        malformed: List[ToolRequest] = []
        for req in tool_calls:
            req.name = str(getattr(req, "name", "") or "").strip()
            if req.name:
                valid.append(req)
            else:
                malformed.append(req)
        return valid, malformed

    def _build_tool_call_repair_prompt(
        self, malformed_tool_calls: List[ToolRequest]
    ) -> str:
        malformed_samples = [
            {
                "call_id": req.call_id,
                "name": req.name,
                "parameters": req.parameters,
                "provider": (req.metadata or {}).get("provider"),
                "malformed_reason": (req.metadata or {}).get("malformed_reason"),
            }
            for req in malformed_tool_calls
        ]
        allowed_tools = ", ".join(self._registry.list_tool_names())
        return (
            "Tool-call repair request.\n"
            "Your previous assistant pass produced malformed tool calls with empty function names.\n"
            f"Allowed tool names (exact): {allowed_tools}\n"
            "Re-emit your intended tool calls now using this strict contract:\n"
            "- Every tool call MUST include a non-empty `name`.\n"
            "- `parameters` MUST be a JSON object.\n"
            "- Do not emit empty objects `{}` as tool calls.\n"
            "- If no tool is required, return normal assistant text with zero tool calls.\n"
            f"Malformed calls observed: {json.dumps(malformed_samples, ensure_ascii=False, default=str)}"
        )

    async def _emit_malformed_tool_call_warning(
        self,
        *,
        turn_id: str,
        pass_id: str,
        round_index: int,
        malformed_tool_calls: List[ToolRequest],
        stage: str,
    ) -> None:
        samples = [
            {
                "call_id": req.call_id,
                "name": req.name,
                "parameters": req.parameters,
                "metadata": req.metadata,
            }
            for req in malformed_tool_calls[:3]
        ]
        await self._bus.emit(
            EventTypes.WARNING,
            {
                "message": "Malformed tool calls detected",
                "details": (
                    f"{stage}: {len(malformed_tool_calls)} call(s) missing tool name."
                ),
                "data": {
                    "malformed_count": len(malformed_tool_calls),
                    "samples": samples,
                },
                "turn_id": turn_id,
                "pass_id": pass_id,
                "round_index": round_index,
            },
        )

    async def _request_tool_call_repair_pass(
        self,
        *,
        turn_id: str,
        round_index: int,
        malformed_tool_calls: List[ToolRequest],
    ) -> AgentResponse:
        await self._set_status(
            AgentState.THINKING,
            "Repairing malformed tool calls...",
            turn_id=turn_id,
            round_index=round_index,
        )
        history = self._context._store.get_full_history()
        repair_prompt = self._build_tool_call_repair_prompt(malformed_tool_calls)
        augmented_history = [
            *history,
            Message(role="system", content=repair_prompt, timestamp=time.time()),
        ]
        response = await run_thinking_loop(
            context_history=augmented_history,
            provider=self._provider,
            bus=self._bus,
            registry=self._registry,
            settings=self._settings,
            turn_id=turn_id,
            round_index=round_index,
        )
        await self._persist_assistant_response(
            response,
            turn_id=turn_id,
            round_index=round_index,
        )
        return response

    async def _handle_user_input(self, payload: UserRequest) -> None:
        """
        Main Handler: User speaks -> Agent processes.
        """
        async with self._request_lock:
            try:
                turn_id = str(getattr(payload, "request_id", "") or uuid.uuid4())

                # 1. State: IDLE -> THINKING
                await self._set_status(
                    AgentState.THINKING,
                    "Processing user input...",
                    turn_id=turn_id,
                    round_index=0,
                )

                # 2. Logic: Update Context
                stats = await self._context.add_user_message(payload.text)

                # 3. Emit Verification
                await self._emit_context_update(stats, turn_id=turn_id, round_index=0)

                # 4. Trigger LLM Thinking Loop (THE BRAIN)
                history = self._context._store.get_full_history()
                self._logger.info("Entering Thinking Loop...")

                response = await run_thinking_loop(
                    context_history=history,
                    provider=self._provider,
                    bus=self._bus,
                    registry=self._registry,
                    settings=self._settings,
                    turn_id=turn_id,
                    round_index=0,
                )
                await self._persist_assistant_response(
                    response,
                    turn_id=turn_id,
                    round_index=0,
                )

                # 5. Think/Act loop: tool results are added back to context,
                # then the model gets another pass to produce a final answer.
                # We cap rounds to prevent runaway loops.
                max_tool_rounds = 400
                rounds = 0
                stopped_by_rejection = False
                stopped_by_malformed = False
                tool_repair_attempted = False
                while response.tool_calls and rounds < max_tool_rounds:
                    valid_tool_calls, malformed_tool_calls = self._split_tool_calls(
                        response.tool_calls
                    )
                    if malformed_tool_calls:
                        await self._emit_malformed_tool_call_warning(
                            turn_id=turn_id,
                            pass_id=response.pass_id,
                            round_index=rounds,
                            malformed_tool_calls=malformed_tool_calls,
                            stage="pre_execution",
                        )
                        if not tool_repair_attempted:
                            tool_repair_attempted = True
                            response = await self._request_tool_call_repair_pass(
                                turn_id=turn_id,
                                round_index=rounds,
                                malformed_tool_calls=malformed_tool_calls,
                            )
                            continue

                        stopped_by_malformed = True
                        await self._bus.emit(
                            EventTypes.WARNING,
                            {
                                "message": "Malformed tool calls persisted after repair",
                                "details": (
                                    f"Stopping turn after {len(malformed_tool_calls)} malformed tool call(s)."
                                ),
                                "turn_id": turn_id,
                                "pass_id": response.pass_id,
                                "round_index": rounds,
                            },
                        )
                        break

                    rounds += 1
                    await self._set_status(
                        AgentState.EXECUTING,
                        f"Executing {len(valid_tool_calls)} tools...",
                        turn_id=turn_id,
                        pass_id=response.pass_id,
                        round_index=rounds,
                    )

                    user_rejected = False
                    for tool_index, tool_req in enumerate(valid_tool_calls):
                        tool_def = self._registry.get_tool(tool_req.name)
                        requires_confirmation = bool(
                            tool_def and tool_def.requires_confirmation
                        )
                        # Always trust local tool policy over provider payload.
                        tool_req.requires_confirmation = requires_confirmation

                        # Create a confirmation future if the tool requires confirmation
                        confirmation_future = None
                        if requires_confirmation and not self._auto_confirm:
                            self._logger.info(
                                f"Creating confirmation future for tool: {tool_req.name}"
                            )
                            confirmation_future = asyncio.Future()
                            self._pending_confirmations[tool_req.call_id] = (
                                confirmation_future
                            )

                        # Execute the tool with the confirmation future
                        try:
                            result = await run_action_loop(
                                tool_req=tool_req,
                                registry=self._registry,
                                bus=self._bus,
                                executor=self._executor,
                                turn_id=turn_id,
                                pass_id=response.pass_id,
                                round_index=rounds,
                                tool_index=tool_index,
                                confirmation_future=confirmation_future,
                                auto_approve=self._auto_confirm,
                                set_status=self._set_status,
                            )
                        finally:
                            self._pending_confirmations.pop(tool_req.call_id, None)

                        # Persist every tool outcome so the next turn/model pass can reason over it.
                        stats = await self._context.add_tool_result(result)
                        await self._emit_context_update(
                            stats,
                            turn_id=turn_id,
                            pass_id=response.pass_id,
                            round_index=rounds,
                            tool_call_id=result.call_id,
                            tool_index=tool_index,
                        )

                        if result.error_code == "user_rejected":
                            # Close the current tool-call batch in-order. The provider expects
                            # each assistant tool_call id to eventually receive a terminal tool
                            # result, even when we stop the turn on rejection.
                            for skipped_offset, skipped_req in enumerate(
                                valid_tool_calls[tool_index + 1 :], start=1
                            ):
                                stats = await self._context.add_tool_result(
                                    ToolResult(
                                        tool_name=skipped_req.name,
                                        call_id=skipped_req.call_id,
                                        success=False,
                                        output=None,
                                        duration=0,
                                        error=(
                                            "Skipped because an earlier tool call in this batch "
                                            "was rejected."
                                        ),
                                        error_code="skipped_due_to_rejection",
                                        output_kind="none",
                                        error_details={
                                            "blocked_by_tool_call_id": tool_req.call_id
                                        },
                                        request_parameters=skipped_req.parameters,
                                    )
                                )
                                await self._emit_context_update(
                                    stats,
                                    turn_id=turn_id,
                                    pass_id=response.pass_id,
                                    round_index=rounds,
                                    tool_call_id=skipped_req.call_id,
                                    tool_index=tool_index + skipped_offset,
                                )
                            user_rejected = True
                            stopped_by_rejection = True
                            await self._bus.emit(
                                EventTypes.INFO,
                                {
                                    "message": (
                                        "Tool execution rejected. Skipping follow-up model pass for this turn."
                                    ),
                                    "turn_id": turn_id,
                                    "pass_id": response.pass_id,
                                    "round_index": rounds,
                                },
                            )
                            break

                    if user_rejected:
                        break

                    await self._set_status(
                        AgentState.THINKING,
                        "Processing tool results...",
                        turn_id=turn_id,
                        round_index=rounds,
                    )
                    history = self._context._store.get_full_history()
                    response = await run_thinking_loop(
                        context_history=history,
                        provider=self._provider,
                        bus=self._bus,
                        registry=self._registry,
                        settings=self._settings,
                        turn_id=turn_id,
                        round_index=rounds,
                    )
                    await self._persist_assistant_response(
                        response,
                        turn_id=turn_id,
                        round_index=rounds,
                    )

                if (
                    response.tool_calls
                    and rounds >= max_tool_rounds
                    and not stopped_by_rejection
                    and not stopped_by_malformed
                ):
                    await self._bus.emit(
                        EventTypes.WARNING,
                        {
                            "message": "Tool loop limit reached",
                            "details": f"Stopped after {max_tool_rounds} tool rounds",
                            "turn_id": turn_id,
                            "pass_id": response.pass_id,
                            "round_index": rounds,
                        },
                    )

                # 6. State: -> IDLE
                await self._set_status(
                    AgentState.IDLE,
                    "Ready",
                    turn_id=turn_id,
                    round_index=rounds,
                )

            except Exception as e:
                self._logger.error(f"Error in main loop: {e}", exc_info=True)
                await self._set_status(AgentState.ERROR, f"System Error: {str(e)}")

    async def _emit_context_update(
        self,
        stats: ContextStats,
        *,
        turn_id: str | None = None,
        pass_id: str | None = None,
        round_index: int | None = None,
        tool_call_id: str | None = None,
        tool_index: int | None = None,
    ) -> None:
        context_limit = int(getattr(self._settings, "context_window_limit", 0) or 0)
        correlation: Dict[str, Any] = {}
        if turn_id:
            correlation["turn_id"] = turn_id
        if pass_id:
            correlation["pass_id"] = pass_id
        if round_index is not None:
            correlation["round_index"] = round_index
        if tool_call_id:
            correlation["tool_call_id"] = tool_call_id
        if tool_index is not None:
            correlation["tool_index"] = tool_index

        payload: Dict[str, Any] = {
            "message": "Context updated",
            "data": {
                "total_tokens": stats.total_tokens,
                "message_count": stats.message_count,
                "loaded_files_count": stats.loaded_files_count,
                "context_limit": context_limit,
            },
        }
        if correlation:
            payload["data"]["correlation"] = correlation
            payload.update(correlation)

        await self._bus.emit(
            EventTypes.INFO,
            payload,
        )

    async def _resolve_context_stats(self) -> ContextStats:
        get_stats = getattr(self._context, "get_stats", None)
        if callable(get_stats):
            maybe_stats = get_stats()
            if asyncio.iscoroutine(maybe_stats):
                maybe_stats = await maybe_stats
            if isinstance(maybe_stats, ContextStats):
                return maybe_stats

        history = self._context._store.get_full_history()
        total_tokens = sum(len((message.content or "")) // 4 for message in history)
        return ContextStats(
            total_tokens=total_tokens,
            message_count=len(history),
            loaded_files_count=0,
        )

    async def _set_status(
        self,
        state: AgentState,
        message: str,
        *,
        turn_id: str | None = None,
        pass_id: str | None = None,
        round_index: int | None = None,
        tool_call_id: str | None = None,
        tool_index: int | None = None,
    ) -> None:
        """
        Helper to update internal state and emit event in one go.
        """
        try:
            self._state.transition_to(state)
            status_payload = AgentStatus(
                status=state.value,
                message=message,
                turn_id=turn_id,
                pass_id=pass_id,
                round_index=round_index,
                tool_call_id=tool_call_id,
                tool_index=tool_index,
            )
            await self._bus.emit(EventTypes.STATUS_CHANGED, status_payload)
        except ValueError as e:
            self._logger.critical(f"State Machine Violation: {e}")
            await self._bus.emit(
                EventTypes.ERROR,
                {
                    "message": "State machine violation",
                    "details": str(e),
                },
            )

    async def _handle_tool_confirmation(self, payload: ConfirmationResponse) -> None:
        """
        Handle TOOL_CONFIRMATION_SUBMITTED events to resolve pending confirmation futures.
        """
        try:
            self._logger.info(
                f"Received tool confirmation for call_id: {payload.tool_call_id}"
            )

            # Validate payload
            if not hasattr(payload, "tool_call_id") or not payload.tool_call_id:
                self._logger.error("Invalid confirmation payload: missing tool_call_id")
                await self._bus.emit(
                    EventTypes.ERROR,
                    {
                        "message": "Invalid confirmation payload",
                        "details": "Missing tool_call_id",
                    },
                )
                return

            if not hasattr(payload, "decision") or payload.decision not in [
                "approved",
                "rejected",
            ]:
                self._logger.error(f"Invalid confirmation decision: {payload.decision}")
                await self._bus.emit(
                    EventTypes.ERROR,
                    {
                        "message": "Invalid confirmation decision",
                        "details": f"Decision must be approved or rejected, got {payload.decision}",
                    },
                )
                return

            future = self._pending_confirmations.get(payload.tool_call_id)
            # Resolve the pending confirmation future if it exists.
            if future and not future.done():
                self._logger.info(
                    f"Resolving confirmation future for call_id: {payload.tool_call_id}"
                )
                future.set_result(payload)
            else:
                self._logger.warning(
                    f"No pending confirmation found for call_id: {payload.tool_call_id}"
                )
                await self._bus.emit(
                    EventTypes.WARNING,
                    {
                        "message": "No pending confirmation found",
                        "details": f"Tool call ID {payload.tool_call_id} not found",
                    },
                )

        except Exception as e:
            self._logger.error(f"Error handling tool confirmation: {e}", exc_info=True)
            await self._bus.emit(
                EventTypes.ERROR,
                {"message": "Error processing tool confirmation", "details": str(e)},
            )

    async def _handle_system_command(self, payload: dict) -> None:
        """
        Handle SYSTEM_COMMAND_ISSUED events to process system-level commands.
        """
        try:
            self._logger.info(f"Received system command: {payload}")

            # Validate payload
            if not isinstance(payload, dict):
                self._logger.error("Invalid system command payload: not a dictionary")
                await self._bus.emit(
                    EventTypes.ERROR,
                    {
                        "message": "Invalid system command payload",
                        "details": "Payload must be a dictionary",
                    },
                )
                return

            command = payload.get("command")
            if not command:
                self._logger.error(
                    "Invalid system command payload: missing 'command' field"
                )
                await self._bus.emit(
                    EventTypes.ERROR,
                    {
                        "message": "Invalid system command payload",
                        "details": "Missing 'command' field",
                    },
                )
                return

            # Process different system commands
            if command == "cancel_current_task":
                await self._handle_cancel_task()
            elif command == "reset_context":
                await self._handle_reset_context()
            elif command == "refresh_status":
                await self._handle_refresh_status()
            elif command == "toggle_auto_confirm":
                auto_confirm = payload.get("auto_confirm", True)
                await self._handle_toggle_auto_confirm(auto_confirm)
            else:
                self._logger.warning(f"Unknown system command: {command}")
                await self._bus.emit(
                    EventTypes.WARNING,
                    {
                        "message": "Unknown system command",
                        "details": f"Command '{command}' is not recognized",
                    },
                )

        except Exception as e:
            self._logger.error(f"Error handling system command: {e}", exc_info=True)
            await self._bus.emit(
                EventTypes.ERROR,
                {"message": "Error processing system command", "details": str(e)},
            )

    async def _handle_cancel_task(self) -> None:
        """
        Handle task cancellation command.
        """
        try:
            active_futures = [
                future
                for future in self._pending_confirmations.values()
                if not future.done()
            ]
            if active_futures:
                self._logger.info(
                    "Cancelling %d pending confirmation task(s)", len(active_futures)
                )
                for future in active_futures:
                    future.cancel()
                self._pending_confirmations.clear()
                await self._set_status(AgentState.IDLE, "Task cancelled by user")
                await self._bus.emit(
                    EventTypes.INFO, {"message": "Task cancelled successfully"}
                )
            else:
                self._logger.info("No active task to cancel")
                await self._bus.emit(
                    EventTypes.INFO, {"message": "No active task to cancel"}
                )
        except Exception as e:
            self._logger.error(f"Error cancelling task: {e}", exc_info=True)
            await self._bus.emit(
                EventTypes.ERROR,
                {"message": "Error cancelling task", "details": str(e)},
            )

    async def _handle_reset_context(self) -> None:
        """
        Handle context reset command.
        """
        try:
            # Reset the context coordinator
            await self._context.reset()
            stats = await self._resolve_context_stats()
            await self._emit_context_update(stats)
            self._logger.info("Context reset successfully")
            await self._bus.emit(
                EventTypes.INFO, {"message": "Context reset successfully"}
            )

            # Only set status to IDLE if we're not already idle
            current_state = self._state.current
            if current_state != AgentState.IDLE:
                await self._set_status(AgentState.IDLE, "Context reset")
            else:
                # Just emit a status update without changing state
                status_payload = AgentStatus(
                    status=AgentState.IDLE.value, message="Context reset"
                )
                await self._bus.emit(EventTypes.STATUS_CHANGED, status_payload)

        except Exception as e:
            self._logger.error(f"Error resetting context: {e}", exc_info=True)
            await self._bus.emit(
                EventTypes.ERROR,
                {"message": "Error resetting context", "details": str(e)},
            )

    async def _handle_refresh_status(self) -> None:
        """
        Emit a status-bar refresh payload without going through user input.
        """
        try:
            stats = await self._resolve_context_stats()
            await self._emit_context_update(stats)
        except Exception as e:
            self._logger.error(f"Error refreshing status: {e}", exc_info=True)
            await self._bus.emit(
                EventTypes.ERROR,
                {"message": "Error refreshing status", "details": str(e)},
            )

    async def _handle_toggle_auto_confirm(self, auto_confirm: bool) -> None:
        """
        Handle auto-confirm toggle command.
        """
        try:
            # Update settings or configuration
            self._logger.info(f"Toggling auto-confirm to: {auto_confirm}")
            self._auto_confirm = bool(auto_confirm)
            await self._bus.emit(
                EventTypes.AUTO_CONFIRM_CHANGED, {"auto_confirm": self._auto_confirm}
            )
            await self._bus.emit(
                EventTypes.INFO,
                {
                    "message": f"Auto-confirm {'enabled' if self._auto_confirm else 'disabled'}"
                },
            )
        except Exception as e:
            self._logger.error(f"Error toggling auto-confirm: {e}", exc_info=True)
            await self._bus.emit(
                EventTypes.ERROR,
                {"message": "Error toggling auto-confirm", "details": str(e)},
            )

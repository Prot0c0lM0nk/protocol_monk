import logging
import asyncio
from typing import Any, Optional

from protocol_monk.protocol.bus import EventBus
from protocol_monk.protocol.events import EventTypes
from protocol_monk.agent.structs import UserRequest, AgentStatus, ConfirmationResponse
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

        # We hold the confirmation future here so we can cancel it if needed
        self._current_confirmation: Optional[asyncio.Future] = None
        self._auto_confirm = bool(getattr(settings, "auto_confirm", False))

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

    async def _handle_user_input(self, payload: UserRequest) -> None:
        """
        Main Handler: User speaks -> Agent processes.
        """
        try:
            # 1. State: IDLE -> THINKING
            await self._set_status(AgentState.THINKING, "Processing user input...")

            # 2. Logic: Update Context
            stats = await self._context.add_user_message(payload.text)

            # 3. Emit Verification
            await self._bus.emit(
                EventTypes.INFO,
                {
                    "message": "Context updated",
                    "data": {
                        "total_tokens": stats.total_tokens,
                        "message_count": stats.message_count,
                    },
                },
            )

            # 4. Trigger LLM Thinking Loop (THE BRAIN)
            history = self._context._store.get_full_history()
            self._logger.info("Entering Thinking Loop...")

            response = await run_thinking_loop(
                context_history=history,
                provider=self._provider,
                bus=self._bus,
                registry=self._registry,
                settings=self._settings,
            )

            # 5. Think/Act loop: tool results are added back to context,
            # then the model gets another pass to produce a final answer.
            # We cap rounds to prevent runaway loops.
            max_tool_rounds = 3
            rounds = 0
            while response.tool_calls and rounds < max_tool_rounds:
                rounds += 1
                await self._set_status(
                    AgentState.EXECUTING,
                    f"Executing {len(response.tool_calls)} tools...",
                )

                user_rejected = False
                for tool_req in response.tool_calls:
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
                        # Store the tool_call_id for matching with incoming confirmations
                        confirmation_future._tool_call_id = tool_req.call_id
                        self._current_confirmation = confirmation_future

                    # Execute the tool with the confirmation future
                    result = await run_action_loop(
                        tool_req=tool_req,
                        registry=self._registry,
                        bus=self._bus,
                        executor=self._executor,
                        confirmation_future=confirmation_future,
                        auto_approve=self._auto_confirm,
                    )

                    # Clear the confirmation future after execution
                    if self._current_confirmation == confirmation_future:
                        self._current_confirmation = None

                    if result.error == "User rejected execution":
                        user_rejected = True
                        await self._bus.emit(
                            EventTypes.INFO,
                            {
                                "message": "Tool execution rejected. Returning control to user."
                            },
                        )
                        break

                    # Persist tool outputs to context so next model pass can use them
                    await self._context.add_tool_result(result)

                if user_rejected:
                    break

                await self._set_status(AgentState.THINKING, "Processing tool results...")
                history = self._context._store.get_full_history()
                response = await run_thinking_loop(
                    context_history=history,
                    provider=self._provider,
                    bus=self._bus,
                    registry=self._registry,
                    settings=self._settings,
                )

            if response.tool_calls:
                await self._bus.emit(
                    EventTypes.WARNING,
                    {
                        "message": "Tool loop limit reached",
                        "details": f"Stopped after {max_tool_rounds} tool rounds",
                    },
                )

            # 6. State: -> IDLE
            await self._set_status(AgentState.IDLE, "Ready")

        except Exception as e:
            self._logger.error(f"Error in main loop: {e}", exc_info=True)
            await self._set_status(AgentState.ERROR, f"System Error: {str(e)}")

    async def _set_status(self, state: AgentState, message: str) -> None:
        """
        Helper to update internal state and emit event in one go.
        """
        try:
            self._state.transition_to(state)
            status_payload = AgentStatus(status=state.value, message=message)
            await self._bus.emit(EventTypes.STATUS_CHANGED, status_payload)
        except ValueError as e:
            self._logger.critical(f"State Machine Violation: {e}")

    async def _handle_tool_confirmation(self, payload: ConfirmationResponse) -> None:
        """
        Handle TOOL_CONFIRMATION_SUBMITTED events to resolve pending confirmation futures.
        """
        try:
            self._logger.info(f"Received tool confirmation for call_id: {payload.tool_call_id}")

            # Validate payload
            if not hasattr(payload, 'tool_call_id') or not payload.tool_call_id:
                self._logger.error("Invalid confirmation payload: missing tool_call_id")
                await self._bus.emit(EventTypes.ERROR, {
                    "message": "Invalid confirmation payload",
                    "details": "Missing tool_call_id"
                })
                return

            if not hasattr(payload, 'decision') or payload.decision not in ["approved", "rejected"]:
                self._logger.error(f"Invalid confirmation decision: {payload.decision}")
                await self._bus.emit(EventTypes.ERROR, {
                    "message": "Invalid confirmation decision",
                    "details": f"Decision must be approved or rejected, got {payload.decision}"
                })
                return

            # Resolve the pending confirmation future if it exists and matches the call_id
            if (self._current_confirmation and
                not self._current_confirmation.done() and
                hasattr(self._current_confirmation, '_tool_call_id') and
                self._current_confirmation._tool_call_id == payload.tool_call_id):

                self._logger.info(f"Resolving confirmation future for call_id: {payload.tool_call_id}")
                self._current_confirmation.set_result(payload)
            else:
                self._logger.warning(f"No pending confirmation found for call_id: {payload.tool_call_id}")
                await self._bus.emit(EventTypes.WARNING, {
                    "message": "No pending confirmation found",
                    "details": f"Tool call ID {payload.tool_call_id} not found"
                })

        except Exception as e:
            self._logger.error(f"Error handling tool confirmation: {e}", exc_info=True)
            await self._bus.emit(EventTypes.ERROR, {
                "message": "Error processing tool confirmation",
                "details": str(e)
            })

    async def _handle_system_command(self, payload: dict) -> None:
        """
        Handle SYSTEM_COMMAND_ISSUED events to process system-level commands.
        """
        try:
            self._logger.info(f"Received system command: {payload}")

            # Validate payload
            if not isinstance(payload, dict):
                self._logger.error("Invalid system command payload: not a dictionary")
                await self._bus.emit(EventTypes.ERROR, {
                    "message": "Invalid system command payload",
                    "details": "Payload must be a dictionary"
                })
                return

            command = payload.get('command')
            if not command:
                self._logger.error("Invalid system command payload: missing 'command' field")
                await self._bus.emit(EventTypes.ERROR, {
                    "message": "Invalid system command payload",
                    "details": "Missing 'command' field"
                })
                return

            # Process different system commands
            if command == "cancel_current_task":
                await self._handle_cancel_task()
            elif command == "reset_context":
                await self._handle_reset_context()
            elif command == "toggle_auto_confirm":
                auto_confirm = payload.get('auto_confirm', True)
                await self._handle_toggle_auto_confirm(auto_confirm)
            else:
                self._logger.warning(f"Unknown system command: {command}")
                await self._bus.emit(EventTypes.WARNING, {
                    "message": "Unknown system command",
                    "details": f"Command '{command}' is not recognized"
                })

        except Exception as e:
            self._logger.error(f"Error handling system command: {e}", exc_info=True)
            await self._bus.emit(EventTypes.ERROR, {
                "message": "Error processing system command",
                "details": str(e)
            })

    async def _handle_cancel_task(self) -> None:
        """
        Handle task cancellation command.
        """
        try:
            if self._current_confirmation and not self._current_confirmation.done():
                self._logger.info("Cancelling current confirmation task")
                self._current_confirmation.cancel()
                self._current_confirmation = None
                await self._set_status(AgentState.IDLE, "Task cancelled by user")
                await self._bus.emit(EventTypes.INFO, {
                    "message": "Task cancelled successfully"
                })
            else:
                self._logger.info("No active task to cancel")
                await self._bus.emit(EventTypes.INFO, {
                    "message": "No active task to cancel"
                })
        except Exception as e:
            self._logger.error(f"Error cancelling task: {e}", exc_info=True)
            await self._bus.emit(EventTypes.ERROR, {
                "message": "Error cancelling task",
                "details": str(e)
            })

    async def _handle_reset_context(self) -> None:
        """
        Handle context reset command.
        """
        try:
            # Reset the context coordinator
            await self._context.reset()
            self._logger.info("Context reset successfully")
            await self._bus.emit(EventTypes.INFO, {
                "message": "Context reset successfully"
            })

            # Only set status to IDLE if we're not already idle
            current_state = self._state.current
            if current_state != AgentState.IDLE:
                await self._set_status(AgentState.IDLE, "Context reset")
            else:
                # Just emit a status update without changing state
                status_payload = AgentStatus(status=AgentState.IDLE.value, message="Context reset")
                await self._bus.emit(EventTypes.STATUS_CHANGED, status_payload)

        except Exception as e:
            self._logger.error(f"Error resetting context: {e}", exc_info=True)
            await self._bus.emit(EventTypes.ERROR, {
                "message": "Error resetting context",
                "details": str(e)
            })

    async def _handle_toggle_auto_confirm(self, auto_confirm: bool) -> None:
        """
        Handle auto-confirm toggle command.
        """
        try:
            # Update settings or configuration
            self._logger.info(f"Toggling auto-confirm to: {auto_confirm}")
            self._auto_confirm = bool(auto_confirm)
            await self._bus.emit(EventTypes.AUTO_CONFIRM_CHANGED, {
                "auto_confirm": self._auto_confirm
            })
            await self._bus.emit(EventTypes.INFO, {
                "message": f"Auto-confirm {'enabled' if self._auto_confirm else 'disabled'}"
            })
        except Exception as e:
            self._logger.error(f"Error toggling auto-confirm: {e}", exc_info=True)
            await self._bus.emit(EventTypes.ERROR, {
                "message": "Error toggling auto-confirm",
                "details": str(e)
            })

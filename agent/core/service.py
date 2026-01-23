import logging
import asyncio
from typing import Any, Optional

from protocol_monk.protocol.bus import EventBus
from protocol_monk.protocol.events import EventTypes
from protocol_monk.agent.structs import UserRequest, AgentStatus
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

    async def start(self) -> None:
        """
        Bootstraps the agent listeners.
        """
        await self._bus.subscribe(
            EventTypes.USER_INPUT_SUBMITTED, self._handle_user_input
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

            # 5. [FIX] Trigger Action Loop (THE HANDS)
            if response.tool_calls:
                await self._set_status(
                    AgentState.EXECUTING,
                    f"Executing {len(response.tool_calls)} tools...",
                )

                for tool_req in response.tool_calls:
                    # Execute the tool
                    # Note: If we needed confirmation, we would create a Future here.
                    # For now, we pass None, assuming tools are auto-approved or safe.
                    result = await run_action_loop(
                        tool_req=tool_req,
                        registry=self._registry,
                        bus=self._bus,
                        executor=self._executor,
                        confirmation_future=None,  # We will add the UI confirmation bridge later
                    )

                    # Log the result to context so the agent knows what happened
                    # (Optional: Add tool output back to conversation history?)
                    # self._context.add_tool_result(...) -> Future enhancement

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

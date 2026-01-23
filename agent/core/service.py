import logging
from typing import Optional

from protocol_monk.protocol.bus import EventBus
from protocol_monk.protocol.events import EventTypes
from protocol_monk.agent.structs import UserRequest, AgentStatus
from protocol_monk.agent.context.coordinator import ContextCoordinator
from protocol_monk.agent.core.state_machine import StateMachine, AgentState
from protocol_monk.tools.registry import ToolRegistry


class AgentService:
    """
    The Main Agent Loop.

    Responsibility:
    1. Listen for USER_INPUT.
    2. Manage Agent State (Idle -> Thinking).
    3. Update Context (via Coordinator).
    4. (Future) Call LLM.
    """

    def __init__(
        self, bus: EventBus, coordinator: ContextCoordinator, registry: ToolRegistry
    ):
        self._bus = bus
        self._context = coordinator
        self._registry = registry
        self._state = StateMachine()
        self._logger = logging.getLogger("AgentService")

    async def start(self) -> None:
        """
        Bootstraps the agent listeners.
        """
        # [FIX] Added 'await' because subscribe() now uses a lock for thread safety.
        # This fixes the RuntimeWarning where the subscription was being ignored.
        await self._bus.subscribe(EventTypes.USER_INPUT_SUBMITTED, self._handle_user_input)
        
        self._logger.info("Agent Service started and listening.")

    async def _handle_user_input(self, payload: UserRequest) -> None:
        """
        Main Handler: User speaks -> Agent processes.
        """
        try:
            # 1. State: IDLE -> THINKING
            await self._set_status(AgentState.THINKING, "Processing user input...")

            # 2. Logic: Update Context (The "Brain")
            # This triggers token counting, file tracking, and pruning automatically.
            stats = await self._context.add_user_message(payload.text)

            # 3. Emit Verification (Feedback)
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

            # 4. (Future) Trigger LLM Logic Loop Here
            # For Phase 1, we just acknowledge and finish.

            # 5. State: THINKING -> IDLE
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

            # Create typed payload
            status_payload = AgentStatus(status=state.value, message=message)

            await self._bus.emit(EventTypes.STATUS_CHANGED, status_payload)

        except ValueError as e:
            # If state transition fails, we log it critically but don't crash
            self._logger.critical(f"State Machine Violation: {e}")
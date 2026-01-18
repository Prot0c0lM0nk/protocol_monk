from enum import Enum
from typing import Set, Dict


class AgentState(str, Enum):
    IDLE = "idle"
    THINKING = "thinking"
    EXECUTING = "executing"
    ERROR = "error"
    PAUSED = "paused"  # Waiting for user confirmation


class StateMachine:
    """
    Enforces valid state transitions for the Agent.
    Prevents invalid jumps (e.g., IDLE -> EXECUTING without THINKING).
    """

    def __init__(self):
        self._current_state = AgentState.IDLE

        # Define allowed transitions
        self._transitions: Dict[AgentState, Set[AgentState]] = {
            AgentState.IDLE: {AgentState.THINKING, AgentState.ERROR},
            AgentState.THINKING: {
                AgentState.EXECUTING,
                AgentState.IDLE,
                AgentState.ERROR,
                AgentState.PAUSED,
            },
            AgentState.EXECUTING: {
                AgentState.THINKING,
                AgentState.IDLE,
                AgentState.ERROR,
                AgentState.PAUSED,
            },
            AgentState.PAUSED: {
                AgentState.EXECUTING,
                AgentState.IDLE,
                AgentState.ERROR,
            },  # Resume or Abort
            AgentState.ERROR: {AgentState.IDLE},  # Reset
        }

    @property
    def current(self) -> AgentState:
        return self._current_state

    def transition_to(self, new_state: AgentState) -> None:
        """
        Attempts to transition to a new state.
        Raises ValueError if the transition is illegal.
        """
        if new_state not in self._transitions[self._current_state]:
            raise ValueError(
                f"Invalid State Transition: {self._current_state} -> {new_state}"
            )
        self._current_state = new_state

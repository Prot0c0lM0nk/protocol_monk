#!/usr/bin/env python3
"""
TAOR Loop (Think-Act-Observe-Reflect)
=====================================
Orchestrates the agent's cognitive cycle with strict serial execution.
"""

import json
import logging
from typing import Dict, List, Optional

from agent.core_exceptions import OrchestrationError
from agent.model.exceptions import ModelError
from agent.tools.exceptions import UserCancellationError

# pylint: disable=protected-access


class TAORLoop:
    """
    The Think-Act-Observe-Reflect Loop.
    Orchestrates the agent's cognitive cycle with strict serial execution.
    """

    def __init__(self, agent):
        self.agent = agent
        self.logger = logging.getLogger(__name__)
        self.max_autonomous_iterations = 50
        self.max_consecutive_failures = 5
        self._consecutive_failures = 0

    async def run_loop(self, user_input: str) -> bool:
        """
        Main execution entry point.
        Returns True if conversation completed normally, False on fatal error.
        """
        # 0. OBSERVE (User Input)
        await self.agent.context_manager.add_message("user", user_input)

        iteration = 0
        self._consecutive_failures = 0

        try:
            while iteration < self.max_autonomous_iterations:
                iteration += 1
                should_continue = await self._execute_cycle(iteration)
                if not should_continue:
                    return True  # Normal completion or handled stop
        except KeyboardInterrupt:
            await self.agent.ui.print_warning("\n🛑 Interrupted.")
            return True

        return True

    async def _execute_cycle(self, iteration: int) -> bool:
        """
        Execute one complete Think-Act-Observe cycle.
        Returns False if the loop should terminate.
        """
        # 1. THINK (Prepare Context & Call Model)
        context = await self.agent._prepare_context()
        if context is None:
            raise OrchestrationError(
                "Failed to prepare context for model call",
                details={"iteration": iteration},
            )

        response = await self.agent._get_model_response(context)
        if response is None:
            # Interrupted
            return False
        if response is False:
            raise ModelError(
                "Model response generation failed", details={"iteration": iteration}
            )

        # 2. PARSE (Extract Intent)
        actions, _ = self.agent._parse_response(response)

        # If no actions, check for ghosts or finish
        if not actions:
            return await self._handle_no_actions(response)

        # 3. ACT (Strict Serial Execution - First action only)
        return await self._process_action(actions[0])

    async def _handle_no_actions(self, response: str) -> bool:
        """Handle cases where no tools were called."""
        if self._detect_ghost_tool(response):
            await self.agent.ui.print_warning("⚠️ Malformed tool detected. Retrying...")
            await self.agent.context_manager.add_message(
                "system", "System Alert: Invalid JSON format. Retry."
            )
            self._consecutive_failures += 1
            if self._consecutive_failures >= self.max_consecutive_failures:
                return False  # Stop loop (failure)
            return True  # Continue loop (retry)

        # Normal finish (Agent just talked)
        return False

    async def _process_action(self, action: Dict) -> bool:
        """Execute the action and record results."""
        try:
            # tool_executor expects a list
            summary = await self.agent.tool_executor.execute_tool_calls([action])
        except UserCancellationError:
            await self.agent.ui.print_warning("⛔ Task Aborted.")
            return False

        # 4. OBSERVE (Record Results)
        had_failure = await self.agent._record_results(summary)

        # Check termination
        if summary.should_finish:
            return False

        # Reset or increment counters
        if not had_failure:
            self._consecutive_failures = 0
        else:
            self._consecutive_failures += 1
            if self._consecutive_failures >= self.max_consecutive_failures:
                await self.agent.ui.print_error("⚠️ Too many consecutive failures.")
                return False

        return True  # Continue loop

    def _detect_ghost_tool(self, response: str) -> bool:
        """Enhanced detection of malformed tool calls using JSON validation."""
        try:
            # Heuristic: If it looks like JSON/Tool but failed parsing
            if "{" in response and ("action:" in response or "name:" in response):
                json.loads(response)  # If this passes, it wasn't a ghost, just text
                return False
        except json.JSONDecodeError:
            return True  # It Failed JSON parse, so it MIGHT be a ghost tool
        return False

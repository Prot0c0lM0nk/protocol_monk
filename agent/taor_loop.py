#!/usr/bin/env python3
"""
TAOR Loop (Think-Act-Observe-Reflect)
=====================================
Orchestrates the agent's cognitive cycle with strict serial execution.
"""

import asyncio
import json
import logging
from typing import Dict
from exceptions import (
    ModelError,
    OrchestrationError,
    UserCancellationError,
    ContextOverflowError,
    ToolInputValidationError,
)

# pylint: disable=protected-access


class TAORLoop:
    """
    The Think-Act-Observe-Reflect Loop.
    Orchestrates the agent's cognitive cycle with strict serial execution.
    """

    def __init__(self, agent):
        """
        Initialize the TAOR loop with agent reference.

        Args:
            agent: Reference to the main agent instance
        """
        self.agent = agent
        self.logger = logging.getLogger(__name__)
        self.max_autonomous_iterations = 50
        self.max_consecutive_failures = 5
        self._consecutive_failures = 0

    async def run_loop(self, user_input: str) -> bool:
        """
        Main execution entry point.
        Returns True if conversation completed normally, False on fatal error.

        Args:
            user_input: User's input string

        Returns:
            bool: True if completed normally, False on fatal error
        """
        # 0. OBSERVE (User Input)
        await self.agent.context_manager.add_message("user", user_input)

        iteration = 0
        self._consecutive_failures = 0

        try:
            while iteration < self.max_autonomous_iterations:
                iteration += 1

                # --- START: ERROR TRAP FOR 500/503 ---
                try:
                    should_continue = await self._execute_cycle(iteration)
                    if not should_continue:
                        return True  # Normal completion or handled stop

                except ModelError as e:
                    error_msg = str(e)
                    # Check for 500 (Internal Error), 503 (Unavailable), or Overloaded
                    if (
                        "500" in error_msg
                        or "503" in error_msg
                        or "Overloaded" in error_msg
                    ):
                        self.agent.ui.print_warning(
                            f"⚠️ Service Error (Cloud 500/503). Retrying in 5s..."
                        )
                        await asyncio.sleep(5)  # Give the server a break
                        iteration -= 1  # Don't burn an iteration on a server glitch
                        continue
                    else:
                        # Real errors (Auth, 404, etc) should still crash/stop
                        await self.agent.ui.print_error(f"🛑 Model Error: {e}")
                        return False

                except OrchestrationError as e:
                    await self.agent.ui.print_error(f"🛑 Logic Error: {e}")
                    return False
                # --- END: ERROR TRAP ---

        except KeyboardInterrupt:
            await self.agent.ui.print_warning("\n🛑 Interrupted.")
            return True

        return True

    async def _execute_cycle(self, iteration: int) -> bool:
        """
        Execute one complete Think-Act-Observe cycle.
        Returns False if the loop should terminate.

        Args:
            iteration: Current iteration number

        Returns:
            bool: False if loop should terminate, True to continue

        Raises:
            OrchestrationError: If context preparation fails
            ModelError: If model response generation fails
        """
        # 1. THINK (Prepare Context & Call Model)
        try:
            context = await self.agent._prepare_context()
        except ContextOverflowError as e:
            await self.agent.ui.print_warning(
                f"⚠️ Context too large: {e.user_hint}. Clearing some messages..."
            )
            await self.agent.context_manager.clear_old_messages()
            context = await self.agent._prepare_context()

        if context is None:
            raise OrchestrationError(
                "Failed to prepare context for model call",
                details={"iteration": iteration},
            )

        # CRITICAL: We let the exception bubble up here so the run_loop catches it.
        # We do NOT return False on exception anymore.
        response = await self.agent._get_model_response(context)

        if response is None:
            # Interrupted / Empty
            return False

        # 2. PARSE (Extract Intent)
        self.agent.logger.info(
            f"TAOR loop received response type: {type(response)}, content: {str(response)[:200]}"
        )
        actions, _ = self.agent._parse_response(response)
        self.agent.logger.info(f"TAOR loop parsed actions: {actions}")

        # Debug: Check what parsing returned

        # If no actions, check for ghosts or finish
        if not actions:
            return await self._handle_no_actions(response)

        # 3. ACT (Strict Serial Execution - All actions)
        # We loop through all actions returned by the model
        for action in actions:
            should_continue = await self._process_action(action)
            # If an action signals the loop should stop (like 'finish'), we exit early
            if not should_continue:
                return False

        return True

    async def _handle_no_actions(self, response) -> bool:
        """
        Handle cases where the initial parse in _execute_cycle didn't find actions.
        """
        # 1. Handle Ghost Tools (Strings that look like JSON but aren't)
        if isinstance(response, str) and self._detect_ghost_tool(response):
            await self.agent.ui.print_warning("⚠️ Invalid tool format. Retrying...")
            await self.agent.context_manager.add_message(
                "system", "Error: Use API tool calling."
            )
            self._consecutive_failures += 1
            return self._consecutive_failures < self.max_consecutive_failures

        # 2. Handle Structured Responses (The 'dict' case)
        if isinstance(response, dict):
            # Route the dict through the execution bridge
            # This will return True if it executes tools, or False if it's just talk
            return await self._execute_structured_response(response)

        # 3. Normal finish (Agent just talked)
        return False

    async def _execute_structured_response(self, response: dict) -> bool:
        """
        Bridge: Extracts tools from a dictionary and processes them.
        Returns True if tools were found and processed, False otherwise.
        """
        # Use the parser to get actions from the dict
        actions, _ = self.agent._parse_response(response)

        if not actions:
            # It's just a regular text response in a dict wrapper
            return False

        # Execute the tools found
        for action in actions:
            # _process_action returns True to continue the loop
            should_continue = await self._process_action(action)
            if not should_continue:
                return False

        return True

    async def _process_action(self, action: Dict) -> bool:
        """
        Execute the action and record results.
        """
        try:
            # tool_executor expects a list
            summary = await self.agent.tool_executor.execute_tool_calls([action])

        except UserCancellationError:
            await self.agent.ui.print_warning("⛔ Task Aborted.")

            # --- SCRUBBING FIX ---
            # Remove the Assistant's message that proposed this tool.
            # This prevents a broken chain (Assistant -> User) which causes 400 Errors.
            # The context effectively rewinds to before the tool was suggested.
            await self.agent.context_manager.remove_last_message()

            return False

        except ToolInputValidationError as e:
            await self.agent.ui.print_warning(f"⚠️  Invalid tool format: {e.message}")

            # --- CHAIN REPAIR FIX ---
            # Instead of adding a System message (which breaks the chain),
            # we must treat this as a failed Tool Result.
            from agent.tool_executor import ExecutionSummary
            from agent.interfaces import ToolResult

            # Create a synthetic failed result
            failure_result = ToolResult(
                success=False,
                tool_name=action.get("action", "unknown"),
                tool_call_id=action.get("id"),
                output=f"Validation Error: {e.message}",
            )

            summary = ExecutionSummary(results=[failure_result])
            # Proceed to record results normally below...

        # 4. OBSERVE (Record Results)
        # This adds the "Tool" role message, completing the chain
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

    def _detect_ghost_tool(self, response) -> bool:
        # If it's already a dict, it's not a 'ghost' string—it's parsed data.
        if isinstance(response, dict):
            return False

        # Ensure we are dealing with a string before processing
        if not isinstance(response, str):
            return False

        try:
            # Look specifically for tool calls, not any JSON-like structure
            if "```json" in response or response.strip().startswith("{"):
                # Extract just the JSON part for validation
                lines = response.split("\n")
                json_lines = []
                in_json = False

                for line in lines:
                    if line.strip() == "```json":
                        in_json = True
                        continue
                    elif line.strip() == "```" and in_json:
                        break
                    elif in_json:
                        json_lines.append(line)
                    elif line.strip().startswith("{") and not in_json:
                        json_lines.append(line)

                if json_lines:
                    json_str = "\n".join(json_lines)
                    json.loads(json_str)
                return False
        except json.JSONDecodeError:
            # If it looks like JSON but fails to parse, it's a ghost tool
            return True

        return False

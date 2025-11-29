import logging
from typing import List, Dict, Any

from agent.tools.exceptions import UserCancellationError
from agent.core_exceptions import OrchestrationError, AgentCoreError
from agent.model.exceptions import ModelError
from agent.tools.exceptions import ToolError
from agent.context.exceptions_expanded import ContextValidationError
# Circular import avoidance: We type hint generically or use string forward references if needed
# but passing 'agent' instance is standard.

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

    async def run_loop(self, user_input: str) -> bool:
        """
        Main execution entry point.
        Returns True if conversation completed normally, False on fatal error.
        """
        # 0. OBSERVE (User Input)
        await self.agent.context_manager.add_message("user", user_input)
        
        iteration = 0
        consecutive_failures = 0

        try:
            while iteration < self.max_autonomous_iterations:
                iteration += 1
                
                # 1. THINK (Prepare Context & Call Model)
                context = await self.agent._prepare_context()
                if context is None:
                    raise OrchestrationError(
                        "Failed to prepare context for model call",
                        details={"iteration": iteration}
                    )
                    
                response = await self.agent._get_model_response(context)
                if response is None: 
                    # Interrupted - this is a valid termination condition
                    return True
                if response is False:
                    raise ModelError(
                        "Model response generation failed",
                        details={"iteration": iteration}
                    )

                # 2. PARSE (Extract Intent)
                actions, has_json_content = self.agent._parse_response(response)
                
                # Handle case where no JSON tools were found (normal conversation)
                if not has_json_content and actions:
                    # This is a normal response without tool calls - not truncation
                    pass
                elif not has_json_content and not actions:
                    # No JSON content and no actions extracted - normal for plain text responses
                    pass
                
                # If no actions, the turn is done (unless ghost tool found)
                if not actions:
                    if self._detect_ghost_tool(response):
                        await self.agent.ui.print_warning("⚠️ Malformed tool detected. Retrying...")
                        await self.agent.context_manager.add_message("system", "System Alert: Invalid JSON format. Retry.")
                        consecutive_failures += 1
                        if consecutive_failures >= self.max_consecutive_failures: return False
                        continue
                    
                    # Normal finish
                    return True

                # 3. ACT (Strict Serial Execution)
                # We only execute the FIRST action. 
                # The model must OBSERVE the result before Acting again.
                # Validate that the action is properly formatted before execution
                # Get the first action (tool executor handles validation)
                current_action = actions[0]
                           
                try:
                    # Wrap in list because executor expects list
                    summary = await self.agent.tool_executor.execute_tool_calls([current_action])
                except UserCancellationError:
                    await self.agent.ui.print_warning("⛔ Task Aborted.")
                    return True

                # 4. OBSERVE & REFLECT (Record Results)
                had_failure = await self.agent._record_results(summary)
                
                # Reflect phase: Trigger any side effects like cleanup or learning
                self._reflect(summary)

                # Check termination
                if summary.should_finish:
                    return True

                # Reset counters if successful
                if not had_failure:
                    consecutive_failures = 0
                else:
                    consecutive_failures += 1
                    if consecutive_failures >= self.max_consecutive_failures:
                        await self.agent.ui.print_error("⚠️ Too many consecutive failures.")
                        return False

                # Loop continues -> Think again
                
        except KeyboardInterrupt:
            await self.agent.ui.print_warning("\n🛑 Interrupted.")
            return True
            
        return True

    def _reflect(self, summary):
        """
        Reflect phase: housekeeping and long-term memory updates.
        """
        # 1. Trigger Scratch Cleanup (Hygiene)
        # We don't delete files mid-session, but we could implement logic here 
        # if we wanted to clear files that were read. For now, we leave them for the session.
        pass

    def _detect_ghost_tool(self, response: str) -> bool:
        """Enhanced detection of malformed tool calls using JSON validation."""
        import json
        try:
            # Try to parse as JSON to detect malformed tool calls
            if "{" in response and ("action:" in response or "name:" in response):
                json.loads(response)
                return False  # Valid JSON, not a ghost tool
        except json.JSONDecodeError:
            # Malformed JSON that might contain tool calls
            return True
        return False
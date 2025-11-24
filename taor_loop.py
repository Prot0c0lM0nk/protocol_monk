"""
TAOR Loop Orchestrator - Think, Act, Observe, Reflect

This module orchestrates the core TAOR (Think-Act-Observe-Reflect) loop
for agent interactions. It coordinates between:
- Tool execution (Act)
- Context management (Observe)
- Knowledge/pattern recording (Reflect)
- Model revision requests (Think again)

This is a reusable module that can be used by both UI and CLI interfaces.
"""

from typing import Dict, Any, Optional, TYPE_CHECKING
from dataclasses import dataclass
import time

if TYPE_CHECKING:
    from agent.core import CleanMonkCodeAgent
    from tools.base import ToolResult


@dataclass
class TAORResult:
    """Result of a single TAOR cycle"""
    success: bool
    output: str
    should_continue: bool
    next_action: Optional[Dict[str, Any]] = None
    execution_time: float = 0.0


class TAORLoop:
    """
    Orchestrator for the Think-Act-Observe-Reflect loop.

    This class handles the execution of single actions within the TAOR cycle,
    ensuring proper integration with context management, knowledge graphs,
    and pattern analysis systems.
    """

    def __init__(self, agent: 'CleanMonkCodeAgent'):
        """
        Initialize TAOR loop with agent reference.

        Args:
            agent: The CleanMonkCodeAgent instance
        """
        self.agent = agent
        self.tool_registry = agent.tool_registry
        self.context_manager = agent.context_manager
        self.logger = agent.logger
        self.pattern_analyzer = getattr(agent, 'pattern_analyzer', None)
        self.knowledge_graph = getattr(agent, 'knowledge_graph', None)
        self.model_client = agent.model_client
        self.prompt_builder = agent.prompt_builder
        self.config = agent.config

    def execute_action(
        self,
        action: Dict[str, Any],
        user_guidance: Optional[str] = None
    ) -> TAORResult:
        """
        Execute a single action within the TAOR loop.

        Flow:
        1. ACT: Execute the tool
        2. OBSERVE: Add result to context
        3. REFLECT: Record in knowledge/pattern systems
        4. Return result for next step

        Args:
            action: Single action dict with 'tool' and 'arguments'
            user_guidance: Optional user guidance for MODIFY flow

        Returns:
            TAORResult with execution details
        """
        from tools.base import ToolResult

        tool_name = action.get("tool")
        arguments = action.get("arguments", {})

        # If user provided guidance, add it to context first
        if user_guidance:
            self.context_manager.add_message(
                role="user",
                content=f"[GUIDANCE] {user_guidance}"
            )

        # ACT: Execute the tool
        start_time = time.time()
        try:
            result: ToolResult = self.tool_registry.execute_tool(tool_name, **arguments)
            execution_time = time.time() - start_time

            # OBSERVE: Add result to context
            self._observe_result(tool_name, result)

            # Log the tool execution
            self.logger.log_tool_result(
                tool_name=tool_name,
                arguments=arguments,
                result=result
            )

            # REFLECT: Record in pattern/knowledge systems
            self._reflect_on_result(tool_name, arguments, result, execution_time)

            return TAORResult(
                success=result.success,
                output=result.output,
                should_continue=result.success,
                execution_time=execution_time
            )

        except Exception as e:
            error_output = f"Error executing {tool_name}: {str(e)}"
            execution_time = time.time() - start_time

            # OBSERVE: Add error to context
            self.context_manager.add_message(role="system", content=f"[ERROR] {error_output}")

            # REFLECT: Record failure
            self._reflect_on_error(tool_name, arguments, str(e))

            return TAORResult(
                success=False,
                output=error_output,
                should_continue=False,
                execution_time=execution_time
            )

    def _observe_result(self, tool_name: str, result: 'ToolResult') -> None:
        """
        OBSERVE phase: Add tool result to context for model awareness.

        Args:
            tool_name: Name of the tool executed
            result: Tool execution result
        """
        result_message = f"[TOOL RESULT: {tool_name}]\n{result.output}"
        self.context_manager.add_message(role="system", content=result_message)

    def _reflect_on_result(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        result: 'ToolResult',
        execution_time: float
    ) -> None:
        """
        REFLECT phase: Record execution in knowledge and pattern systems.

        Args:
            tool_name: Name of the tool executed
            arguments: Arguments passed to the tool
            result: Tool execution result
            execution_time: Time taken to execute
        """
        # Record in pattern analyzer
        if self.pattern_analyzer:
            try:
                from agent.patterns.base import Outcome, ContextSnapshot, ComplexityLevel

                # Create context snapshot
                context_snapshot = ContextSnapshot(
                    conversation_length=len(self.context_manager.conversation),
                    recent_tools=[tool_name],
                    task_type="tool_execution",
                    complexity=ComplexityLevel.MODERATE,
                    user_expertise="intermediate",
                    time_of_day="day",
                    working_memory_usage=0.5
                )

                # Determine outcome
                outcome = Outcome.SUCCESS if result.success else Outcome.ERROR

                # Record interaction
                self.pattern_analyzer.record_interaction(
                    tool_name=tool_name,
                    arguments=arguments,
                    outcome=outcome,
                    execution_time=execution_time,
                    context=context_snapshot.__dict__,
                    error_message=result.output if not result.success else None
                )
            except Exception as e:
                # Don't let pattern recording break execution
                self.logger.log_error(f"Pattern recording failed: {e}")

        # --- [THIS IS THE FIX] ---
        if not result.success:
            # Record failure in knowledge graph if execution failed
            if self.knowledge_graph and result.should_remember:
                try:
                    self.knowledge_graph.record_failure(
                        tool_name=tool_name,
                        arguments=arguments,
                        error_message=result.output,
                        context_summary="Action execution failed"
                    )
                except Exception as e:
                    self.logger.log_error(f"Knowledge graph failure recording failed: {e}")
        else:
            # --- [THIS IS THE NEW CODE FOR SUCCESS] ---
            # Record SUCCESSFUL facts in knowledge graph
            if self.knowledge_graph:
                try:
                    # Create a generic "fact" that the tool ran
                    # and what it produced.
                    fact_type = f"tool_success:{tool_name}"
                    fact_value = result.output
                    
                    # Create evidence for this fact
                    evidence = {
                        "tool_name": tool_name,
                        "arguments": arguments,
                        "result": result.output
                    }
                    
                    # This method signature is based on your architecture docs
                    self.knowledge_graph.add_fact(
                        fact_type=fact_type,
                        value=fact_value,
                        status="VERIFIED", # Mark this fact as verified
                        evidence=evidence
                    )
                except Exception as e:
                    self.logger.log_error(f"Knowledge graph success recording failed: {e}")

    def _reflect_on_error(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        error_message: str
    ) -> None:
        """
        REFLECT phase for errors: Record error in knowledge systems.

        Args:
            tool_name: Name of the tool that failed
            arguments: Arguments that caused the failure
            error_message: Error message
        """
        if self.knowledge_graph:
            try:
                self.knowledge_graph.record_failure(
                    tool_name=tool_name,
                    arguments=arguments,
                    error_message=error_message,
                    context_summary="Tool execution exception"
                )
            except Exception as e:
                self.logger.log_error(f"Knowledge graph error recording failed: {e}")

    async def request_model_revision(
        self,
        guidance: str,
        original_action: Dict[str, Any]
    ) -> Optional[str]:
        """
        THINK phase: Request model to revise an action based on user guidance.

        This implements the MODIFY flow:
        1. Add user guidance to context
        2. Ask model to generate a new action with the guidance
        3. Return the raw model response for the caller to parse

        Args:
            guidance: User's modification guidance
            original_action: The action user wants to modify

        Returns:
            Raw model response string or None if model fails
        """
        # Add guidance to context
        guidance_message = (
            f"[USER GUIDANCE]\n"
            f"The user wants to modify the proposed action.\n\n"
            f"Original action: {original_action.get('tool')} with args {original_action.get('arguments')}\n\n"
            f"User guidance: {guidance}\n\n"
            f"Please generate a revised monk_act with a new action that incorporates this guidance."
        )
        self.context_manager.add_message(role="user", content=guidance_message)

        # Build prompt
        system_prompt = self.prompt_builder.build_agentic_prompt(
            current_model=self.config.agent.default_model,
            user_request=guidance
        )

        # Get context
        context = self.context_manager.get_formatted_context()
        if not context or context[0].get("role") != "system":
            context.insert(0, {"role": "system", "content": system_prompt})

        try:
            # Call model for revision
            response_gen = self.model_client.get_response(
                context=context,
                force_json=False,
                stream=False
            )

            response_text = ""
            for chunk in response_gen:
                response_text += chunk

            # Add model's revision to context
            self.context_manager.add_message(role="assistant", content=response_text)
            return response_text

        except Exception as e:
            self.logger.log_error(f"Model revision failed: {e}")
            return None

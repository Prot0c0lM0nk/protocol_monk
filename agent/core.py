#!/usr/bin/env python3
"""
Protocol Monk Core Agent
========================
The central nervous system of the application.
Orchestrates the Model, the Tools, and the Context.
"""

import logging
import traceback
from pathlib import Path
from typing import Dict, Optional, Any

from config.static import settings
from agent.context import ContextManager
from agent.model_client import ModelClient
from agent.tool_executor import ToolExecutor
from agent.exceptions import ModelConfigurationError, UserCancellationError
from agent.model_manager import RuntimeModelManager
from ui.base import UI
from ui.plain import PlainUI
from utils.json_parser import extract_json_with_feedback

# Import the new logger
from utils.enhanced_logger import EnhancedLogger

class ProtocolAgent:
    """Core agent that handles the main interaction loop."""

    def __init__(
        self,
        working_dir: str = ".",
        model_name: str = settings.model.default_model,
        tool_registry = None,
        ui: Optional[UI] = None
    ):
        self.working_dir = Path(working_dir).resolve()
        self.current_model = model_name
        self.ui = ui or PlainUI()
        self.logger = logging.getLogger(__name__)
        
        # Initialize Enhanced Logger for context snapshots
        self.enhanced_logger = EnhancedLogger(self.working_dir)

        # 1. Initialize Context Manager
        self.context_manager = ContextManager(
            max_tokens=settings.model.context_window,
            working_dir=self.working_dir,
            tool_registry=tool_registry
        )

        # 2. Wiring Fix
        if tool_registry:
            tool_registry.context_manager = self.context_manager

        # 3. Initialize Managers
        self.model_manager = RuntimeModelManager()
        
        try:
            self.model_client = ModelClient(model_name=model_name)
        except ModelConfigurationError as e:
            print(f"Error: Failed to initialize model client: {e.message}")
            raise

        self.tool_executor = ToolExecutor(
            tool_registry=tool_registry,
            working_dir=self.working_dir,
            auto_confirm=False,
            ui_callback=self._handle_ui_event
        )

        self.consecutive_errors = 0
        self.max_consecutive_errors = 3

    async def async_initialize(self):
        if hasattr(self.tool_executor.tool_registry, 'async_initialize'):
            await self.tool_executor.tool_registry.async_initialize()
        await self.context_manager.async_initialize()

    async def _handle_ui_event(self, event: str, data: Dict[str, Any]) -> Any:
        if event == "confirm":
            return await self.ui.confirm_tool_call(data["tool_call"], data["auto_confirm"])
        elif event == "execution_start":
            await self.ui.display_execution_start(data["count"])
        elif event == "progress":
            await self.ui.display_progress(data["current"], data["total"])
        elif event == "tool_error":
            await self.ui.print_error(data["error"])
        elif event == "tool_rejected":
            await self.ui.print_info("Action rejected by user")
        elif event == "tool_modified":
            await self.ui.print_info("Tool parameters modified by user")
        elif event == "result":
            await self.ui.display_tool_result(data["result"], data["tool_name"])
        elif event == "task_complete":
            await self.ui.display_task_complete(data.get("summary", ""))
        elif event == "execution_complete":
            await self.ui.print_info("Tool execution complete")
        elif event == "auto_confirm_changed":
            await self.ui.set_auto_confirm(data["value"])
        return None

    async def process_request(self, user_input: str) -> bool:
        await self.context_manager.add_message("user", user_input)
        self.consecutive_errors = 0

        max_autonomous_iterations = 50
        max_failure_retries = 5
        iteration = 0
        consecutive_failures = 0

        try:
            while iteration < max_autonomous_iterations:
                iteration += 1

                # Step 1: Prepare context
                context = await self._prepare_context()
                if context is None:
                    return False

                # Step 2: Get model response
                response = await self._get_model_response(context)
                if response is None:  # Interrupted by user
                    return True
                if response is False:  # Error occurred
                    return False

                # Step 3: Parse response
                actions, is_truncated = self._parse_response(response)
                
                # Always save assistant message to history
                if response:
                    await self.context_manager.add_message("assistant", response)

                # Step 4: Handle truncation
                if is_truncated:
                    await self.ui.print_warning("⚠️ Response was cut off (Context Limit Reached).")
                    self.logger.warning("ContextLimitExceeded: Model output truncated.")
                    await self.context_manager.add_message("system", "System Note: The previous message was truncated due to length.")
                    return True

                # Step 5: If no actions, conversation turn is complete
                if not actions:
                    # Ghost Tool Detection
                    if ("\"action\":" in response or "\"name\":" in response) and "{" in response:
                        await self.ui.print_warning("⚠️ Detected malformed tool call. Retrying...")
                        await self.context_manager.add_message(
                            "system", 
                            "System Alert: Your JSON tool call was malformed. Rewrite it strictly."
                        )
                        continue
                    elif response:
                        self.consecutive_errors = 0
                        return True
                    else:
                        consecutive_failures += 1
                        if consecutive_failures >= max_failure_retries: return False
                        continue

                # Step 6: Execute actions
                try:
                    results = await self._execute_actions(actions)
                except UserCancellationError:
                    await self.ui.print_warning("⛔ Task Aborted by User.")
                    await self.context_manager.add_message("system", "User aborted the process.")
                    return True

                # Step 7: Record results
                had_failure = await self._record_results(results)

                # Check if we should finish
                if results.should_finish:
                    return True

                # Handle failures
                if had_failure:
                    consecutive_failures += 1
                    if consecutive_failures >= max_failure_retries:
                        await self.ui.print_error(f"⚠️ Max retries ({max_failure_retries}) reached")
                        return False
                    continue

                consecutive_failures = 0
                await self.ui.print_info("→ Waiting for model...")
                continue

        except KeyboardInterrupt:
            await self.ui.print_warning("\n\n🛑 Process interrupted by user.")
            return True
            
        return True

    async def clear_conversation(self):
        await self.context_manager.clear()
        await self.ui.print_info("✓ Conversation history cleared")
        
    async def get_status(self) -> Dict:
        context_stats = await self.context_manager.get_stats()
        return {
            "working_dir": str(self.working_dir),
            "current_model": self.current_model,
            "conversation_length": context_stats["total_messages"],
            "estimated_tokens": context_stats["total_tokens"],
            "token_limit": self.context_manager.max_tokens,
            "provider": self.model_client.current_provider
        }

    async def set_model(self, model_name: str):
        self.current_model = model_name
        self.model_client.set_model(model_name)
        # Update token limits
        model_manager = RuntimeModelManager()
        model_info = model_manager.get_available_models().get(model_name)
        if model_info:
            self.context_manager.accountant.max_tokens = model_info.context_window
            self.context_manager.pruner.max_tokens = model_info.context_window


    async def _prepare_context(self):
        """Prepare conversation context for model input."""
        try:
            # We just pass the model name, Manager handles the "NeuralSym" logic
            conversation_context = await self.context_manager.get_context(self.current_model)
            
            # VISIBILITY FIX: Dump the context to file so we can see what the bot sees
            self.enhanced_logger.log_context_snapshot(conversation_context)
            
            return conversation_context
        except Exception as e:
            await self.ui.print_error(f"Error getting context: {e}")
            return None

    async def _get_model_response(self, context):
        """Get model response with streaming."""
        await self.ui.start_thinking()
        
        # --- STREAMING ---
        full_response = ""
        try:
            async for chunk in self.model_client.get_response_async(
                context, stream=True
            ):
                full_response += chunk
                await self.ui.print_stream(chunk)
            return full_response
        except KeyboardInterrupt:
            await self.ui.print_warning("\n\n🛑 Interrupted by user.")
            return None  # Special signal for interruption
        except Exception as e:
            await self.ui.print_error(f"Streaming Error: {e}")
            return False  # Error signal

    def _parse_response(self, text):
        """Parse model response for tool calls."""
        collected_tool_calls, is_truncated = extract_json_with_feedback(text)
        return collected_tool_calls, is_truncated

    async def _execute_actions(self, actions):
        """Execute tool actions."""
        return await self.tool_executor.execute_tool_calls(actions)

    async def _record_results(self, summary):
        """Record tool execution results in context."""
        had_failure = False
        for result in summary.results:
            await self.context_manager.add_message(
                role="tool",
                content=result.output,
                importance=5
            )
            tool_data = getattr(result, "data", {}) or {}
        
            self.context_manager.record_tool_execution_outcome(
                tool_name=result.tool_name,
                arguments=tool_data,
                success=result.success,
                error_message=result.output if not result.success else None
            )

            if not result.success:
                had_failure = True
        
        return had_failure
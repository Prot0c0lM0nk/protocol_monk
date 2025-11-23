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

                # --- CONTEXT RETRIEVAL (Simplified) ---
                try:
                    # We just pass the model name, Manager handles the "NeuralSym" logic
                    conversation_context = await self.context_manager.get_context(self.current_model)
                    
                    # VISIBILITY FIX: Dump the context to file so we can see what the bot sees
                    self.enhanced_logger.log_context_snapshot(conversation_context)
                    
                except Exception as e:
                    await self.ui.print_error(f"Error getting context: {e}")
                    return False

                await self.ui.start_thinking()

                # --- STREAMING ---
                full_response = ""
                try:
                    async for chunk in self.model_client.get_response_async(
                        conversation_context, stream=True
                    ):
                        full_response += chunk
                        await self.ui.print_stream(chunk)
                except KeyboardInterrupt:
                    await self.ui.print_warning("\n\n🛑 Interrupted by user.")
                    return True 
                except Exception as e:
                    await self.ui.print_error(f"Streaming Error: {e}")
                    return False

                # --- PARSING & EXECUTION ---
                collected_tool_calls, is_truncated = extract_json_with_feedback(full_response)
                
                # 1. Always show the text first (The Assistant's "Thought")
                # Note: If you are streaming, this is already on screen, 
                # but we need to make sure it's saved to history.
                if full_response:
                     await self.context_manager.add_message("assistant", full_response)

                # 2. Handle Truncation
                if is_truncated:
                    await self.ui.print_warning("⚠️ Response was cut off (Context Limit Reached).")
                    self.logger.warning("ContextLimitExceeded: Model output truncated.")
                    
                    # Soft Failure: We added the partial message above, so we just stop here.
                    # We do NOT return False (which implies a crash), we return True (task done, but messy).
                    await self.context_manager.add_message("system", "System Note: The previous message was truncated due to length.")
                    return True 
                
                try:
                    if full_response:
                        await self.context_manager.add_message("assistant", full_response)

                    if collected_tool_calls:
                        self.consecutive_errors = 0
                        try:
                            execution_results = await self.tool_executor.execute_tool_calls(collected_tool_calls)

                            had_failure = False
                            for result in execution_results.results:
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

                            if execution_results.should_finish:
                                return True

                            if had_failure:
                                consecutive_failures += 1
                                if consecutive_failures >= max_failure_retries:
                                    await self.ui.print_error(f"⚠️ Max retries ({max_failure_retries}) reached")
                                    return False
                                continue

                            consecutive_failures = 0
                            await self.ui.print_info("→ Waiting for model...")
                            continue
                        
                        except UserCancellationError:
                            await self.ui.print_warning("⛔ Task Aborted by User.")
                            await self.context_manager.add_message("system", "User aborted the process.")
                            return True

                    # Ghost Tool Detection
                    elif ("\"action\":" in full_response or "\"name\":" in full_response) and "{" in full_response:
                        await self.ui.print_warning("⚠️ Detected malformed tool call. Retrying...")
                        await self.context_manager.add_message(
                            "system", 
                            "System Alert: Your JSON tool call was malformed. Rewrite it strictly."
                        )
                        continue

                    elif full_response:
                        self.consecutive_errors = 0
                        return True
                        
                    else:
                        consecutive_failures += 1
                        if consecutive_failures >= max_failure_retries: return False
                        continue

                except Exception as e:
                    await self.ui.print_error(f"Error: {e}")
                    await self.ui.print_info(traceback.format_exc())
                    return False

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
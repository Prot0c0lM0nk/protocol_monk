#!/usr/bin/env python3
"""
Protocol Monk Core Agent
========================
The central nervous system of the application.
Orchestrates the Model, the Tools, and the Context via TAOR Loop.
"""

import logging
from pathlib import Path
from typing import Dict, Optional, Any, List, Tuple

from config.static import settings
from agent.context import ContextManager
from agent.model_client import ModelClient
from agent.tool_executor import ToolExecutor, ExecutionSummary
from agent.model.exceptions import ModelConfigurationError
from agent.model_manager import RuntimeModelManager
from ui.base import UI
from ui.plain import PlainUI
from utils.json_parser import extract_json_with_feedback
from utils.enhanced_logger import EnhancedLogger

# NEW IMPORTS
from agent.taor_loop import TAORLoop
from agent.scratch_manager import ScratchManager
from agent.core_exceptions import OrchestrationError, AgentCoreError
from agent.model.exceptions import ModelError
from agent.tools.exceptions import ToolError
from agent.taor_loop import TAORLoop
from agent.scratch_manager import ScratchManager

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
        
        self.enhanced_logger = EnhancedLogger(self.working_dir)

        # 1. Components
        self.context_manager = ContextManager(
            max_tokens=settings.model.context_window,
            working_dir=self.working_dir,
            tool_registry=tool_registry
        )
        
        # Wiring
        if tool_registry:
            tool_registry.context_manager = self.context_manager

        self.model_manager = RuntimeModelManager()
        
        # 2. Scratch Manager (Fixes Infinite Writes)
        self.scratch_manager = ScratchManager(self.working_dir)

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

        # 3. TAOR Loop (The Immutable Orchestrator)
        self.taor_loop = TAORLoop(self)

    async def async_initialize(self):
        if hasattr(self.tool_executor.tool_registry, 'async_initialize'):
            await self.tool_executor.tool_registry.async_initialize()
        await self.context_manager.async_initialize()

    async def _handle_ui_event(self, event: str, data: Dict[str, Any]) -> Any:
        # Pass-through to UI
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
        elif event == "auto_confirm_changed":
            await self.ui.set_auto_confirm(data["value"])
        return None

    async def process_request(self, user_input: str) -> bool:
        """Delegate to TAOR Loop."""
        return await self.taor_loop.run_loop(user_input)

    # --- Helpers called by TAOR Loop ---

    async def _prepare_context(self) -> List[Dict]:
        try:
            context = await self.context_manager.get_context(self.current_model)
            self.enhanced_logger.log_context_snapshot(context)
            return context
        except Exception as e:
            await self.ui.print_error(f"Error getting context: {e}")
            return None

    async def _get_model_response(self, context: List[Dict]):
        await self.ui.start_thinking()
        full_response = ""
        try:
            async for chunk in self.model_client.get_response_async(context, stream=True):
                full_response += chunk
                await self.ui.print_stream(chunk)
            
            # Save Assistant thought
            if full_response:
                await self.context_manager.add_message("assistant", full_response)
            
            return full_response
        except KeyboardInterrupt:
            await self.ui.print_warning("\n🛑 Interrupted.")
            return None
        except Exception as e:
            await self.ui.print_error(f"Streaming Error: {e}")
            return False

    def _parse_response(self, text: str) -> Tuple[List[Dict], bool]:
        return extract_json_with_feedback(text)

    async def _record_results(self, summary: ExecutionSummary) -> bool:
        """Record results and return True if any failures occurred."""
        had_failure = False
        for result in summary.results:
            await self.context_manager.add_message("tool", result.output, importance=5)
            
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

    # --- Legacy Support Methods ---
    async def clear_conversation(self):
        await self.context_manager.clear()
        await self.ui.print_info("✓ Cleared.")
        
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
        model_manager = RuntimeModelManager()
        model_info = model_manager.get_available_models().get(model_name)
        if model_info:
            self.context_manager.accountant.max_tokens = model_info.context_window
            self.context_manager.pruner.max_tokens = model_info.context_window
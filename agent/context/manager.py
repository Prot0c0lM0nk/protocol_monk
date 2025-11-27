import logging
import asyncio
from pathlib import Path
from typing import List, Dict, Optional, TYPE_CHECKING
from config.static import settings
from agent import exceptions

# Component imports
from .message import Message
from .token_accountant import TokenAccountant
from .file_tracker import FileTracker
from .pruner import ContextPruner

# NeuralSym integration
from .neural_sym_integration import NeuralSymContextManager, NEURALSYM_AVAILABLE

if TYPE_CHECKING:
    from tools.registry import ToolRegistry

class ContextManager:
    """
    Manages conversation history and coordinates token budgeting.
    Acts as the central hub for the ProtocolAgent's memory.
    """
    def __init__(
        self,
        max_tokens: int = 16384,
        working_dir: Optional[Path] = None,
        tokenizer = None,
        tool_registry: Optional['ToolRegistry'] = None
    ):
        self.logger = logging.getLogger(__name__)
        self.tool_registry = tool_registry
        self.conversation: List[Message] = []
        self._lock = asyncio.Lock()
        self.system_message = "[System prompt not yet initialized. Call async_initialize()]"
        
        # Instantiate components
        self.accountant = TokenAccountant(max_tokens=max_tokens, tokenizer=tokenizer)
        self.tracker = FileTracker(working_dir=working_dir or Path.cwd())
        self.pruner = ContextPruner(max_tokens=max_tokens)
        
        # Initialize NeuralSym integration if available
        if NEURALSYM_AVAILABLE:
            self.neural_sym = NeuralSymContextManager(working_dir=working_dir or Path.cwd())
        else:
            self.neural_sym = None

    async def async_initialize(self):
        """Initialize async components and load the system prompt from disk."""
        self.system_message = await self._build_system_message()
        self.accountant.recalculate(self.system_message, self.conversation)

    async def _build_system_message(self) -> str:
        """Reads the system prompt template and injects tool definitions."""
        try:
            # Run file I/O in a separate thread to avoid blocking
            prompt_template = await asyncio.to_thread(
                settings.filesystem.system_prompt_file.read_text, encoding='utf-8'
            )
            
            if self.tool_registry and hasattr(self.tool_registry, 'get_formatted_tool_schemas'):
                tool_definitions = await self.tool_registry.get_formatted_tool_schemas()
            else:
                tool_definitions = "[ERROR: Tool registry not available. Tools will not work.]"
                
            return prompt_template.replace("{{AVAILABLE_TOOLS_SECTION}}", tool_definitions)
            
        except FileNotFoundError as e:
            error_msg = f"System prompt template not found at: {settings.filesystem.system_prompt_file}."
            self.logger.critical(error_msg, exc_info=True)
            raise exceptions.ConfigurationError(message=error_msg, root_cause=e)
        except Exception as e:
            error_msg = f"Failed to build system prompt: {e}"
            self.logger.error(error_msg, exc_info=True)
            return f"[ERROR] {error_msg}"

    async def add_message(self, role: str, content: str, importance: Optional[int] = None):
        """
        Add a message to the conversation. 
        Handles token counting, pruning, and file content management automatically.
        """
        async with self._lock:
            # Log meaningful information about what's being added
            content_preview = content[:50] + "..." if len(content) > 50 else content
            self.logger.debug(f"Adding {role} message: {content_preview}")

            # 1. Estimate tokens
            new_tokens = self.accountant.estimate(content)

            # 2. Prune if budget exceeded
            if not self.accountant.check_budget(new_tokens):
                self.logger.info("Context approaching limit, pruning...")
                self.conversation = self.pruner.prune(self.conversation, self.accountant)
                self.accountant.recalculate(self.system_message, self.conversation)

            # 3. Optimized File Check
            if len(content) < 256 and "\n" not in content:
                possible_file = self.tracker.working_dir / content
                if possible_file.exists() and possible_file.is_file():
                    await self.tracker.replace_old_file_content(content, self.conversation)

            # 4. Add the new message
            if importance is None:
                importance = 5 if role == "tool" else 3
            
            msg = Message(role=role, content=content, importance=importance)
            self.conversation.append(msg)
            
            # 5. Update token count
            self.accountant.add(new_tokens)

    async def add_user_message(self, content: str, importance: int = 4):
        await self.add_message("user", content, importance)

    async def add_assistant_message(self, content: str, importance: int = 3):
        await self.add_message("assistant", content, importance)

    async def get_context(self, model_name: str = None) -> List[Dict]:
        """
        Formats the conversation for the LLM API.
        automatically applies NeuralSym enhancement if the model is small/weak.
        """
        # 1. Get the base context (System + History)
        base_context = await self._get_base_context()
        
        # 2. Check if we need to enhance it (Small Model Logic)
        if model_name and self.neural_sym:
            # Check if model is small (contains size indicators like 8b, 4b, 2b, 1.7b, 0.6b, etc.)
            is_small_model = any(x in model_name.lower() for x in ["8b", "4b", "2b", "1.7b", "0.6b", "small", "mini", "tiny"])
            if is_small_model:
                try:
                    return await self.neural_sym.get_enhanced_context(base_context, model_name)
                except Exception as e:
                    self.logger.warning(f"NeuralSym enhancement failed (falling back to base): {e}")
        
        return base_context

    async def _get_base_context(self) -> List[Dict]:
        """Standard context construction without AI enhancement."""
        async with self._lock:
            context = [{"role": "system", "content": self.system_message}]
            for msg in self.conversation:
                context.append({"role": msg.role, "content": msg.content})
            return context

    async def clear(self):
        """Resets the entire context state."""
        async with self._lock:
            self.conversation = []
            await self.tracker.clear()
            self.accountant.recalculate(self.system_message, self.conversation)

    @property
    def max_tokens(self) -> int:
        return self.accountant.max_tokens

    def get_total_tokens(self) -> int:
        """Get the current total token count."""
        return self.accountant.total_tokens

    async def get_stats(self) -> Dict:
        """Returns current usage statistics."""
        async with self._lock:
            stats = self.accountant.get_stats()
            stats["total_messages"] = len(self.conversation)
            stats["files_tracked"] = len(self.tracker.files_shown)
            return stats

    def prune_context(self, strategy: str, target_limit: int):
        """Prune context based on strategy and target limit."""
        if strategy in ["strict", "archive"]:
            self.conversation = self.pruner.prune(self.conversation, self.accountant)
        elif strategy == "smart":
             if len(self.conversation) > 2:
                self.conversation = self.conversation[-2:]
        
        self.accountant.recalculate(self.system_message, self.conversation)

    # --- Neural Sym Passthrough Methods ---
    
    def record_tool_execution_outcome(self, *args, **kwargs):
        if self.neural_sym:
            try:
                self.neural_sym.record_interaction_outcome(*args, **kwargs)
            except Exception:
                pass
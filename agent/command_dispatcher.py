#!/usr/bin/env python3
"""
Command Dispatcher Module

Centralized handling of slash commands to clean up main.py
"""

from typing import Optional, Dict, List
from agent.monk import ProtocolAgent
from ui.base import UI
from agent.model_manager import RuntimeModelManager
from config.static import settings
import logging

# Reuse the blessing from main.py
BLESSING = """☦ Go in peace. May your code compile without warning. ☦"""

class CommandDispatcher:
    """Centralized dispatcher for slash commands."""
    
    def __init__(self, agent: ProtocolAgent):
        self.agent = agent
        self.ui = agent.ui
        self.logger = logging.getLogger(__name__)
    
    async def dispatch(self, user_input: str) -> Optional[bool]:
        """Process slash commands and return appropriate signals.
        
        Returns:
            False: Quit command received
            True: Command handled successfully
            None: Not a command, should process as chat
        """
        if not user_input.startswith('/'):
            return None
        
        cmd = user_input.strip().lower()
        
        if cmd == '/quit':
            await self.ui.print_info(BLESSING)
            return False
        elif cmd == '/help':
            await self._handle_help()
            return True
        elif cmd == '/status':
            await self._handle_status()
            return True
        elif cmd == '/clear':
            await self.agent.clear_conversation()
            return True
        elif cmd.startswith('/model'):
            await self._handle_model_switch()
            return True
        else:
            await self.ui.print_error("Unknown command")
            return True
    
    async def _handle_help(self):
        """Display help information."""
        help_text = """The Protocol Commands:

/help     - Display this wisdom
/status   - View current state
/model    - Switch to a different model
/clear    - Clear conversation history
/quit     - Exit with blessing
"""
        await self.ui.print_info(help_text)
    
    async def _handle_status(self):
        """Display agent status."""
        stats = await self.agent.get_status()
        from config.session import get_active_session
        session = get_active_session()
        
        env_info = "system"
        if session.preferred_env:
            env_info = f"conda: {session.preferred_env}"
        elif session.venv_path:
            env_info = f"venv: {session.venv_path}"
        elif session.is_python_project:
            env_info = "system Python"
        else:
            env_info = "general directory"

        status_text = f"""Current State:

🤖 Model: {stats['current_model']}
🔌 Provider: {stats['provider']}
📁 Working Directory: {session.directory_name}
   {stats['working_dir']}
🐍 Environment: {env_info}

💬 Conversation Length: {stats['conversation_length']} messages
🧮 Token Usage: {stats['estimated_tokens']:,} / {stats['token_limit']:,} ({(stats['estimated_tokens']/stats['token_limit']*100):.1f}%)
"""
        await self.ui.print_info(status_text)
    
    async def _handle_model_switch(self):
        """Handle the model switch command with guardrail workflow."""
        model_manager = RuntimeModelManager()
        available_models = model_manager.get_available_models()
        
        await self.ui.print_info("Available Models:")
        model_list = list(available_models.keys())
        
        # Safe display loop
        for i, model_name in enumerate(model_list, 1):
            # Handle both object and dict access safely
            m = available_models[model_name]
            prov = getattr(m, 'provider', m.get('provider', 'unknown') if isinstance(m, dict) else 'unknown')
            ctx = getattr(m, 'context_window', m.get('context_window', 0) if isinstance(m, dict) else 0)
            await self.ui.print_info(f"  {i}. {model_name} ({prov}, {ctx:,} tokens)")
        
        try:
            choice = await self.ui.prompt_user("\nSelect a model (enter number or name): ")
            choice = choice.strip()
            
            if choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(model_list):
                    selected_model = model_list[idx]
                else:
                    await self.ui.print_error("Invalid selection.")
                    return None
            else:
                if choice in available_models:
                    selected_model = choice
                else:
                    await self.ui.print_error(f"Model '{choice}' not found.")
                    return None
            
            # Guardrail Logic
            current_tokens = self.agent.context_manager.get_total_tokens()
            switch_report = model_manager.assess_switch(current_tokens, selected_model)
            
            if switch_report.safe:
                await self.agent.set_model(selected_model)
                await self.ui.print_info(f"✅ Model switched to: {selected_model}")
            else:
                await self.ui.print_warning(f"⚠️  Context Warning: {switch_report.message}")
                await self.ui.print_warning(f"Current tokens: {switch_report.current_tokens:,}")
                await self.ui.print_warning(f"Target limit: {switch_report.target_limit:,}")
                
                action = await self.ui.prompt_user("Prune, Archive, or Cancel? (p/a/c): ")
                action = action.strip().lower()
                
                if action in ['p', 'prune']:
                    self.agent.context_manager.prune_context("strict", switch_report.target_limit)
                    await self.agent.set_model(selected_model)
                    await self.ui.print_info(f"✅ Context pruned and model switched to: {selected_model}")
                elif action in ['a', 'archive']:
                    self.agent.context_manager.prune_context("archive", switch_report.target_limit)
                    await self.agent.set_model(selected_model)
                    await self.ui.print_info(f"✅ Context archived and model switched to: {selected_model}")
                else:
                    await self.ui.print_info("Model switch cancelled.")
                    return None
            
            return selected_model
                    
        except ValueError as e:
            await self.ui.print_error(f"Invalid model selection: {e}")
            return None
        except KeyError as e:
            await self.ui.print_error(f"Model configuration error: {e}")
            return None
        except RuntimeError as e:
            await self.ui.print_error(f"Runtime error during model switch: {e}")
            return None
        except Exception as e:
            await self.ui.print_error(f"Unexpected error during model switch: {e}")
            self.logger.error(f"Unexpected error in model switch: {e}", exc_info=True)
            return None
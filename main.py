#!/usr/bin/env python3
"""
Protocol Monk - Terminal AI Coding Assistant
=============================================

"The Protocol is a path. A discipline. A way of seeing code not as chaos,
but as sacred geometry waiting to be understood."

Matrix-Orthodox themed terminal assistant for coding tasks.
"""

import asyncio
import sys
import logging
from pathlib import Path

from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory

# Import config
from config.static import settings
from config.session import initialize_session, get_active_session

# Import core components
from agent.core import ProtocolAgent
from agent import exceptions
from tools.registry import ToolRegistry
from ui.base import UI
from ui.plain import PlainUI

# Import Model Manager
from agent.model_manager import RuntimeModelManager

# =============================================================================
# LOGGING SETUP
# =============================================================================

def setup_logging():
    """
    Configure the root logger so all modules write to the debug file.
    """
    if settings.debug.debug_execution_logging:
        log_path = Path(settings.debug.debug_log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        file_handler = logging.FileHandler(str(log_path), mode='w')
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        file_handler.setFormatter(formatter)
        
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.DEBUG)
        root_logger.addHandler(file_handler)
        
        from utils.debug_logger import _logger
        _logger.configure_file_logging(True, str(log_path))
    else:
        from utils.debug_logger import _logger
        _logger.configure_file_logging(False, "")

# =============================================================================
# BRANDING & UI HELPERS
# =============================================================================

MORPHEUS_GREETING = """╔═══════════════════════════════════════════════╗
║                                               ║
║   ☦  P R O T O C O L   M O N K  ☦           ║
║                                               ║
║   "What if I told you... the code was never broken?" ║
║                                               ║
╚═══════════════════════════════════════════════╝

You stand at the threshold between chaos and order.
The Protocol awaits your command.

Type /help for guidance. Type /quit to return to the desert of the real.
"""

BLESSING = """☦ Go in peace. May your code compile without warning. ☦"""

async def display_startup_animation(ui: UI):
    """Display Matrix-style startup sequence."""
    frames = [
        "Initializing Protocol...",
        "Loading Orthodox principles...",
        "Connecting to the Source...",
        "✓ Protocol ready"
    ]
    for frame in frames:
        await ui.display_startup_frame(frame)
        await asyncio.sleep(0.3)
    await ui.display_startup_frame("")

async def display_status(agent: ProtocolAgent):
    """Display agent status."""
    stats = await agent.get_status()
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
    await agent.ui.print_info(status_text)

async def display_help(agent: ProtocolAgent):
    help_text = """The Protocol Commands:

/help     - Display this wisdom
/status   - View current state
/model    - Switch to a different model
/clear    - Clear conversation history
/quit     - Exit with blessing
"""
    await agent.ui.print_info(help_text)

async def handle_model_switch_command(agent: ProtocolAgent, ui: UI):
    """Handle the model switch command with guardrail workflow."""
    model_manager = RuntimeModelManager()
    available_models = model_manager.get_available_models()
    
    await ui.print_info("Available Models:")
    model_list = list(available_models.keys())
    
    # Safe display loop
    for i, model_name in enumerate(model_list, 1):
        # Handle both object and dict access safely
        m = available_models[model_name]
        prov = getattr(m, 'provider', m.get('provider', 'unknown') if isinstance(m, dict) else 'unknown')
        ctx = getattr(m, 'context_window', m.get('context_window', 0) if isinstance(m, dict) else 0)
        await ui.print_info(f"  {i}. {model_name} ({prov}, {ctx:,} tokens)")
    
    try:
        choice = await ui.prompt_user("\nSelect a model (enter number or name): ")
        choice = choice.strip()
        
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(model_list):
                selected_model = model_list[idx]
            else:
                await ui.print_error("Invalid selection.")
                return None
        else:
            if choice in available_models:
                selected_model = choice
            else:
                await ui.print_error(f"Model '{choice}' not found.")
                return None
        
        # Startup phase check
        if agent is None:
            await ui.print_info(f"\nSelected model: {selected_model}")
            return selected_model
        
        # Guardrail Logic
        current_tokens = agent.context_manager.get_total_tokens()
        switch_report = model_manager.assess_switch(current_tokens, selected_model)
        
        if switch_report.safe:
            await agent.set_model(selected_model)
            await ui.print_info(f"✅ Model switched to: {selected_model}")
        else:
            await ui.print_warning(f"⚠️  Context Warning: {switch_report.message}")
            await ui.print_warning(f"Current tokens: {switch_report.current_tokens:,}")
            await ui.print_warning(f"Target limit: {switch_report.target_limit:,}")
            
            action = await ui.prompt_user("Prune, Archive, or Cancel? (p/a/c): ")
            action = action.strip().lower()
            
            if action in ['p', 'prune']:
                agent.context_manager.prune_context("strict", switch_report.target_limit)
                await agent.set_model(selected_model)
                await ui.print_info(f"✅ Context pruned and model switched to: {selected_model}")
            elif action in ['a', 'archive']:
                agent.context_manager.prune_context("archive", switch_report.target_limit)
                await agent.set_model(selected_model)
                await ui.print_info(f"✅ Context archived and model switched to: {selected_model}")
            else:
                await ui.print_info("Model switch cancelled.")
                return None
        
        return selected_model
                
    except Exception as e:
        await ui.print_error(f"Error during model switch: {e}")
        return None

async def process_user_input(agent: ProtocolAgent, user_input: str) -> bool:
    cmd = user_input.strip().lower()
    
    if cmd == '/quit':
        await agent.ui.print_info(BLESSING)
        return False
    elif cmd == '/help':
        await display_help(agent)
        return True
    elif cmd == '/status':
        await display_status(agent)
        return True
    elif cmd == '/clear':
        await agent.clear_conversation()
        return True
    elif cmd.startswith('/model'):
        await handle_model_switch_command(agent, agent.ui)
        return True
    
    if user_input:
        try:
            await agent.process_request(user_input)
            await agent.ui.print_info("")
        except KeyboardInterrupt:
            await agent.ui.print_warning("Operation interrupted by user.")
            await agent.ui.print_info("")
        
    return True

async def main():
    """Main entry point."""
    agent = None
    
    try:
        setup_logging()
        use_rich_ui = "--rich" in sys.argv
        use_tui = "--tui" in sys.argv
        
        session = initialize_session()
        
        tool_registry = ToolRegistry(
            working_dir=session.working_dir,
            preferred_env=session.preferred_env,
            venv_path=session.venv_path
        )

        # Initialize UI
        if use_tui:
            from ui.textual.app import MonkCodeTUI
            app = MonkCodeTUI(agent)
            app.run()
            return
        elif use_rich_ui:
            from ui.rich_ui import RichUI 
            ui = RichUI()
        else:
            ui = PlainUI()
        
        # ---------------------------------------------------------
        # NEW STARTUP SEQUENCE (FIXED)
        # ---------------------------------------------------------
        model_manager = RuntimeModelManager()
        current_model = settings.model.default_model
        selected_model = current_model  # Default to current model
        if use_rich_ui:
            from rich.panel import Panel
            from ui.styles import console
            console.print()
            console.print(Panel(
                f"Target Model: [bold holy.gold]{current_model}[/]",
                title="[dim]System Configuration[/]",
                border_style="dim white",
                padding=(1, 2)
            ))
        
        # Actually prompt (assuming rich_ui.py prompt_user has console.print fix)
        choice = await ui.prompt_user("Initialize with this model? (Y/n)")
        
        if choice.strip().lower() in ['n', 'no']:
            # Safe fetch
            available_models = model_manager.get_available_models()
            # Convert dict values to list safely
            models = list(available_models.values()) if available_models else []
            
            if models:
                await ui.display_model_list(models, current_model)
                
                new_model_name = await ui.prompt_user("Enter model name to select:")
                if new_model_name:
                    # Safe name extraction
                    valid_names = []
                    for m in models:
                        # Handle if m is dict or object
                        name = getattr(m, 'name', m.get('name') if isinstance(m, dict) else str(m))
                        valid_names.append(name)
                    
                    if new_model_name in valid_names:
                        settings.model.update_model(new_model_name)  # Use the new method
                        current_model = new_model_name
                        selected_model = new_model_name  # Also update selected_model
                        await ui.print_info(f"✓ Target updated to: {current_model}")
                    else:
                        await ui.print_warning(f"Model '{new_model_name}' not found. Using default.")
            else:
                 await ui.print_warning("No models detected (Scanner empty). Continuing with default.")

        # selected_model is now properly set whether user changed it or not
        # ---------------------------------------------------------
        # Initialize Agent
        # ---------------------------------------------------------
        agent = ProtocolAgent(
            working_dir=session.working_dir,
            model_name=selected_model,
            tool_registry=tool_registry,
            ui=ui
        )
        
        # Initialize Enhanced Logger
        from utils.enhanced_logger import EnhancedLogger
        enhanced_logger = EnhancedLogger()
        
        await agent.async_initialize()
        
        validation_errors = settings.validate()
        if validation_errors:
            await agent.ui.print_warning("Configuration validation failed:")
            for err in validation_errors:
                await agent.ui.print_warning(f"  - {err}")
                
        await display_startup_animation(agent.ui)
        await agent.ui.display_startup_banner(MORPHEUS_GREETING)
        
        # Main Loop
        if use_rich_ui:
            while True:
                try:
                    user_input = await agent.ui.prompt_user("Next command")
                except (EOFError, KeyboardInterrupt):
                    print("\nReceived interrupt signal. Exiting...")
                    break
                
                if not await process_user_input(agent, user_input):
                    break
                await asyncio.sleep(0.1)
        else:
            session_history = FileHistory(settings.filesystem.history_file)
            session_prompt = PromptSession(history=session_history)
            while True:
                try:
                    user_input = await asyncio.to_thread(session_prompt.prompt, "☦> ")
                    if not user_input.strip():
                        continue
                    if not await process_user_input(agent, user_input):
                        break
                except (OSError, RuntimeError, EOFError):
                    break
                except KeyboardInterrupt:
                    print("\nReceived interrupt signal. Exiting...")
                    break
                    
    except exceptions.ConfigurationError as e:
        print(f"❌ Config Error: {e.message}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"❌ Unexpected error: {e}", file=sys.stderr)
        logging.getLogger().critical("Unexpected crash", exc_info=True)
        sys.exit(1)
    finally:
        try:
            if 'enhanced_logger' in locals():
                enhanced_logger.close_session()
        except Exception:
            pass
        try:
            from utils.debug_logger import close_debug_log
            close_debug_log()
        except Exception:
            pass
        if agent:
            try:
                await agent.model_client.close()
            except Exception:
                pass

if __name__ == "__main__":
    asyncio.run(main())
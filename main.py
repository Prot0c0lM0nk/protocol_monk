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
from agent.command_dispatcher import CommandDispatcher
from tools.registry import ToolRegistry
from ui.base import UI
from ui.plain import PlainUI

# Import Model Manager
from agent.model_manager import RuntimeModelManager
# Import exceptions
from agent import exceptions

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

async def process_user_input(agent: ProtocolAgent, dispatcher: CommandDispatcher, user_input: str) -> bool:
    """Process user input using the command dispatcher."""
    result = await dispatcher.dispatch(user_input)
    
    if result is False:  # Quit command
        return False
    elif result is True:  # Command handled
        return True
    elif result is None:  # Not a command, process as chat
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
        
        # Initialize Command Dispatcher
        dispatcher = CommandDispatcher(agent)
        
        # Main Loop
        while True:
            try:
                user_input = await agent.ui.prompt_user("Next command")
                if not await process_user_input(agent, dispatcher, user_input):
                    break
            except (EOFError, KeyboardInterrupt):
                print("\nReceived interrupt signal. Exiting...")
                break
        
        session_history = FileHistory(settings.filesystem.history_file)
        session_prompt = PromptSession(history=session_history)
        while True:
            try:
                user_input = await asyncio.to_thread(session_prompt.prompt, "☦> ")
                if not user_input.strip():
                    continue
                if not await process_user_input(agent, dispatcher, user_input):
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
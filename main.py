#!/usr/bin/env python3
"""
Protocol Monk - Terminal AI Coding Assistant
=============================================

"The Protocol is a path. A discipline. A way of seeing code not as chaos,
but as sacred geometry waiting to be understood."

Matrix-Orthodox themed terminal assistant for coding tasks.
"""

import asyncio
import logging
import sys
from pathlib import Path
from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from typing import Optional, Tuple

from exceptions import (
    ConfigurationError,
    SessionInitializationError,
    UIInitializationError,
    ToolRegistryError,
    ModelClientError,
    ConfigFileError,
    DirectorySelectionError,
    ModelConfigError,
    ValidationError,
)
from agent.command_dispatcher import CommandDispatcher
from agent.model_manager import RuntimeModelManager

# Import Agent & Core
from agent.monk import ProtocolAgent
from config.session import initialize_session

# Import config
from config.static import settings

# Import Tools & Utils
from tools.registry import ToolRegistry

# Import UI
from ui.base import UI
from ui.plain import PlainUI
from ui.rich_ui import RichUI
#from ui.textual.app import ProtocolMonkApp

from utils.debug_logger import _logger, close_debug_log
from utils.enhanced_logger import EnhancedLogger

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

        file_handler = logging.FileHandler(str(log_path), mode="w")
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        file_handler.setFormatter(formatter)

        root_logger = logging.getLogger()
        root_logger.setLevel(logging.DEBUG)
        root_logger.addHandler(file_handler)

        _logger.configure_file_logging(True, str(log_path))
    else:
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


async def display_startup_animation(ui: UI):
    """Display Matrix-style startup sequence."""
    frames = [
        "Initializing Protocol...",
        "Loading Orthodox principles...",
        "Connecting to the Source...",
        "✓ Protocol ready",
    ]
    for frame in frames:
        await ui.display_startup_frame(frame)
        await asyncio.sleep(0.3)
    await ui.display_startup_frame("")


async def process_user_input(
    agent: ProtocolAgent, dispatcher: CommandDispatcher, user_input: str
) -> bool:
    """Process user input using the command dispatcher."""
    result = await dispatcher.dispatch(user_input)

    if result is False:  # Quit command
        return False
    if result is True:  # Command handled
        return True

    # Not a command, process as chat
    if user_input:
        try:
            await agent.process_request(user_input)
            await agent.ui.print_info("")
        except KeyboardInterrupt:
            await agent.ui.print_warning("Operation interrupted by user.")
            await agent.ui.print_info("")
    return True


def parse_arguments():
    """Parse command line arguments."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Protocol Monk - Terminal AI Coding Assistant"
    )
    parser.add_argument("--rich", action="store_true", help="Use Rich UI")
    parser.add_argument("--tui", action="store_true", help="Use Textual TUI")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")

    return parser.parse_args()


# =============================================================================
# MAIN ORCHESTRATION
# =============================================================================


async def main():
    """Main entry point orchestrator."""
    agent: Optional[ProtocolAgent] = None
    enhanced_logger: Optional[EnhancedLogger] = None

    try:
        setup_logging()

        # 1. Initialization
        try:
            session = initialize_session()
        except Exception as e:
            raise SessionInitializationError(
                f"Failed to initialize session: {e}"
            ) from e

        try:
            args = parse_arguments()
            use_rich = args.rich
            use_tui = args.tui
            ui = _select_ui_mode(use_rich, use_tui)
        except Exception as e:
            raise UIInitializationError(f"Failed to initialize UI: {e}") from e

        # 2. Tool Registry
        try:
            tool_registry = ToolRegistry(
                working_dir=session.working_dir,
                preferred_env=session.preferred_env,
                venv_path=session.venv_path,
            )
        except Exception as e:
            raise ToolRegistryError(f"Failed to initialize tool registry: {e}") from e

        # 3. Model Selection (Interactive)
        try:
            selected_model, selected_provider = await _configure_model(
                ui, use_tui, use_rich
            )
        except Exception as e:
            raise ModelClientError(f"Failed to configure model: {e}") from e

        # 4. Agent Setup
        try:
            agent = ProtocolAgent(
                working_dir=session.working_dir,
                model_name=selected_model,
                provider=selected_provider,
                tool_registry=tool_registry,
                ui=ui,
            )
        except Exception as e:
            raise ModelClientError(f"Failed to initialize agent: {e}") from e

        try:
            enhanced_logger = EnhancedLogger()
            await agent.async_initialize()
        except Exception as e:
            raise ModelClientError(f"Failed to initialize agent components: {e}") from e

        # 5. Run Interface
        #if use_tui:
            await _run_tui(agent)
        else:
            await _run_cli(agent, use_rich)

    except ConfigurationError as e:
        print(f"❌ Config Error: {e.message}", file=sys.stderr)
        sys.exit(1)
    except SessionInitializationError as e:
        print(f"❌ Session Error: {e.message}", file=sys.stderr)
        sys.exit(1)
    except UIInitializationError as e:
        print(f"❌ UI Error: {e.message}", file=sys.stderr)
        sys.exit(1)
    except ToolRegistryError as e:
        print(f"❌ Tool Registry Error: {e.message}", file=sys.stderr)
        sys.exit(1)
    except ModelClientError as e:
        print(f"❌ Model Error: {e.message}", file=sys.stderr)
        sys.exit(1)
    except ConfigFileError as e:
        print(f"❌ Config File Error: {e.message}", file=sys.stderr)
        if e.file_path:
            print(f"   File: {e.file_path}", file=sys.stderr)
        if e.operation:
            print(f"   Operation: {e.operation}", file=sys.stderr)
        sys.exit(1)
    except DirectorySelectionError as e:
        print(f"❌ Directory Selection Error: {e.message}", file=sys.stderr)
        if e.directory_path:
            print(f"   Path: {e.directory_path}", file=sys.stderr)
        sys.exit(1)
    except ModelConfigError as e:
        print(f"❌ Model Configuration Error: {e.message}", file=sys.stderr)
        if e.config_file:
            print(f"   Config file: {e.config_file}", file=sys.stderr)
        sys.exit(1)
    except ValidationError as e:
        print(f"❌ Validation Error: {e.message}", file=sys.stderr)
        if e.field_name:
            print(f"   Field: {e.field_name}", file=sys.stderr)
        if e.invalid_value:
            print(f"   Invalid value: {e.invalid_value}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"❌ Unexpected error: {e}", file=sys.stderr)
        logging.getLogger().critical("Unexpected crash", exc_info=True)
        sys.exit(1)
    finally:
        await _cleanup(agent, enhanced_logger)


def _parse_ui_flags() -> Tuple[bool, bool]:
    """Parse UI-related command line flags."""
    return "--rich" in sys.argv, "--tui" in sys.argv


def _select_ui_mode(use_rich: bool, use_tui: bool) -> UI:
    """Instantiate the appropriate UI class."""
    if use_tui:
        # For TUI, we'll create a placeholder UI that will be replaced
        # when the Textual app initializes
        return PlainUI()
    if use_rich:
        return RichUI()
    return PlainUI()


async def _configure_model(ui: UI, use_tui: bool, use_rich: bool) -> tuple[str, str]:
    current_provider = "ollama" 
    if not use_tui:
        # Improved clarity on the provider prompt
        await ui.print_info(f"Default provider: {current_provider}")
        provider_choice = await ui.prompt_user(
            f"Select provider (press Enter to use {current_provider}): "
        )
        if provider_choice.strip().lower() in ["ollama", "openrouter"]:
            current_provider = provider_choice.strip().lower()
            await ui.print_info(f"Provider set to: {current_provider}")
        elif provider_choice.strip():
            await ui.print_warning(
                f"Unknown provider '{provider_choice}'. Using default: {current_provider}"
            )

    # Validate OpenRouter API key if selected
    if current_provider == "openrouter" and not settings.environment.openrouter_api_key:
        await ui.print_warning(
            "OpenRouter API key not configured. Set OPENROUTER_API_KEY environment variable."
        )
        await ui.print_info("Falling back to ollama provider.")
        current_provider = "ollama"

    current_model = settings.model.default_model

    if use_tui:
        return current_model, current_provider

    if use_rich:
        from rich.panel import Panel  # pylint: disable=import-outside-toplevel

        from ui.styles import console  # pylint: disable=import-outside-toplevel

        console.print()
        console.print(
            Panel(
                f"Target Model: [bold holy.gold]{current_model}[/]",
                title="[dim]System Configuration[/]",
                border_style="dim white",
                padding=(1, 2),
            )
        )

    # UPDATED: Prompt includes the model name
    choice = await ui.prompt_user(f"Initialize with model '{current_model}'? (Y/n)")
    if choice.strip().lower() in ["n", "no"]:
        return await _select_new_model(ui, current_model, current_provider)

    return current_model, current_provider


async def _select_new_model(ui: UI, current_model: str, current_provider: str) -> tuple[str, str]:
    """Prompt user to select a different model from the current provider."""
    # FIX: Pass the current_provider to ensure we see the right models
    model_manager = RuntimeModelManager(provider=current_provider) 
    available_models = model_manager.get_available_models()
    models = list(available_models.values()) if available_models else []

    if not models:
        await ui.print_warning("No models detected. Continuing with default.")
        return current_model, current_provider

    # UI will now show provider info as well
    await ui.display_model_list(models, current_model) 
    choice = await ui.prompt_user("Enter model name or number to select")

    if not choice:
        return current_model, current_provider

    # Logic to handle both name and numeric input
    selected_name = None
    model_names = [getattr(m, "name", m.get("name") if isinstance(m, dict) else str(m)) for m in models]

    if choice.isdigit():
        idx = int(choice) - 1
        if 0 <= idx < len(model_names):
            selected_name = model_names[idx]
    elif choice in model_names:
        selected_name = choice

    if selected_name:
        settings.model.update_model(selected_name)
        await ui.print_info(f"✓ Target updated to: {selected_name}")
        return selected_name, current_provider

    await ui.print_warning(f"Model '{choice}' not found. Using default.")
    return current_model, current_provider


#async def _run_tui(agent: ProtocolAgent):
    """Launch the Textual User Interface."""
    # Import here to avoid circular imports
    from ui.textual.app import ProtocolMonkApp

    # Create and run the Textual app
    app = ProtocolMonkApp(agent)

    # Run the app with asyncio.run() to properly handle the event loop
    # We need to use asyncio.run() because Textual's run() method
    # creates its own event loop
    try:
        await app.run_async()
    except Exception as e:
        print(f"Error running TUI: {e}", file=sys.stderr)
        raise


async def _run_cli(agent: ProtocolAgent, use_rich: bool):
    """Run the standard CLI interaction loop."""
    validation_errors = settings.validate()
    if validation_errors:
        await agent.ui.print_warning("Configuration validation failed:")
        for err in validation_errors:
            await agent.ui.print_warning(f"  - {err}")

    await display_startup_animation(agent.ui)
    await agent.ui.display_startup_banner(MORPHEUS_GREETING)

    dispatcher = CommandDispatcher(agent)

    if use_rich:
        await _rich_input_loop(agent, dispatcher)
    else:
        await _plain_input_loop(agent, dispatcher)


async def _rich_input_loop(agent: ProtocolAgent, dispatcher: CommandDispatcher):
    """Input loop using prompt_toolkit."""
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


async def _plain_input_loop(agent: ProtocolAgent, dispatcher: CommandDispatcher):
    """Input loop using standard input."""
    while True:
        try:
            # UPDATED: Prompt string is simpler, UI handles the prompt display
            user_input = await agent.ui.prompt_user("Next command")
            if not await process_user_input(agent, dispatcher, user_input):
                break
        except (EOFError, KeyboardInterrupt):
            print("\nReceived interrupt signal. Exiting...")
            break


async def _cleanup(
    agent: Optional[ProtocolAgent], enhanced_logger: Optional[EnhancedLogger]
):
    """Ensure resources are closed properly with enhanced exception handling."""
    logger = logging.getLogger(__name__)

    # Close enhanced logger
    if enhanced_logger:
        try:
            enhanced_logger.close()
        except (OSError, IOError) as e:
            logger.warning(f"Failed to close enhanced logger: {e}")
        except Exception as e:
            logger.error(
                f"Unexpected error closing enhanced logger: {e}", exc_info=True
            )

    # Close debug log
    try:
        close_debug_log()
    except (OSError, IOError) as e:
        logger.warning(f"Failed to close debug log: {e}")
    except Exception as e:
        logger.error(f"Unexpected error closing debug log: {e}", exc_info=True)

    # Close agent model client
    if agent:
        try:
            await agent.model_client.close()
        except (OSError, IOError) as e:
            logger.warning(f"Failed to close agent model client: {e}")
        except Exception as e:
            logger.error(
                f"Unexpected error closing agent model client: {e}", exc_info=True
            )

    # Close UI (with cancellation protection)
    if agent and agent.ui:
        try:
            await agent.ui.close()
        except asyncio.CancelledError:
            logger.warning("UI cleanup cancelled due to interrupt")
            # Still try to do basic cleanup even if cancelled
            try:
                # For RichUI, try to stop thinking and streaming at minimum
                if hasattr(agent.ui, "_stop_thinking"):
                    agent.ui._stop_thinking()
                if hasattr(agent.ui, "_streaming_active") and hasattr(
                    agent.ui, "_end_streaming"
                ):
                    if agent.ui._streaming_active:
                        await agent.ui._end_streaming()
            except Exception:
                pass  # Best effort only
            raise  # Re-raise the cancellation
        except Exception as e:
            logger.error(f"Error closing UI: {e}", exc_info=True)

    # Clean up context snapshots
    try:
        import shutil

        # Clean up main context snapshots directory
        context_snapshots_dir = Path("context_snapshots")
        if context_snapshots_dir.exists():
            shutil.rmtree(context_snapshots_dir)
            logger.info("Cleaned up context snapshots directory")

        # Clean up workspace context snapshots directory
        workspace_context_dir = Path("workspace/context_snapshots")
        if workspace_context_dir.exists():
            shutil.rmtree(workspace_context_dir)
            logger.info("Cleaned up workspace context snapshots directory")

    except (OSError, IOError) as e:
        logger.warning(f"Failed to clean up context snapshots: {e}")
    except Exception as e:
        logger.error(
            f"Unexpected error cleaning up context snapshots: {e}", exc_info=True
        )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        # Handle KeyboardInterrupt gracefully with proper cleanup
        print(
            "\n\n[Protocol Monk] Received interrupt signal. Performing graceful shutdown..."
        )
        sys.exit(0)
    except Exception as e:
        # Handle any other unexpected exceptions
        print(f"\n[Protocol Monk] Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)

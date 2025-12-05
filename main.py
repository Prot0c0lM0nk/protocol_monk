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

from exceptions import ConfigurationError
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
from ui.textual.app import MonkCodeTUI
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
        session = initialize_session()
        use_rich, use_tui = _parse_ui_flags()
        ui = _select_ui_mode(use_rich, use_tui)

        # 2. Tool Registry
        tool_registry = ToolRegistry(
            working_dir=session.working_dir,
            preferred_env=session.preferred_env,
            venv_path=session.venv_path,
        )

        # 3. Model Selection (Interactive)
        selected_model = await _configure_model(ui, use_tui, use_rich)

        # 4. Agent Setup
        agent = ProtocolAgent(
            working_dir=session.working_dir,
            model_name=selected_model,
            tool_registry=tool_registry,
            ui=ui,
        )

        enhanced_logger = EnhancedLogger()
        await agent.async_initialize()

        # 5. Run Interface
        if use_tui:
            await _run_tui(agent)
        else:
            await _run_cli(agent, use_rich)

    except ConfigurationError as e:
        print(f"❌ Config Error: {e.message}", file=sys.stderr)
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
        return PlainUI()  # TUI creates its own UI later, placeholder
    if use_rich:
        return RichUI()
    return PlainUI()


async def _configure_model(ui: UI, use_tui: bool, use_rich: bool) -> str:
    """Handle the interactive model selection at startup."""
    current_model = settings.model.default_model

    if use_tui:
        return current_model

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

    choice = await ui.prompt_user("Initialize with this model? (Y/n)")
    if choice.strip().lower() in ["n", "no"]:
        return await _select_new_model(ui, current_model)

    return current_model


async def _select_new_model(ui: UI, current_model: str) -> str:
    """Prompt user to select a different model."""
    model_manager = RuntimeModelManager()
    available_models = model_manager.get_available_models()
    models = list(available_models.values()) if available_models else []

    if not models:
        await ui.print_warning(
            "No models detected (Scanner empty). Continuing with default."
        )
        return current_model

    await ui.display_model_list(models, current_model)
    new_model_name = await ui.prompt_user("Enter model name to select:")

    if not new_model_name:
        return current_model

    valid_names = [
        getattr(m, "name", m.get("name") if isinstance(m, dict) else str(m))
        for m in models
    ]

    if new_model_name in valid_names:
        settings.model.update_model(new_model_name)
        await ui.print_info(f"✓ Target updated to: {new_model_name}")
        return new_model_name

    await ui.print_warning(f"Model '{new_model_name}' not found. Using default.")
    return current_model


async def _run_tui(agent: ProtocolAgent):
    """Launch the Textual User Interface."""
    app = MonkCodeTUI(agent)
    await app.run_async()


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
            user_input = await agent.ui.prompt_user("Next command")
            if not await process_user_input(agent, dispatcher, user_input):
                break
        except (EOFError, KeyboardInterrupt):
            print("\nReceived interrupt signal. Exiting...")
            break


async def _cleanup(
    agent: Optional[ProtocolAgent], enhanced_logger: Optional[EnhancedLogger]
):
    """Ensure resources are closed properly."""
    try:
        if enhanced_logger:
            enhanced_logger.close()  # Fixed method name
    except Exception:  # pylint: disable=broad-exception-caught
        pass

    try:
        close_debug_log()
    except Exception:  # pylint: disable=broad-exception-caught
        pass

    if agent:
        try:
            await agent.model_client.close()
        except Exception:  # pylint: disable=broad-exception-caught
            pass


if __name__ == "__main__":
    asyncio.run(main())

#!/usr/bin/env python3
"""
Application Starter for Protocol Monk
====================================

Ultra-lightweight starter that:
1. Bootstraps minimal configuration
2. Selects UI mode (--rich flag)
3. Creates the application instance
4. Starts the event loop
5. Handles graceful shutdown

This should be the ONLY thing main.py does.
"""

import asyncio
import logging
import signal
import sys
from pathlib import Path

from config.bootstrap import bootstrap_application
from config.static import settings
from exceptions.config import BootstrapError
from utils.debug_logger import _logger, close_debug_log


def setup_logging():
    """Setup minimal logging for startup."""
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


class Application:
    """Main application container."""

    def __init__(self):
        self.working_dir = None
        self.ui_mode = None
        self.agent = None
        self.ui_task = None
        self.running = False

    async def start(self):
        """Start the application."""
        try:
            # Bootstrap minimal configuration and UI mode
            self.working_dir, self.ui_mode = bootstrap_application()

            # Setup logging
            setup_logging()

            # Create the appropriate UI instance based on mode
            if self.ui_mode == "rich":
                from ui.rich import create_rich_ui
                ui_instance = create_rich_ui()
                print(f"[Protocol Monk] Starting with Rich UI...")
            else:
                from ui.plain import create_plain_ui
                ui_instance = create_plain_ui()
                print(f"[Protocol Monk] Starting with Plain UI...")

            # Create and start the agent
            from agent.monk import ProtocolAgent
            from tools.registry import ToolRegistry

            tool_registry = ToolRegistry(
                working_dir=self.working_dir,
                preferred_env=None,  # Will be set by agent if needed
                venv_path=None,  # Will be set by agent if needed
            )

            self.agent = ProtocolAgent(
                working_dir=self.working_dir,
                model_name=settings.model.default_model,
                provider=(
                    settings.api.provider_chain[0]
                    if settings.api.provider_chain
                    else "ollama"
                ),
                tool_registry=tool_registry,
                event_bus=None,  # Agent will create its own event bus
                ui=ui_instance,
            )

            # Initialize agent asynchronously
            await self.agent.async_initialize()

            # Start UI event loop in background
            # This handles tool confirmations and user input coordination
            self.ui_task = asyncio.create_task(ui_instance.run_async())

            # Start the main loop
            self.running = True
            await self.agent.run()

        except BootstrapError as e:
            print(f"❌ Bootstrap Error: {e}", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f"❌ Application Error: {e}", file=sys.stderr)
            logging.getLogger().critical("Application crash", exc_info=True)
            sys.exit(1)

    async def stop(self):
        """Stop the application gracefully."""
        self.running = False

        # Cancel UI task if running
        if self.ui_task and not self.ui_task.done():
            self.ui_task.cancel()
            try:
                await self.ui_task
            except asyncio.CancelledError:
                pass

        if self.agent:
            try:
                await self.agent.shutdown()
            except Exception as e:
                logging.getLogger(__name__).error(f"Error stopping agent: {e}")

        # Close debug log
        try:
            close_debug_log()
        except Exception as e:
            logging.getLogger(__name__).error(f"Error closing debug log: {e}")


def signal_handler(app, signum, frame):
    """Handle shutdown signals."""
    print(f"\n[Protocol Monk] Received signal {signum}. Shutting down gracefully...")
    asyncio.create_task(app.stop())


async def main():
    """Main entry point."""
    app = Application()

    # Handle SIGTERM (Kill signal) gracefully
    signal.signal(signal.SIGTERM, lambda s, f: asyncio.create_task(app.stop()))

    # Start the application
    await app.start()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[Protocol Monk] Interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n[Protocol Monk] Fatal error: {e}", file=sys.stderr)
        sys.exit(1)

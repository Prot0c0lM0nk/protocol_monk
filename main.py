#!/usr/bin/env python3
"""
Application Starter for Protocol Monk
====================================
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
        self.ui_task = None  # For Plain/Rich (Background UI)
        self.agent_task = None  # For Textual (Background Agent)
        self.tui_app = None  # For Textual App instance
        self.running = False

    async def start(self):
        """Start the application."""
        try:
            # 1. Bootstrap Configuration
            self.working_dir, self.ui_mode = bootstrap_application()
            setup_logging()

            # 2. UI Factory Logic
            ui_instance = None

            if self.ui_mode == "textual":
                print(f"[Protocol Monk] Initializing Textual TUI...")
                # Import the Textual UI
                from ui.textual.app import TextualUI

                # Instantiate TextualUI (combines App and UI)
                self.tui_app = TextualUI()
                ui_instance = self.tui_app

            elif self.ui_mode == "rich":
                # Note: We removed the raw print here so the banner is cleaner
                try:
                    from ui.rich import RichUI

                    ui_instance = RichUI()
                except ImportError:
                    # Fallback to factory if you kept the old structure
                    from ui.rich import create_rich_ui

                    ui_instance = create_rich_ui()

                # === [THE TRIGGER] ===
                # This activates your new renderer logic
                await ui_instance.display_startup_banner("Protocol Monk Online")
                # =====================

            else:
                print(f"[Protocol Monk] Starting with Plain UI...")
                from ui.plain.interface import PlainUI

                ui_instance = PlainUI()

            # 3. Agent Instantiation
            from agent.monk import ProtocolAgent
            from tools.registry import ToolRegistry

            tool_registry = ToolRegistry(
                working_dir=self.working_dir,
                preferred_env=None,
                venv_path=None,
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
                event_bus=None,
                ui=ui_instance,
            )

            # 4. Connect agent to TextualUI
            if self.ui_mode == "textual":
                self.tui_app.set_agent(self.agent)

            # 5. Async Initialization
            await self.agent.async_initialize()

            # 6. EXECUTION BRANCH (The Loop Inversion)
            self.running = True

            if self.ui_mode == "textual":
                # === TEXTUAL MODE ===
                # The App owns the main loop. The Agent runs in the background.

                # A. Start Agent in Background
                self.agent_task = asyncio.create_task(self.agent.run())

                # B. Run App in Foreground (BLOCKING)
                await self.tui_app.run_async()

                # C. Cleanup when App exits
                if not self.agent_task.done():
                    self.agent_task.cancel()

            else:
                # === CLI/RICH MODE ===
                # The Agent owns the main loop. The UI updates in background/inline.

                if hasattr(ui_instance, "run_async"):
                    self.ui_task = asyncio.create_task(ui_instance.run_async())

                # Run Agent in Foreground (BLOCKING)
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

        # Stop Textual App if running
        if self.tui_app:
            await self.tui_app.exit()

        # Stop Background Agent (Textual Mode)
        if self.agent_task and not self.agent_task.done():
            self.agent_task.cancel()
            try:
                await self.agent_task
            except asyncio.CancelledError:
                pass

        # Stop Background UI (CLI Mode)
        if self.ui_task and not self.ui_task.done():
            self.ui_task.cancel()
            try:
                await self.ui_task
            except asyncio.CancelledError:
                pass

        # Shutdown Agent
        if self.agent:
            try:
                await self.agent.shutdown()
            except Exception as e:
                logging.getLogger(__name__).error(f"Error stopping agent: {e}")

        try:
            close_debug_log()
        except Exception:
            pass


def signal_handler(app, signum, frame):
    """Handle shutdown signals."""
    asyncio.create_task(app.stop())


async def main():
    """Main entry point."""
    app = Application()
    signal.signal(signal.SIGTERM, lambda s, f: asyncio.create_task(app.stop()))
    await app.start()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)
    except Exception as e:
        print(f"Fatal: {e}", file=sys.stderr)
        sys.exit(1)

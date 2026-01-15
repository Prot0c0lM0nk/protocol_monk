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
        self.ui_task = None 
        self.agent_task = None
        self.tui_app = None 
        self.running = False

    async def start(self):
        """Start the application."""
        try:
            # 1. Bootstrap Configuration
            self.working_dir, self.ui_mode = bootstrap_application()
            setup_logging()

            # 2. Textual Mode (Worker Architecture)
            if self.ui_mode == "textual":
                print(f"[Protocol Monk] Initializing Textual TUI...")
                from ui.textual.app import ProtocolMonkApp
                from ui.textual.interface import TextualUI
                from agent.monk import ProtocolAgent
                from tools.registry import ToolRegistry

                self.tui_app = ProtocolMonkApp()
                ui_bridge = TextualUI(self.tui_app)
                
                tool_registry = ToolRegistry(
                    working_dir=self.working_dir,
                    preferred_env=None,
                    venv_path=None,
                )

                self.agent = ProtocolAgent(
                    working_dir=self.working_dir,
                    model_name=settings.model.default_model,
                    provider=(settings.api.provider_chain[0] if settings.api.provider_chain else "ollama"),
                    tool_registry=tool_registry,
                    event_bus=None,
                    ui=ui_bridge 
                )
                
                await self.agent.async_initialize()

                # Connect
                self.tui_app.textual_ui = ui_bridge
                self.tui_app.agent = self.agent 

                # BLOCKING RUN for Textual
                self.running = True
                await self.tui_app.run_async()

            # 3. Rich Mode (Legacy Loop)
            elif self.ui_mode == "rich":
                try:
                    from ui.rich import RichUI
                    ui_instance = RichUI()
                except ImportError:
                    from ui.rich import create_rich_ui
                    ui_instance = create_rich_ui()
                    
                await ui_instance.display_startup_banner("Protocol Monk Online")
                await self._run_legacy_agent(ui_instance)

            # 4. Plain Mode (Legacy Loop)
            else:
                print(f"[Protocol Monk] Starting with Plain UI...")
                from ui.plain.interface import PlainUI
                ui_instance = PlainUI()
                await self._run_legacy_agent(ui_instance)

        except BootstrapError as e:
            print(f"❌ Bootstrap Error: {e}", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f"❌ Application Error: {e}", file=sys.stderr)
            logging.getLogger().critical("Application crash", exc_info=True)
            sys.exit(1)

    async def _run_legacy_agent(self, ui_instance):
        """Helper to run the agent in blocking mode for CLI/Rich."""
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
            provider="ollama",
            tool_registry=tool_registry,
            event_bus=None,
            ui=ui_instance,
        )

        await self.agent.async_initialize()
        self.running = True
        
        # Start UI background task if needed
        if hasattr(ui_instance, "run_async"):
            self.ui_task = asyncio.create_task(ui_instance.run_async())

        # === THE FIX: AWAIT HERE ===
        # This keeps the program alive for CLI/Rich
        await self.agent.run()

    async def stop(self):
        """Stop the application gracefully."""
        self.running = False
        if self.tui_app:
            await self.tui_app.exit()
        if self.agent_task and not self.agent_task.done():
            self.agent_task.cancel()
        if self.ui_task and not self.ui_task.done():
            self.ui_task.cancel()
        if self.agent:
            try:
                await self.agent.shutdown()
            except Exception:
                pass
        try:
            close_debug_log()
        except Exception:
            pass


def signal_handler(app, signum, frame):
    asyncio.create_task(app.stop())


async def main():
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
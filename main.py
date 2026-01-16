#!/usr/bin/env python3
"""
Application Starter for Protocol Monk
====================================
Wires together the Event Bus, Agent Service, and UI.
"""

import asyncio
import logging
import signal
import sys
from pathlib import Path

# New Architecture Imports
from agent.service import AgentService
from agent.events import EventBus, AgentEvents
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
    """
    Main application container.
    Responsible for dependency injection and lifecycle management.
    """

    def __init__(self):
        self.working_dir = None
        self.ui_mode = None
        self.event_bus = None
        self.agent_service = None
        self.ui = None
        self.tui_app = None
        self.running = False

    async def start(self):
        """Start the application."""
        try:
            # 1. Bootstrap Configuration
            self.working_dir, self.ui_mode = bootstrap_application()
            setup_logging()

            # 2. Initialize Infrastructure (The Spine)
            self.event_bus = EventBus()
            
            # 3. Initialize Agent Service (The Brain)
            # It sits in the background and waits for events.
            from tools.registry import ToolRegistry
            tool_registry = ToolRegistry(
                working_dir=self.working_dir,
                preferred_env=None,
                venv_path=None,
            )

            print(f"[Protocol Monk] Initializing Agent Service...")
            self.agent_service = AgentService(
                working_dir=self.working_dir,
                model_name=settings.model.default_model,
                provider=(settings.api.provider_chain[0] if settings.api.provider_chain else "ollama"),
                tool_registry=tool_registry,
                event_bus=self.event_bus,
            )
            
            await self.agent_service.async_initialize()

            # 4. Initialize UI (The Driver) based on mode
            if self.ui_mode == "textual":
                await self._start_textual_ui()
            elif self.ui_mode == "rich":
                await self._start_rich_ui()
            else:
                await self._start_plain_ui()

        except BootstrapError as e:
            print(f"❌ Bootstrap Error: {e}", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f"❌ Application Error: {e}", file=sys.stderr)
            logging.getLogger().critical("Application crash", exc_info=True)
            sys.exit(1)

    async def _start_plain_ui(self):
        """Start the Plain CLI."""
        print(f"[Protocol Monk] Starting Plain UI...")
        from ui.plain.interface import PlainUI

        self.ui = PlainUI(event_bus=self.event_bus)
        
        # === ARCHITECTURAL FIX: Emit pure data packet ===
        await self.event_bus.emit(
            AgentEvents.APP_STARTED.value,
            {
                "working_dir": str(self.working_dir),
                "model": self.agent_service.current_model,
                "provider": self.agent_service.current_provider,
                "version": "1.0.0" # Example metadata
            }
        )
        # ===============================================
        
        self.running = True
        await self.ui.run_loop()

    async def _start_rich_ui(self):
        """Start the Rich UI in blocking loop mode."""
        print(f"[Protocol Monk] Starting Rich UI...")
        try:
            from ui.rich import RichUI
            self.ui = RichUI(event_bus=self.event_bus)
        except ImportError:
            # Fallback if RichUI signature hasn't been updated yet
            from ui.rich import create_rich_ui
            self.ui = create_rich_ui()
            if hasattr(self.ui, 'event_bus'):
                self.ui.event_bus = self.event_bus

        await self.ui.display_startup_banner("Protocol Monk Online")
        
        self.running = True
        # Rich UI must also implement run_loop or similar
        if hasattr(self.ui, 'run_loop'):
            await self.ui.run_loop()
        else:
            # Fallback for partial migration
            print("⚠️ Rich UI run_loop not implemented. Exiting.")

    async def _start_textual_ui(self):
        """Start the Textual TUI."""
        print(f"[Protocol Monk] Initializing Textual TUI...")
        from ui.textual.app import ProtocolMonkApp
        from ui.textual.interface import TextualUI

        self.tui_app = ProtocolMonkApp()
        
        # Wire up the bridge
        # Note: TextualUI likely needs updates to fully utilize AgentService events
        # but passing the service instance maintains compatibility for now.
        ui_bridge = TextualUI(self.tui_app)
        self.tui_app.textual_ui = ui_bridge
        self.tui_app.agent = self.agent_service  # Service replaces Agent

        self.running = True
        await self.tui_app.run_async()

    async def stop(self):
        """Stop the application gracefully."""
        self.running = False
        
        # Stop UI
        if self.tui_app:
            await self.tui_app.exit()
            
        # Stop Service
        if self.agent_service:
            try:
                await self.agent_service.shutdown()
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
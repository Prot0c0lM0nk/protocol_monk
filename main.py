import asyncio
import logging
import os
from pathlib import Path

# 1. Import Config
from protocol_monk.config.settings import load_settings

# 2. Import Protocol Layer
from protocol_monk.protocol.bus import EventBus
from protocol_monk.protocol.events import EventTypes

# 3. Import Context & Tools
from protocol_monk.agent.context.store import ContextStore
from protocol_monk.agent.context.file_tracker import FileTracker
from protocol_monk.agent.context.coordinator import ContextCoordinator
from protocol_monk.tools.registry import ToolRegistry
from protocol_monk.tools.defaults import register_default_tools

# 4. Import Agent Layer
from protocol_monk.agent.core.service import AgentService

# 5. Import Utils & Providers
from protocol_monk.utils.scratch import ScratchManager
from protocol_monk.utils.logger import EventLogger
from protocol_monk.utils.session_transcript import SessionTranscriptSink
from protocol_monk.providers.ollama import OllamaProvider

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("Bootstrap")


async def main():
    """Main entry point for Protocol Monk."""
    try:
        logger.info("Phase 1: Loading Configuration...")
        app_root = Path(os.getcwd()) / "protocol_monk"
        settings = load_settings(app_root)

        root_level = getattr(logging, settings.log_level.upper(), logging.INFO)
        logging.getLogger().setLevel(root_level)

        # Silence noisy third-party chatter during interactive sessions.
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)
        logging.getLogger("ollama").setLevel(logging.WARNING)
        if root_level > logging.DEBUG:
            logging.getLogger("ModelDiscovery").setLevel(logging.WARNING)
            logging.getLogger("Settings").setLevel(logging.WARNING)
            logging.getLogger("ToolRegistry").setLevel(logging.WARNING)

        # Initialize model discovery (async)
        await settings.initialize()

        # [FIX] Lazy logging
        logger.info("Active model: %s", settings.active_model_name)

        logger.info("Phase 2: Wiring Components...")

        # A. Nervous System
        bus = EventBus()

        # Capture full session event history for replay/debug.
        transcript_sink = SessionTranscriptSink(bus, settings.workspace_root)
        await transcript_sink.start()
        logger.info("Session transcript: %s", transcript_sink.path)

        # Start the EventLogger only in debug runs to avoid duplicate UI output.
        if settings.log_level == "DEBUG":
            event_logger = EventLogger(bus)
            await event_logger.start()

        # B. Tools (The Hands)
        registry = ToolRegistry()
        register_default_tools(registry, settings)

        # [FIX] Lazy logging
        logger.info("Registered Tools: %s", registry.list_tool_names())
        registry.seal()

        # C. The Provider (The Model Interface)
        provider = OllamaProvider(settings)

        # D. Scratch Manager (Cleanup)
        # [FIX] Removed unused 'scratch_manager' variable (using _ instead)
        # unless we pass it to coordinator later.
        with ScratchManager(Path(os.getcwd())) as _:

            # E. Memory Systems (The Brain)
            context_store = ContextStore()
            file_tracker = FileTracker()

            coordinator = ContextCoordinator(
                store=context_store, tracker=file_tracker, settings=settings
            )

            # F. Agent Service (The Orchestrator)
            agent_service = AgentService(
                bus=bus,
                coordinator=coordinator,
                registry=registry,
                provider=provider,
                settings=settings,
            )

            logger.info("Phase 3: Starting Services...")
            await agent_service.start()

            # Start CLI
            from protocol_monk.ui.cli import PromptToolkitCLI
            cli = PromptToolkitCLI(bus, settings)
            await cli.start()

            logger.info("Phase 4: Starting CLI...")
            await cli.run()

            logger.info("Shutdown complete.")

    except Exception as e:
        # [FIX] Lazy logging for exceptions
        logger.critical("Startup Failed: %s", e, exc_info=True)
        exit(1)


if __name__ == "__main__":
    asyncio.run(main())

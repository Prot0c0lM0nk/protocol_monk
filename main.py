import asyncio
import logging
import uuid
import time
import os
from pathlib import Path

# 1. Import Config
from protocol_monk.config.settings import load_settings

# 2. Import Protocol Layer
from protocol_monk.protocol.bus import EventBus
from protocol_monk.protocol.events import EventTypes
from protocol_monk.agent.structs import UserRequest

# 3. Import Context & Tools
from protocol_monk.agent.context.store import ContextStore
from protocol_monk.agent.context.file_tracker import FileTracker
from protocol_monk.agent.context.coordinator import ContextCoordinator
from protocol_monk.tools.registry import ToolRegistry

# Import Tools
from protocol_monk.tools.file_operations.read_file_tool import ReadFileTool
from protocol_monk.tools.file_operations.create_file_tool import CreateFileTool
from protocol_monk.tools.file_operations.append_to_file_tool import AppendToFileTool

# 4. Import Agent Layer
from protocol_monk.agent.core.service import AgentService

# 5. Import Utils & Providers
from protocol_monk.utils.scratch import ScratchManager
from protocol_monk.utils.logger import EventLogger
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

        # Initialize model discovery (async)
        await settings.initialize()

        # [FIX] Lazy logging
        logger.info("Active model: %s", settings.active_model_name)

        logger.info("Phase 2: Wiring Components...")

        # A. Nervous System
        bus = EventBus()

        # Start the EventLogger
        event_logger = EventLogger(bus)
        await event_logger.start()

        # B. Tools (The Hands)
        registry = ToolRegistry()
        registry.register(ReadFileTool(settings))
        registry.register(CreateFileTool(settings))
        registry.register(AppendToFileTool(settings))

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

            logger.info("Phase 4: Simulating User Input...")

            simulated_input = UserRequest(
                text="Append ' - from Protocol Monk' to the file named hello.txt",
                source="simulation",
                request_id=str(uuid.uuid4()),
                timestamp=time.time(),
            )

            await bus.emit(EventTypes.USER_INPUT_SUBMITTED, simulated_input)

            # Keep alive briefly to allow processing
            await asyncio.sleep(15.0)
            logger.info("Simulation Complete. Shutting down.")

    except Exception as e:
        # [FIX] Lazy logging for exceptions
        logger.critical("Startup Failed: %s", e, exc_info=True)
        exit(1)


if __name__ == "__main__":
    asyncio.run(main())

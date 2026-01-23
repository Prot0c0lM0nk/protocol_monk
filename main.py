import asyncio
import logging
import uuid
import time
import os
from pathlib import Path

# 1. Import Exceptions
from protocol_monk.exceptions.config import ConfigError
from protocol_monk.exceptions.base import MonkBaseError

# 2. Import Config
from protocol_monk.config.settings import load_settings

# 3. Import Protocol Layer
from protocol_monk.protocol.bus import EventBus
from protocol_monk.protocol.events import EventTypes
from protocol_monk.agent.structs import UserRequest

# 4. Import Context & Tools
from protocol_monk.agent.context.store import ContextStore
from protocol_monk.agent.context.file_tracker import FileTracker
from protocol_monk.agent.context.coordinator import ContextCoordinator
from protocol_monk.tools.registry import ToolRegistry

# Import Tools
from protocol_monk.tools.file_operations.read_file_tool import ReadFileTool
from protocol_monk.tools.file_operations.create_file_tool import CreateFileTool
from protocol_monk.tools.file_operations.append_to_file_tool import AppendToFileTool

# 5. Import Agent Layer
from protocol_monk.agent.core.service import AgentService

# 6. Import Utils & Providers [NEW]
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
    try:
        logger.info("Phase 1: Loading Configuration...")
        app_root = Path(os.getcwd()) / "protocol_monk"
        settings = load_settings(app_root)

        # Initialize model discovery (async)
        await settings.initialize()

        logger.info(f"Active model: {settings.active_model_name}")

        logger.info("Phase 2: Wiring Components...")

        # A. Nervous System
        bus = EventBus()
        
        # [NEW] Start the EventLogger so we can see what's happening
        event_logger = EventLogger(bus)
        await event_logger.start()

        # B. Tools (The Hands)
        registry = ToolRegistry()
        registry.register(ReadFileTool(settings))
        registry.register(CreateFileTool(settings))
        registry.register(AppendToFileTool(settings))
        logger.info(f"Registered Tools: {registry.list_tool_names()}")
        registry.seal()

        # [NEW] C. The Provider (The Model Interface)
        provider = OllamaProvider(settings)

        # D. Scratch Manager (Cleanup)
        with ScratchManager(Path(os.getcwd())) as scratch_manager:
            
            # E. Memory Systems (The Brain)
            context_store = ContextStore()
            file_tracker = FileTracker()

            coordinator = ContextCoordinator(
                store=context_store, 
                tracker=file_tracker, 
                settings=settings
            )

            # F. Agent Service (The Orchestrator)
            # [FIX] Now injecting 'provider' and 'settings' as required
            agent_service = AgentService(
                bus=bus, 
                coordinator=coordinator, 
                registry=registry,
                provider=provider,
                settings=settings
            )

            logger.info("Phase 3: Starting Services...")
            await agent_service.start()

            logger.info("Phase 4: Simulating User Input...")
            simulated_input = UserRequest(
                text="Create a file named hello.txt with the content 'Hello World'",
                source="simulation",
                request_id=str(uuid.uuid4()),
                timestamp=time.time(),
            )

            await bus.emit(EventTypes.USER_INPUT_SUBMITTED, simulated_input)

            # [FIX] Increased wait time to 15s to give the model time to generate
            # and the tool time to execute.
            await asyncio.sleep(15.0)
            logger.info("Simulation Complete. Shutting down.")

    except Exception as e:
        logger.critical(f"Startup Failed: {e}", exc_info=True)
        exit(1)


if __name__ == "__main__":
    asyncio.run(main())
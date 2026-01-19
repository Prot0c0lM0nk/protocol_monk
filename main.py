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

# FIXED: Import from agent.structs, not protocol.objects
from protocol_monk.agent.structs import UserRequest

# 4. Import Context & Tools
from protocol_monk.agent.context.store import ContextStore
from protocol_monk.agent.context.file_tracker import FileTracker
from protocol_monk.agent.context.coordinator import ContextCoordinator
from protocol_monk.tools.registry import ToolRegistry

# Import Tools to Register
from protocol_monk.tools.file_operations.read_file_tool import ReadFileTool
from protocol_monk.tools.file_operations.create_file_tool import CreateFileTool
from protocol_monk.tools.file_operations.append_to_file_tool import AppendToFileTool

# (Import other tools as needed)

# 5. Import Agent Layer
from protocol_monk.agent.core.service import AgentService

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

        logger.info("Phase 2: Wiring Components...")

        # A. Nervous System
        bus = EventBus()

        # B. Tools (The Hands)
        # Initialize Registry and Load Tools
        registry = ToolRegistry()

        # Register File Ops (Injecting settings so they know the workspace)
        registry.register(ReadFileTool(settings))
        registry.register(CreateFileTool(settings))
        registry.register(AppendToFileTool(settings))

        logger.info(f"Registered Tools: {registry.list_tool_names()}")

        # C. Memory Systems (The Brain)
        context_store = ContextStore()
        file_tracker = FileTracker()

        # D. Coordinator
        coordinator = ContextCoordinator(
            store=context_store, tracker=file_tracker, settings=settings
        )

        # E. Agent Service (The Orchestrator)
        # NOW: We inject the registry so the Service can find tools
        agent_service = AgentService(
            bus=bus, coordinator=coordinator, registry=registry
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

        # Keep alive briefly to allow processing
        await asyncio.sleep(2.0)
        logger.info("Simulation Complete. Shutting down.")

    except Exception as e:
        logger.critical(f"Startup Failed: {e}", exc_info=True)
        exit(1)


if __name__ == "__main__":
    asyncio.run(main())

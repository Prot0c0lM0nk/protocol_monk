import asyncio
import logging
import uuid
import time
import os
from pathlib import Path

# 1. Import Exceptions for safe startup
from protocol_monk.exceptions.config import ConfigError
from protocol_monk.exceptions.base import MonkBaseError

# 2. Import Config
from protocol_monk.config.settings import load_settings

# 3. Import Protocol Layer
from protocol_monk.protocol.bus import EventBus
from protocol_monk.protocol.events import EventTypes
from protocol_monk.protocol.objects import UserRequest

# 4. Import Context Layer
from protocol_monk.agent.context.store import ContextStore
from protocol_monk.agent.context.file_tracker import FileTracker
from protocol_monk.agent.context.coordinator import ContextCoordinator

# 5. Import Agent Layer
from protocol_monk.agent.core.service import AgentService

# Configure Logging (Ephemeral Console Log)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("Bootstrap")


async def main():
    try:
        # --- PHASE 1: Configuration ---
        logger.info("Phase 1: Loading Configuration...")

        # We assume we are running from the parent directory of protocol_monk
        # or protocol_monk is the root. Let's assume current working dir.
        app_root = Path(os.getcwd()) / "protocol_monk"

        # Set required env vars for this simulation if not set
        # In production, these come from the environment
        if not os.getenv("MONK_WORKSPACE"):
            os.environ["MONK_WORKSPACE"] = str(Path.cwd())
        if not os.getenv("MONK_SYSTEM_PROMPT_PATH"):
            os.environ["MONK_SYSTEM_PROMPT_PATH"] = "system_prompt.txt"
        if not os.getenv("MONK_LOG_LEVEL"):
            os.environ["MONK_LOG_LEVEL"] = "INFO"

        settings = load_settings(app_root)
        logger.info(f"Config Loaded. Log Level: {settings.log_level}")

        # --- PHASE 2: Dependency Injection (Wiring) ---
        logger.info("Phase 2: Wiring Components...")

        # A. Nervous System
        bus = EventBus()

        # B. Memory Systems (The "Brain")
        context_store = ContextStore()
        file_tracker = FileTracker()

        # C. Coordinator (The Logic)
        # We inject store and tracker into the coordinator
        coordinator = ContextCoordinator(
            store=context_store, tracker=file_tracker, settings=settings
        )

        # D. Agent Service (The Orchestrator)
        # We inject the Bus and the Coordinator
        agent_service = AgentService(bus=bus, coordinator=coordinator)

        # --- PHASE 3: Startup ---
        logger.info("Phase 3: Starting Services...")

        # Start the Agent (Listeners)
        await agent_service.start()

        # --- PHASE 4: Simulation (Proof of Life) ---
        logger.info("Phase 4: Simulating User Input...")

        # Create a valid event payload
        simulated_input = UserRequest(
            text="Hello, Monk! This is a test of the event system.",
            source="simulation",
            request_id=str(uuid.uuid4()),
            timestamp=time.time(),
        )

        # Emit the event!
        # The AgentService is listening for this specific event type.
        await bus.emit(EventTypes.USER_INPUT_SUBMITTED, simulated_input)

        # Give the async loop a moment to process the event
        await asyncio.sleep(0.5)

        logger.info("Simulation Complete. Shutting down.")

    except ConfigError as e:
        logger.critical(f"Startup Failed (Configuration): {e}")
        exit(1)
    except MonkBaseError as e:
        logger.critical(f"Startup Failed (Core Logic): {e}")
        exit(1)
    except Exception as e:
        logger.critical(f"Startup Failed (Unexpected): {e}", exc_info=True)
        exit(1)


if __name__ == "__main__":
    asyncio.run(main())

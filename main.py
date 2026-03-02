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
from protocol_monk.providers.factory import create_provider

# 6. Import UI Components
from protocol_monk.ui.rich.boot import BootAnimation, BootPhase

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("Bootstrap")
RICH_UI_NOISY_LOGGERS = (
    "AgentService",
    "ToolExecutor",
    "LogicLoops",
    "EventBus",
    "ContextCoordinator",
    "RichPromptToolkitUI",
)


def _resolve_ui_backend(requested: str) -> tuple[str, str]:
    requested_ui = (requested or "rich").strip().lower() or "rich"
    if requested_ui in {"rich", "cli"}:
        return requested_ui, ""
    if requested_ui == "textual":
        return "rich", "UI backend 'textual' is unsupported. Falling back to Rich."
    return "rich", f"Unknown UI backend '{requested_ui}'. Falling back to Rich."


def _apply_rich_log_suppression(ui_backend: str, root_level: int) -> None:
    """Reduce noisy logger output in Rich mode for non-debug runs."""
    if ui_backend != "rich":
        return
    if root_level <= logging.DEBUG:
        return
    for logger_name in RICH_UI_NOISY_LOGGERS:
        logging.getLogger(logger_name).setLevel(logging.WARNING)


def _validate_context_tracking_tools(registry: ToolRegistry) -> tuple[list[str], list[str]]:
    expected = sorted(
        {ContextCoordinator.FILE_READ_TOOL, *ContextCoordinator.FILE_MUTATION_TOOLS}
    )
    registered = set(registry.list_tool_names())
    missing = sorted(name for name in expected if name not in registered)
    return expected, missing


async def main():
    """Main entry point for Protocol Monk."""
    try:
        # Phase 1: Loading Configuration
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

        # Run Setup Wizard (skip in non-interactive mode)
        skip_wizard = os.getenv("PROTOCOL_MONK_SKIP_WIZARD", "").lower() in ("1", "true", "yes")
        if not skip_wizard:
            from protocol_monk.ui.rich.wizard import SetupWizard

            wizard = SetupWizard()
            try:
                choices = await wizard.run(settings)
                wizard.apply_choices(settings, choices)
            except (EOFError, KeyboardInterrupt):
                pass  # User cancelled, use defaults

        # Determine UI backend
        requested_ui_backend = os.getenv("PROTOCOL_MONK_UI", "rich")
        ui_backend, ui_note = _resolve_ui_backend(requested_ui_backend)
        _apply_rich_log_suppression(ui_backend, root_level)

        boot: BootAnimation | None = None

        # Run boot animation for Rich UI
        if ui_backend == "rich":
            boot = BootAnimation()
            await boot.run_animation(duration_per_art=0.5)

        # Phase 2: Wiring Components

        # A. Nervous System
        bus = EventBus()

        # Capture full session event history for replay/debug.
        transcript_sink = SessionTranscriptSink(
            bus,
            settings.workspace_root,
            max_sessions=settings.trace_max_sessions,
            max_total_bytes=settings.trace_max_total_bytes,
        )
        await transcript_sink.start()

        # Start the EventLogger only in debug runs to avoid duplicate UI output.
        if settings.log_level == "DEBUG":
            event_logger = EventLogger(bus)
            await event_logger.start()

        # B. Tools (The Hands)
        registry = ToolRegistry()
        register_default_tools(registry, settings)
        registered_tools = registry.list_tool_names()

        await bus.emit(
            EventTypes.INFO,
            {
                "message": "Tool registry ready",
                "data": {
                    "tool_count": len(registered_tools),
                    "tools": registered_tools,
                },
            },
        )
        expected_tracking_tools, missing_tracking_tools = _validate_context_tracking_tools(
            registry
        )
        if missing_tracking_tools:
            warning = (
                "Context file-tracking tool map references unregistered tool(s): "
                + ", ".join(missing_tracking_tools)
            )
            logger.warning(warning)
            await bus.emit(
                EventTypes.WARNING,
                {
                    "message": "Context tracking tool map mismatch",
                    "details": warning,
                    "data": {
                        "expected_tracking_tools": expected_tracking_tools,
                        "registered_tools": registered_tools,
                        "missing_tracking_tools": missing_tracking_tools,
                    },
                },
            )
        else:
            await bus.emit(
                EventTypes.INFO,
                {
                    "message": "Context tracking tool map validated",
                    "data": {
                        "expected_tracking_tools": expected_tracking_tools,
                        "registered_tools": registered_tools,
                    },
                },
            )
        registry.seal()

        # C. The Provider (The Model Interface)
        provider = create_provider(settings)
        await bus.emit(
            EventTypes.INFO,
            {
                "message": "Provider configured",
                "data": {
                    "provider": settings.llm_provider,
                    "active_model": settings.active_model_name,
                },
            },
        )

        if ui_note:
            logger.warning(ui_note)
            await bus.emit(
                EventTypes.WARNING,
                {
                    "message": "UI backend override applied",
                    "details": ui_note,
                },
            )
        await bus.emit(
            EventTypes.INFO,
            {
                "message": "Runtime configured",
                "data": {
                    "requested_ui": requested_ui_backend,
                    "resolved_ui": ui_backend,
                    "provider": settings.llm_provider,
                    "active_model": settings.active_model_name,
                    "workspace": str(settings.workspace_root),
                },
            },
        )

        # D. Scratch Manager (Cleanup)
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

            await agent_service.start()

            # Phase 4: Starting UI
            if boot is not None:
                boot.update_phase(BootPhase.UI, "Ready")

            if ui_backend == "cli":
                from protocol_monk.ui.cli import PromptToolkitCLI

                cli = PromptToolkitCLI(bus, settings)
                await cli.start()
                await cli.run()
            else:
                from protocol_monk.ui.rich.app import RichPromptToolkitUI

                rich_ui = RichPromptToolkitUI(bus=bus, settings=settings)
                await rich_ui.start()
                await rich_ui.run()

            return 0

    except Exception as e:
        logger.critical("Startup Failed: %s", e, exc_info=True)
        return 1


def run() -> int:
    """
    Synchronous wrapper with Ctrl-C policy.

    - Normal/handled failures return explicit status codes from main().
    - User interrupt exits cleanly without traceback noise in INFO mode.
    """
    try:
        return asyncio.run(main())
    except KeyboardInterrupt:
        if logging.getLogger().isEnabledFor(logging.DEBUG):
            logger.debug("Interrupted by user. Exiting.", exc_info=True)
        else:
            logger.info("Interrupted by user. Exiting.")
        return 0


if __name__ == "__main__":
    raise SystemExit(run())

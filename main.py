import asyncio
import logging
import os
from pathlib import Path

# 1. Import Config
from protocol_monk.config.settings import load_settings
from protocol_monk.exceptions.config import ConfigError
from protocol_monk.exceptions.base import log_exception

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
from protocol_monk.skill_runtime import SkillRuntime
from protocol_monk.plugins.neuralsym import build_protocol_monk_neuralsym_adapter

# 6. Import UI Components
from protocol_monk.ui.rich.boot import BootAnimation, BootPhase

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("Bootstrap")
APP_ROOT = Path(__file__).resolve().parent
RICH_UI_NOISY_LOGGERS = (
    "AgentService",
    "ToolExecutor",
    "LogicLoops",
    "EventBus",
    "ContextCoordinator",
    "RichPromptToolkitUI",
)


def _env_flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes"}


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


def _log_startup_diagnostics(settings) -> None:
    logger.info(
        (
            "Startup diagnostics: provider=%s active_model=%s workspace=%s "
            "ollama_model_map=%s openrouter_model_map=%s"
        ),
        getattr(settings, "llm_provider", "unknown"),
        getattr(settings, "active_model_name", "unknown"),
        getattr(settings, "workspace_root", getattr(settings, "workspace", "unknown")),
        getattr(settings, "models_json_path", "unknown"),
        getattr(settings, "openrouter_models_json_path", "unknown"),
    )


async def _validate_provider_ready(provider, settings) -> None:
    provider_name = getattr(settings, "llm_provider", "unknown")
    active_model = getattr(settings, "active_model_name", "unknown")
    try:
        is_ready = await provider.validate_connection()
    except Exception as exc:
        raise ConfigError(
            f"Provider '{provider_name}' failed readiness check for model '{active_model}': {exc}"
        ) from exc

    if not is_ready:
        raise ConfigError(
            f"Provider '{provider_name}' is unavailable or not authenticated for model '{active_model}'."
        )


def _validate_context_tracking_tools(registry: ToolRegistry) -> tuple[list[str], list[str]]:
    expected = sorted(
        {ContextCoordinator.FILE_READ_TOOL, *ContextCoordinator.FILE_MUTATION_TOOLS}
    )
    registered = set(registry.list_tool_names())
    missing = sorted(name for name in expected if name not in registered)
    return expected, missing


async def run_session_app(
    settings,
    *,
    skip_wizard: bool = False,
    requested_ui_backend: str = "rich",
) -> int:
    """Run the terminal session against an already-loaded settings object."""
    try:
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

        if not skip_wizard:
            from protocol_monk.ui.rich.wizard import SetupWizard

            wizard = SetupWizard()
            try:
                choices = await wizard.run(settings)
                wizard.apply_choices(settings, choices)
            except (EOFError, KeyboardInterrupt):
                pass  # User cancelled, use defaults

        # Initialize provider/model state only after setup choices are applied.
        await settings.initialize()
        _log_startup_diagnostics(settings)

        provider = create_provider(settings)
        await _validate_provider_ready(provider, settings)

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
        await bus.emit(
            EventTypes.INFO,
            {
                "message": "Provider configured",
                "data": {
                    "provider": settings.llm_provider,
                    "active_model": settings.active_model_name,
                    "connection_validated": True,
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
                    "ollama_model_map": str(settings.models_json_path),
                    "openrouter_model_map": str(settings.openrouter_models_json_path),
                },
            },
        )

        # D. Scratch Manager (Cleanup)
        with ScratchManager(settings.resolved_paths.scratch_root) as _:
            skill_runtime = SkillRuntime(settings.resolved_paths.skills_root)
            neuralsym_adapter = await build_protocol_monk_neuralsym_adapter(settings)

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
                skill_runtime=skill_runtime,
                neuralsym_adapter=neuralsym_adapter,
            )

            try:
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
            finally:
                if neuralsym_adapter is not None:
                    await neuralsym_adapter.stop()

    except Exception as exc:
        log_exception(logger, logging.CRITICAL, "Startup failed", exc)
        return 1


async def main():
    """Main entry point for Protocol Monk."""
    settings = load_settings(APP_ROOT)
    return await run_session_app(
        settings,
        skip_wizard=_env_flag("PROTOCOL_MONK_SKIP_WIZARD"),
        requested_ui_backend=os.getenv("PROTOCOL_MONK_UI", "rich"),
    )


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

import logging
import logging.handlers
import sys
from typing import Dict, Any, List

from protocol_monk.protocol.bus import EventBus
from protocol_monk.protocol.events import EventTypes


class EventLogger:
    """
    The Ephemeral Logger.

    Adheres to 11_LOGGING_STRATEGY.md:
    - No persistent files.
    - Aggregates stream chunks to avoid noise.
    - dual-streams to Stderr (VS Code) and SysLog (Console.app).
    """

    def __init__(self, bus: EventBus):
        self._bus = bus
        self._buffer: List[str] = []  # The "Stream Aggregator" buffer

        # Setup Python Logger
        self._logger = logging.getLogger("ProtocolMonk")
        self._logger.setLevel(logging.DEBUG)
        self._logger.propagate = False  # Don't double-print to root logger

        # 1. Console Handler (Standard Error) - Visible in VS Code
        console = logging.StreamHandler(sys.stderr)
        console.setFormatter(logging.Formatter("COMPONENT: %(message)s"))
        self._logger.addHandler(console)

        # 2. SysLog Handler - Visible in Mac Console.app
        # We try to connect to the standard Mac socket.
        try:
            syslog = logging.handlers.SysLogHandler(address="/var/run/syslog")
            syslog.setFormatter(logging.Formatter("%(name)s: %(message)s"))
            self._logger.addHandler(syslog)
        except Exception:
            # Fallback if SysLog socket isn't available (rare on Mac)
            pass

    async def start(self):
        """Subscribe to the Nervous System."""
        # Operational Events
        await self._bus.subscribe(EventTypes.INFO, self._log_info)
        await self._bus.subscribe(EventTypes.WARNING, self._log_warning)
        await self._bus.subscribe(EventTypes.ERROR, self._log_error)
        await self._bus.subscribe(EventTypes.STATUS_CHANGED, self._log_status)

        # Tool Events
        await self._bus.subscribe(EventTypes.TOOL_EXECUTION_COMPLETE, self._log_tool)

        # The "Stream Aggregator" Pattern
        await self._bus.subscribe(EventTypes.STREAM_CHUNK, self._handle_chunk)
        await self._bus.subscribe(
            EventTypes.RESPONSE_COMPLETE, self._handle_response_end
        )

        # Context Visibility (Brain State)
        await self._bus.subscribe(EventTypes.CONTEXT_OVERFLOW, self._log_context_event)

        # Note: We can also subscribe to 'USER_INPUT_SUBMITTED' to log what user said
        await self._bus.subscribe(EventTypes.USER_INPUT_SUBMITTED, self._log_user_input)

    # --- Handlers ---

    async def _log_info(self, data: Dict[str, Any]):
        msg = data.get("message", str(data))
        self._logger.info(f"ℹ️  {msg}")

    async def _log_warning(self, data: Dict[str, Any]):
        msg = data.get("message", str(data))
        self._logger.warning(f"⚠️  {msg}")

    async def _log_error(self, data: Dict[str, Any]):
        msg = data.get("message", str(data))
        self._logger.error(f"🚨 ERROR: {msg}")

    async def _log_status(self, data: Any):
        # Handle Pydantic model or Dict
        if hasattr(data, "status"):
            status = data.status
            msg = data.message
        else:
            status = data.get("status")
            msg = data.get("message")

        self._logger.info(f"🔄 STATUS: {status} | {msg}")

    async def _log_tool(self, data: Dict[str, Any]):
        tool = data.get("tool_name", "unknown")
        success = data.get("success", False)
        icon = "✅" if success else "❌"
        self._logger.info(f"{icon} TOOL: {tool} finished")

    async def _log_user_input(self, data: Any):
        text = getattr(data, "text", str(data))
        self._logger.info(f"👤 USER: {text}")

    async def _log_context_event(self, data: Any):
        self._logger.info(f"🧠 CONTEXT: {data}")

    # --- The Aggregator Logic ---

    async def _handle_chunk(self, data: Dict[str, Any]):
        """Silent buffer. Doesn't print."""
        chunk = data.get("chunk", "")
        if chunk:
            self._buffer.append(chunk)

    async def _handle_response_end(self, data: Any):
        """Flushes the buffer to the log."""
        full_text = "".join(self._buffer)
        self._logger.info(f"🤖 MODEL: {full_text}")
        self._buffer.clear()

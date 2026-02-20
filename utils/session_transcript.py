"""Session transcript sink for full-fidelity event capture."""

import asyncio
import dataclasses
import json
import time
import uuid
from enum import Enum
from pathlib import Path
from typing import Any, Dict

from protocol_monk.protocol.bus import EventBus
from protocol_monk.protocol.events import EventTypes


class SessionTranscriptSink:
    """Append-only JSONL recorder for all event bus activity."""

    def __init__(self, bus: EventBus, workspace_root: Path):
        self._bus = bus
        self._workspace_root = Path(workspace_root)
        self._session_id = f"{int(time.time())}-{uuid.uuid4().hex[:8]}"
        self._sequence = 0
        self._lock = asyncio.Lock()
        self._path = (
            self._workspace_root
            / ".protocol_monk"
            / "sessions"
            / f"{self._session_id}.jsonl"
        )

    @property
    def path(self) -> Path:
        return self._path

    async def start(self) -> None:
        """Create session file and subscribe to all known event types."""
        self._path.parent.mkdir(parents=True, exist_ok=True)

        await self._append("session_start", {"session_id": self._session_id})

        for event_type in EventTypes:
            await self._bus.subscribe(
                event_type, self._make_event_handler(event_type.value)
            )

    def _make_event_handler(self, event_name: str):
        async def _handler(payload: Any) -> None:
            await self._append(event_name, payload)

        return _handler

    async def _append(self, event_type: str, payload: Any) -> None:
        record = {
            "session_id": self._session_id,
            "sequence": self._sequence,
            "timestamp": time.time(),
            "event_type": event_type,
            "payload": self._serialize(payload),
        }
        self._sequence += 1

        line = json.dumps(record, ensure_ascii=True, separators=(",", ":"))
        async with self._lock:
            with self._path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")

    def _serialize(self, payload: Any) -> Any:
        if payload is None:
            return None
        if isinstance(payload, (str, int, float, bool)):
            return payload
        if isinstance(payload, Enum):
            return payload.value
        if dataclasses.is_dataclass(payload):
            return self._serialize(dataclasses.asdict(payload))
        if isinstance(payload, dict):
            return {str(k): self._serialize(v) for k, v in payload.items()}
        if isinstance(payload, (list, tuple)):
            return [self._serialize(item) for item in payload]
        if isinstance(payload, Path):
            return str(payload)
        if hasattr(payload, "__dict__"):
            return self._serialize(vars(payload))
        return str(payload)

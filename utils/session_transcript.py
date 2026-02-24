"""Session transcript sink for full-fidelity event capture."""

import asyncio
import dataclasses
import json
import logging
import time
import uuid
from enum import Enum
from pathlib import Path
from typing import Any, Dict

from protocol_monk.protocol.bus import EventBus
from protocol_monk.protocol.events import EventTypes

logger = logging.getLogger("SessionTranscript")


class SessionTranscriptSink:
    """Append-only JSONL recorder for all event bus activity."""

    def __init__(
        self,
        bus: EventBus,
        workspace_root: Path,
        max_sessions: int = 200,
        max_total_bytes: int = 250 * 1024 * 1024,
    ):
        self._bus = bus
        self._workspace_root = Path(workspace_root)
        self._session_id = f"{int(time.time())}-{uuid.uuid4().hex[:8]}"
        self._sequence = 0
        self._lock = asyncio.Lock()
        self._schema_version = 2
        self._max_sessions = max(1, int(max_sessions))
        self._max_total_bytes = max(1, int(max_total_bytes))
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
        self._prune_retention()

        await self._append("session_start", {"session_id": self._session_id})
        self._prune_retention()

        for event_type in EventTypes:
            await self._bus.subscribe(
                event_type, self._make_event_handler(event_type.value)
            )

    def _make_event_handler(self, event_name: str):
        async def _handler(payload: Any) -> None:
            await self._append(event_name, payload)

        return _handler

    async def _append(self, event_type: str, payload: Any) -> None:
        serialized_payload = self._serialize(payload)
        record = {
            "schema_version": self._schema_version,
            "session_id": self._session_id,
            "sequence": self._sequence,
            "timestamp": time.time(),
            "event_type": event_type,
            "correlation": self._extract_correlation(serialized_payload),
            "payload": serialized_payload,
        }
        self._sequence += 1

        line = json.dumps(record, ensure_ascii=True, separators=(",", ":"))
        async with self._lock:
            with self._path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")

    def _extract_correlation(self, payload: Any) -> Dict[str, Any]:
        if not isinstance(payload, dict):
            return {}

        keys = (
            "turn_id",
            "pass_id",
            "tool_call_id",
            "round_index",
            "tool_index",
            "sequence",
        )
        correlation: Dict[str, Any] = {
            key: payload[key] for key in keys if key in payload and payload[key] is not None
        }

        request_id = payload.get("request_id")
        if request_id and "turn_id" not in correlation:
            correlation["turn_id"] = request_id

        nested_data = payload.get("data")
        if isinstance(nested_data, dict):
            nested_corr = nested_data.get("correlation")
            if isinstance(nested_corr, dict):
                for key in keys:
                    if key in nested_corr and nested_corr[key] is not None:
                        correlation.setdefault(key, nested_corr[key])

        return correlation

    def _prune_retention(self) -> None:
        session_dir = self._path.parent
        files = sorted(
            session_dir.glob("*.jsonl"),
            key=lambda p: p.stat().st_mtime if p.exists() else 0,
            reverse=True,
        )
        kept = 0
        total_bytes = 0
        for file_path in files:
            try:
                file_size = file_path.stat().st_size
            except OSError:
                continue

            should_keep = kept < self._max_sessions and (
                total_bytes + file_size <= self._max_total_bytes or kept == 0
            )
            if should_keep:
                kept += 1
                total_bytes += file_size
                continue

            try:
                file_path.unlink()
            except OSError as exc:
                logger.warning("Failed to prune session transcript %s: %s", file_path, exc)

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

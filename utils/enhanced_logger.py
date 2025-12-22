#!/usr/bin/env python3
"""
Enhanced Logging System for MonkCode Agent.
Responsibility: Audit Trail & Context Visibility.
"""

from datetime import datetime
from threading import Lock

import json
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from config.static import settings


@dataclass
class LogEntry:
    timestamp: str
    session_id: str
    event_type: str
    content: Any  # Changed to Any to handle Dict/List directly
    metadata: Dict[str, Any]
    conversation_id: Optional[str] = None


class EnhancedLogger:
    """
    Captures the 'Brain State' of the agent.
    Separated from DebugLogger (which captures Application State).
    """

    def __init__(self, log_dir: Path = None):
        # Fallback to current dir if settings fail (safety net)
        try:
            self.log_dir = log_dir or settings.filesystem.working_dir
        except Exception:
            self.log_dir = Path(".")

        self.session_id = f"session_{int(time.time())}"
        self.conversation_counter = 0
        self._lock = Lock()
        self.closed = False

        # Define file paths
        self.detailed_log = self.log_dir / f"detailed_{self.session_id}.jsonl"
        self.context_snapshot_dir = self.log_dir / "context_snapshots"

        # Ensure directories exist
        try:
            self.log_dir.mkdir(parents=True, exist_ok=True)
            self.context_snapshot_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            print(
                f"!! CRITICAL: EnhancedLogger cannot create directories: {e}",
                file=sys.stderr,
            )

    def _get_timestamp(self) -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

    def _write_entry(self, event_type: str, content: Any, metadata: Dict = None):
        """Thread-safe write to JSONL log."""
        if self.closed:
            return

        entry = LogEntry(
            timestamp=self._get_timestamp(),
            session_id=self.session_id,
            event_type=event_type,
            content=content,
            metadata=metadata or {},
            conversation_id=str(self.conversation_counter),
        )

        with self._lock:
            try:
                with open(self.detailed_log, "a", encoding="utf-8") as f:
                    f.write(json.dumps(asdict(entry)) + "\n")
            except Exception as e:
                # Last resort print to stderr so we know we are blind
                print(f"!! EnhancedLogger Write Failed: {e}", file=sys.stderr)

    # --- PUBLIC API ---

    def log_user_input(self, user_input: str):
        with self._lock:
            self.conversation_counter += 1
        self._write_entry("user_input", user_input)
        return str(self.conversation_counter)

    def log_agent_turn(self, response: str, tokens: int, model: str):
        self._write_entry("agent_turn", response, {"model": model, "tokens": tokens})

    def log_tool_execution(
        self, tool_name: str, params: Dict, result: str, success: bool
    ):
        self._write_entry(
            "tool_execution",
            {"tool": tool_name, "params": params, "result": result},
            {"success": success},
        )

    def log_context_snapshot(self, messages: List[Dict]):
        """
        CRITICAL: Dumps the exact context window to a readable file.
        Call this right before sending to the model.
        """
        # Ensure directory exists before writing
        try:
            self.context_snapshot_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            print(f"!! Failed to create context_snapshot_dir: {e}", file=sys.stderr)
            return

        snapshot_file = (
            self.context_snapshot_dir
            / f"ctx_{self.conversation_counter:03d}_{int(time.time())}.txt"
        )

        try:
            with open(snapshot_file, "w", encoding="utf-8") as f:
                f.write(f"=== CONTEXT SNAPSHOT {self.conversation_counter} ===\n")
                f.write(f"Timestamp: {self._get_timestamp()}\n")
                f.write(f"Message Count: {len(messages)}\n\n")

                for idx, msg in enumerate(messages):
                    role = msg.get("role", "unknown").upper()
                    content = msg.get("content", "")

                    f.write(f"--- [{idx}] {role} ---\n")
                    if isinstance(content, str):
                        f.write(content)
                    else:
                        f.write(json.dumps(content, indent=2))
                    f.write("\n\n")

            # Log that we took a snapshot
            self._write_entry("context_snapshot", str(snapshot_file))

        except Exception as e:
            print(f"!! Failed to write context snapshot: {e}", file=sys.stderr)

    def close(self):
        self.closed = True

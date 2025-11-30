"""
Safe persistence layer for the knowledge graph.

Handles atomic save/load with debouncing and crash-safe writes.
"""

import tempfile

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional


class PersistenceManager:
    """Atomic, debounced disk persistence for knowledge graph."""

    def __init__(self, path: Optional[Path] = None, debounce_seconds: float = 1.0):
        self.path = path
        self.debounce = debounce_seconds
        self._last_persist = 0.0
        self._pending = False
        self._last_saved_facts: Optional[Dict[str, Any]] = None

    def save(self, facts: Dict[str, Any], force: bool = False) -> None:
        if not self.path:
            return
        # Cache facts for potential flush on close
        self._last_saved_facts = facts
        now = time.time()
        if not force and (now - self._last_persist) < self.debounce:
            self._pending = True
            return
        self._atomic_write(facts)
        self._last_persist = now
        self._pending = False

    def load(self) -> Optional[Dict[str, Any]]:
        if not self.path or not self.path.exists():
            return None
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            # Convert dict data back to proper objects elsewhere
            return self._convert_loaded(data.get("facts", {}))
        except Exception as e:
            import logging

            logging.getLogger(__name__).warning("Knowledge graph load failed: %s", e)
            return None

    def close(self):
        # Flush pending data if any
        if self._pending and self._last_saved_facts is not None:
            self.save(self._last_saved_facts, force=True)

    # ---------- Internal ----------
    def _atomic_write(self, facts: Dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        export = {fid: self._serialize_fact(fact) for fid, fact in facts.items()}
        data = {"facts": export, "version": "2.0"}
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=self.path.parent,
            delete=False,
            suffix=".tmp",
        ) as tmp:
            json.dump(data, tmp, indent=2, default=str)
            tmp_path = tmp.name
        os.replace(tmp_path, str(self.path))

    def _serialize_fact(self, fact) -> Dict[str, Any]:
        d = fact.to_dict()
        # Status and evidence strength are already serialized as strings by to_dict()
        d["context_tags"] = list(d["context_tags"])
        return d

    def _convert_loaded(self, facts_dict: Dict[str, Any]) -> Dict[str, Any]:
        # Defer to graph_manager to rebuild proper objects
        return facts_dict

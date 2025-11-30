"""
Serialization and deserialization for pattern analyzer
Blueprint 4: Statistical Self-Improvement (Patterns)
"""

import tempfile
from enum import Enum

import json
import os
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base import ComplexityLevel, ContextSnapshot, Interaction, Outcome, ToolProfile


class EnumEncoder(json.JSONEncoder):
    """JSON encoder that properly serializes Enum values and sets"""

    def default(self, obj: Any) -> Any:
        if isinstance(obj, Enum):
            return obj.value
        if isinstance(obj, set):
            return list(obj)
        return super().default(obj)


class PatternPersistence:
    """Handles persistence and loading of pattern analyzer state"""

    def __init__(
        self,
        interactions: Dict,
        tool_profiles: Dict,
        causal_patterns: Dict,
        learning_curve: List,
        persistence_path: Optional[Path] = None,
    ):
        self.interactions = interactions
        self.tool_profiles = tool_profiles
        self.causal_patterns = causal_patterns
        self.learning_curve = learning_curve
        self.persistence_path = persistence_path

        # Persistence settings
        self._pending_persist = False
        self._last_persist_time = 0
        self._persist_debounce_seconds = 1.0
        self._lock = None

    def set_lock(self, lock):
        """Set the thread lock from the analyzer"""
        self._lock = lock

    def persist(self, force: bool = False) -> None:
        """Save analyzer state with compression and debouncing"""
        if not self.persistence_path:
            return

        current_time = time.time()
        time_since_last_persist = current_time - self._last_persist_time

        if not force and time_since_last_persist < self._persist_debounce_seconds:
            self._pending_persist = True
            return

        try:
            self.persistence_path.parent.mkdir(parents=True, exist_ok=True)

            if self._lock:
                with self._lock:
                    data = self._prepare_data()
            else:
                data = self._prepare_data()

            # Write to temp file first, then atomic replace
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.persistence_path.parent,
                delete=False,
                suffix=".tmp",
            ) as tmp_file:
                json.dump(data, tmp_file, indent=2, cls=EnumEncoder)
                tmp_path = tmp_file.name

            os.replace(tmp_path, str(self.persistence_path))

            self._last_persist_time = current_time
            self._pending_persist = False

        except Exception as e:
            import sys

            print(f"[ERROR] Pattern analyzer persistence failed: {e}", file=sys.stderr)

    def _prepare_data(self) -> Dict:
        """Prepare data for serialization"""
        return {
            "interactions": {
                iid: interaction.to_dict()
                for iid, interaction in self.interactions.items()
            },
            "tool_profiles": {
                name: self._tool_profile_to_dict(profile)
                for name, profile in self.tool_profiles.items()
            },
            "causal_patterns": {},  # Will be implemented later
            "learning_curve": self.learning_curve,
            "version": "2.0",
        }

    def _tool_profile_to_dict(self, profile: ToolProfile) -> Dict:
        """Convert tool profile to dictionary"""
        return {
            "name": profile.name,
            "success_rate": profile.success_rate,
            "average_execution_time": profile.average_execution_time,
            "reliability_score": profile.reliability_score,
            "context_preferences": profile.context_preferences,
            "common_failure_modes": profile.common_failure_modes,
            "prerequisite_sensitivity": profile.prerequisite_sensitivity,
            "learning_curve": profile.learning_curve,
        }

    def load(self) -> None:
        """Load analyzer state from file"""
        if not self.persistence_path or not self.persistence_path.exists():
            return

        try:
            with open(self.persistence_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Load interactions
            for iid, interaction_data in data.get("interactions", {}).items():
                interaction = self._dict_to_interaction(interaction_data)
                self.interactions[iid] = interaction

            # Load tool profiles
            for name, profile_data in data.get("tool_profiles", {}).items():
                profile = self._dict_to_tool_profile(profile_data)
                self.tool_profiles[name] = profile

            # Load learning curve
            self.learning_curve.clear()
            self.learning_curve.extend(data.get("learning_curve", []))

        except Exception as e:
            import sys

            print(
                f"[ERROR] Failed to load pattern analyzer state: {e}", file=sys.stderr
            )

    def _dict_to_interaction(self, data: Dict) -> Interaction:
        """Convert dictionary to Interaction object"""
        # Reconstruct context snapshot
        context_data = data["context"]
        context = ContextSnapshot(
            conversation_length=context_data["conversation_length"],
            recent_tools=context_data["recent_tools"],
            task_type=context_data["task_type"],
            complexity=ComplexityLevel(context_data["complexity"]),
            user_expertise=context_data["user_expertise"],
            time_of_day=context_data["time_of_day"],
            working_memory_usage=context_data["working_memory_usage"],
            emotional_tone=context_data.get("emotional_tone"),
            urgency_level=context_data.get("urgency_level", 1),
        )

        # Reconstruct interaction
        return Interaction(
            id=data["id"],
            tool_name=data["tool_name"],
            arguments=data["arguments"],
            outcome=Outcome(data["outcome"]),
            execution_time=data["execution_time"],
            timestamp=data["timestamp"],
            context=context,
            error_message=data.get("error_message"),
            result=data.get("result"),
            pre_conditions=(
                set(data.get("pre_conditions", []))
                if data.get("pre_conditions")
                else None
            ),
            post_conditions=(
                set(data.get("post_conditions", []))
                if data.get("post_conditions")
                else None
            ),
            confidence=data.get("confidence", 1.0),
            retry_count=data.get("retry_count", 0),
            alternative_approaches_considered=data.get(
                "alternative_approaches_considered"
            ),
        )

    def _dict_to_tool_profile(self, data: Dict) -> ToolProfile:
        """Convert dictionary to ToolProfile object"""
        return ToolProfile(
            name=data["name"],
            success_rate=data["success_rate"],
            average_execution_time=data["average_execution_time"],
            reliability_score=data["reliability_score"],
            context_preferences=data["context_preferences"],
            common_failure_modes=data["common_failure_modes"],
            prerequisite_sensitivity=data["prerequisite_sensitivity"],
            learning_curve=data["learning_curve"],
        )

    def close(self) -> None:
        """Flush any pending persists on close"""
        if self._pending_persist:
            self.persist(force=True)

#!/usr/bin/env python3
"""
Knowledge Graph Manager for Protocol Monk

Manages the semantic knowledge graph for long-term memory and reasoning.
"""

import asyncio
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from exceptions.base import MonkBaseError
from .risk_analyzer import RiskAnalyzer

_logger = logging.getLogger(__name__)


class GraphManagerError(MonkBaseError):
    """Raised for internal graph consistency or I/O problems."""

    pass

import logging
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from .base import ActionPlan, Evidence, EvidenceStrength, Fact, FactStatus
from .persistence import PersistenceManager
from .query_engine import QueryEngine
from .risk_analyzer import RiskAnalyzer

_logger = logging.getLogger(__name__)


class GraphManagerError(Exception):
    """Raised for internal graph consistency or I/O problems."""

    pass


class KnowledgeGraph:
    """
    Tracks facts with evidence chains, relationships, and actionable insights.
    Public API remains backward-compatible.

    Supports telemetry callback for integration with PatternAnalyzer.
    """

    def __init__(
        self,
        persistence_path: Optional[Path] = None,
        telemetry_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ):
        # Legacy failure tracking (for backward compatibility)
        self.failures = []

        # Convert string to Path if necessary
        if persistence_path and not isinstance(persistence_path, Path):
            persistence_path = Path(persistence_path)

        # New fact-based knowledge system
        self._facts: Dict[str, Fact] = {}  # fact_id -> Fact
        self._fact_index: Dict[str, List[str]] = {}  # fact_type -> [fact_ids]
        self._context_index: Dict[str, List[str]] = {}  # context_tag -> [fact_ids]
        self._persistence = PersistenceManager(persistence_path)
        self._query = QueryEngine(self._facts, self._fact_index, self._context_index)
        self._risk = RiskAnalyzer(self._facts, self._fact_index)

        # Telemetry callback for Pattern Analyzer integration
        self.telemetry_callback = telemetry_callback

        # Debounced persistence
        self._pending_persist = False
        self._last_persist_time = 0.0
        self._persist_debounce_seconds = 1.0

        if persistence_path and persistence_path.exists():
            self._load()

    # ---------- Properties for backward compatibility ----------
    @property
    def facts(self) -> Dict[str, Fact]:
        """Read-only access to facts dictionary for backward compatibility."""
        return self._facts

    # ---------- Public CRUD API ----------
    def add_fact(
        self,
        fact_type: str,
        value,
        evidence: Evidence,
        status: FactStatus = FactStatus.VERIFIED,
        context_tags: Optional[Set[str]] = None,
        depends_on: Optional[List[str]] = None,
    ) -> str:
        fact = Fact.new(
            fact_type=fact_type,
            value=value,
            evidence=evidence,
            status=status,
            context_tags=context_tags,
            depends_on=depends_on,
        )
        self._facts[fact.id] = fact
        self._index_fact(fact)

        # Emit telemetry for Pattern Analyzer
        if self.telemetry_callback:
            self.telemetry_callback(
                {
                    "event_type": "fact_added",
                    "fact_id": fact.id,
                    "fact_type": fact_type,
                    "value": value,
                    "status": status.name,
                    "context_tags": list(context_tags) if context_tags else [],
                }
            )

        self._persist()
        return fact.id

    def add_evidence(self, fact_id: str, evidence: Evidence) -> None:
        fact = self._get_fact(fact_id)
        old_status = fact.status
        fact.evidences.append(evidence)
        fact.updated_at = evidence.timestamp

        # Bayesian-ish pooling: combine confidences instead of just taking max
        # This prevents later weak evidence from dropping confidence
        new_conf = 1 - (1 - fact.confidence) * (1 - evidence.strength.value)
        fact.confidence = min(new_conf, 0.999)  # Cap below 1.0

        # Check if status should change based on evidence
        new_status = self._infer_status_from_evidence(fact)
        if new_status != old_status:
            _logger.info(
                f"Fact {fact_id} status changed: {old_status.name} → {new_status.name}"
            )
            fact.status = new_status
            self._cascade_status_change(fact_id, old_status, new_status)

        # Emit telemetry for Pattern Analyzer
        if self.telemetry_callback:
            self.telemetry_callback(
                {
                    "event_type": "evidence_added",
                    "fact_id": fact_id,
                    "evidence": {
                        "content": evidence.content,
                        "strength": evidence.strength.name,
                        "timestamp": evidence.timestamp,
                    },
                    "old_status": old_status.name,
                    "new_status": new_status.name,
                }
            )

        self._persist()

    def get_facts_by_type(
        self, fact_type: str, min_confidence: float = 0.0
    ) -> List[Fact]:
        return self._query.by_type(fact_type, min_confidence)

    def get_facts_by_context(
        self, context_tags: Set[str], min_confidence: float = 0.0
    ) -> List[Fact]:
        return self._query.by_context(context_tags, min_confidence)

    # ---------- Dependency Management ----------
    def add_dependency(self, fact_id: str, depends_on_fact_id: str) -> None:
        fact = self._get_fact(fact_id)
        dep = self._get_fact(depends_on_fact_id)
        if depends_on_fact_id not in fact.depends_on:
            fact.depends_on.append(depends_on_fact_id)
            # Populate reverse link for bidirectional graph traversal
            if fact_id not in dep.required_for:
                dep.required_for.append(fact_id)
            self._persist()

    def get_dependency_chain(self, fact_id: str) -> List[Fact]:
        visited, chain = set(), []

        def _collect(fid: str):
            if fid in visited:
                return
            visited.add(fid)
            fact = self._facts[fid]
            # Collect dependencies first (depth-first)
            for dep_id in fact.depends_on:
                _collect(dep_id)
            # Add this fact to the chain after its dependencies
            chain.append(fact)

        _collect(fact_id)
        return chain

    def validate_fact_dependencies(self, fact_id: str) -> Tuple[bool, List[str]]:
        fact = self._get_fact(fact_id)
        invalid = []
        for dep_id in fact.depends_on:
            if dep_id not in self._facts:
                invalid.append(f"Missing dependency: {dep_id}")
            elif self._facts[dep_id].status == FactStatus.REFUTED:
                invalid.append(f"Refuted dependency: {dep_id}")
        return len(invalid) == 0, invalid

    # ---------- Actionable Insights ----------
    def build_action_plan(self, goal: str, context_tags: Set[str]) -> ActionPlan:
        return self._query.build_action_plan(goal, context_tags)

    def context_summary(self, context_tags: Set[str]) -> Dict:
        return self._query.context_summary(context_tags)

    def should_retry(self, tool_name: str, arguments: dict) -> Tuple[bool, str]:
        return self._risk.should_retry(tool_name, arguments)

    def get_relevant_context(self, intent: str) -> Dict:
        return self._risk.relevant_context(intent)

    def predict_failure_risks(self, proposed_action: str) -> List[str]:
        return self._risk.predict_failure_risks(proposed_action)

    def suggest_verification_steps(self, proposed_action: str) -> List[str]:
        return self._risk.suggest_verification_steps(proposed_action)

    def query_failures(self, tool_name: str) -> list:
        """Queries the knowledge graph for past failures of a specific tool."""
        return [f for f in self.failures if f["tool_name"] == tool_name]

    # ---------- Backward Compatibility Shims ----------
    def mark_verified(
        self, fact_type, value, evidence, source="tool_execution", confidence=1.0
    ):
        from .base import EvidenceStrength

        strength = (
            EvidenceStrength.CONCLUSIVE
            if confidence >= 1.0
            else (
                EvidenceStrength.STRONG
                if confidence >= 0.9
                else (
                    EvidenceStrength.MODERATE
                    if confidence >= 0.7
                    else EvidenceStrength.WEAK
                )
            )
        )
        ev = Evidence.new(source=source, content=evidence, strength=strength)
        self.add_fact(
            fact_type=fact_type,
            value=value,
            evidence=ev,
            status=FactStatus.VERIFIED,
            context_tags={source},
        )

    def is_verified(self, fact_type: str) -> bool:
        return any(
            f.status == FactStatus.VERIFIED for f in self.get_facts_by_type(fact_type)
        )

    # ---------- Context Manager ----------
    def record_failure(
        self,
        tool_name=None,
        arguments=None,
        error_message=None,
        context_summary="",
        **kwargs,
    ):
        tool_name = tool_name or kwargs.get("tool_name")
        arguments = arguments or kwargs.get("arguments", {})
        error_message = error_message or kwargs.get("error_message", "")

        # Legacy: populate failures list for backward compatibility
        failure_record = {
            "tool_name": tool_name,
            "arguments": arguments,
            "error_message": error_message,
        }
        self.failures.append(failure_record)

        # Record failure embedding for Pattern Analyzer
        self._risk.record_failure_embedding(tool_name, arguments, error_message)

        ev = Evidence.new(
            source="tool_execution",
            content=f"Tool '{tool_name}' rejected by user: {error_message}",
            strength=EvidenceStrength.WEAK,
            tool_used=tool_name,
            tool_args=arguments,
            tool_result={"status": "rejected", "reason": context_summary},
        )
        self.add_fact(
            fact_type="tool_rejection",
            value={"tool": tool_name, "args": arguments, "reason": error_message},
            evidence=ev,
            status=FactStatus.REFUTED,
            context_tags={"tool_execution", "user_rejection"},
        )

    def _get_verified_facts(self) -> List[Any]:
        """Get verified facts sorted by update time.

        Returns:
            List of verified facts sorted by update time (newest first)
        """
        verified = [f for f in self._facts.values() if f.status == FactStatus.VERIFIED]
        verified.sort(key=lambda f: f.updated_at, reverse=True)
        return verified

    def _get_refuted_facts(self) -> List[Any]:
        """Get refuted facts sorted by update time.

        Returns:
            List of refuted facts sorted by update time (newest first)
        """
        refuted = [f for f in self._facts.values() if f.status == FactStatus.REFUTED]
        refuted.sort(key=lambda f: f.updated_at, reverse=True)
        return refuted

    def _format_verified_facts(self, verified: List[Any]) -> List[str]:
        """Format verified facts for display.

        Args:
            verified: List of verified facts

        Returns:
            List of formatted strings for verified facts
        """
        lines = []
        if verified:
            lines.append("Verified Facts:")
            lines.extend(
                f"  • {f.fact_type}: {f.value} (confidence: {f.confidence:.2f})"
                for f in verified[:5]
            )
        return lines

    def _format_refuted_facts(self, refuted: List[Any]) -> List[str]:
        """Format refuted facts for display.

        Args:
            refuted: List of refuted facts

        Returns:
            List of formatted strings for refuted facts
        """
        lines = []
        if refuted:
            lines.append("Recent Failures (avoid these approaches):")
            for f in refuted[:3]:
                if isinstance(f.value, dict) and "tool" in f.value:
                    reason = f.value.get("reason", "")
                    lines.append(f"  • {f.value['tool']}: {reason}")
        return lines

    def to_prompt_context(self) -> str:
        """Generate a string representation of the knowledge state for prompt context.

        Returns:
            Formatted string containing verified facts and recent failures
        """
        verified = self._get_verified_facts()
        refuted = self._get_refuted_facts()

        lines = ["[KNOWLEDGE STATE]"]
        lines.extend(self._format_verified_facts(verified))
        lines.extend(self._format_refuted_facts(refuted))

        return "\n".join(lines)

    # ---------- Persistence API ----------
    def save(self):
        """Explicitly save the knowledge graph to disk."""
        self._persist(force=True)

    def load(self):
        """Explicitly load the knowledge graph from disk."""
        self._load()

    # ---------- Context Manager ----------
    def close(self):
        """Close the knowledge graph and save pending changes."""
        self._persist(force=True)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    # ---------- Internal Helpers ----------
    def _get_fact(self, fact_id: str) -> Fact:
        if fact_id not in self._facts:
            raise GraphManagerError(f"Fact {fact_id} not found")
        return self._facts[fact_id]

    def _index_fact(self, fact: Fact) -> None:
        self._fact_index.setdefault(fact.fact_type, []).append(fact.id)
        for tag in fact.context_tags:
            self._context_index.setdefault(tag, []).append(fact.id)

    def _persist(self, force: bool = False) -> None:
        self._persistence.save(self._facts, force=force)

    def _load(self) -> None:
        loaded = self._persistence.load()
        if loaded:
            # Convert loaded dicts back to Fact objects
            # Clear and update existing dict to preserve references held by QueryEngine/RiskAnalyzer
            self._facts.clear()
            for fid, data in loaded.items():
                self._facts[fid] = Fact.from_dict(data)
            self._rebuild_indexes()

    def _rebuild_indexes(self) -> None:
        self._fact_index.clear()
        self._context_index.clear()
        self.failures.clear()  # Rebuild legacy failures list

        for fact in self._facts.values():
            self._index_fact(fact)

            # Rebuild legacy failures list from tool_rejection facts
            if fact.fact_type == "tool_rejection" and isinstance(fact.value, dict):
                failure_record = {
                    "tool_name": fact.value.get("tool"),
                    "arguments": fact.value.get("args", {}),
                    "error_message": fact.value.get("reason", ""),
                }
                self.failures.append(failure_record)

    def _infer_status_from_evidence(self, fact: Fact) -> FactStatus:
        """Infer fact status from accumulated evidence."""
        if fact.confidence >= 0.9:
            return FactStatus.VERIFIED
        elif fact.confidence >= 0.5:
            return FactStatus.ASSUMED
        elif fact.confidence < 0.3:
            return FactStatus.REFUTED
        else:
            return FactStatus.UNCERTAIN

    def _cascade_status_change(
        self, fact_id: str, old_status: FactStatus, new_status: FactStatus
    ) -> None:
        """Cascade status changes to dependent facts."""
        # If a fact is refuted, mark all facts that depend on it as uncertain
        if new_status == FactStatus.REFUTED:
            fact = self._facts[fact_id]
            for dependent_id in fact.required_for:
                dependent = self._facts.get(dependent_id)
                if dependent and dependent.status != FactStatus.REFUTED:
                    _logger.info(
                        f"Cascading refutation: {dependent_id} → UNCERTAIN (dependency {fact_id} was refuted)"
                    )
                    dependent.status = FactStatus.UNCERTAIN
                    # Could recursively cascade further, but keeping it shallow for now
                    self._cascade_status_change(
                        dependent_id, dependent.status, FactStatus.UNCERTAIN
                    )

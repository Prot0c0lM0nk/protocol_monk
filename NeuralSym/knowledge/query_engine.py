"""
Query and planning logic for the knowledge graph.

Provides context-aware queries, action plan generation, and summaries.
"""

from collections import defaultdict

import time
from typing import Any, Dict, List, Set

from .base import ActionPlan, EvidenceStrength, Fact, FactStatus

# Patterns for inferring required facts
GOAL_PATTERNS = {
    "file_operation": ["file_exists", "file_permissions", "directory_exists"],
    "api_operation": ["api_available", "authentication_valid", "endpoint_accessible"],
    "network_operation": ["network_available", "url_accessible", "dns_resolvable"],
}

TOOL_MAPPING = {
    "file_exists": ["list_files", "check_file"],
    "file_permissions": ["check_permissions"],
    "directory_exists": ["list_files", "check_directory"],
    "api_available": ["test_endpoint", "make_request"],
    "authentication_valid": ["test_auth", "validate_credentials"],
    "network_available": ["ping", "check_connectivity"],
}

# Common knowledge gaps by context
COMMON_GAPS = {
    "file_operations": ["backup_exists", "disk_space", "file_format"],
    "network_operations": ["latency", "bandwidth", "firewall_rules"],
    "api_operations": ["rate_limits", "response_format", "error_patterns"],
}


class QueryEngine:
    """Read-only query and planning operations on the knowledge graph."""

    def __init__(self, facts, fact_index, context_index):
        self._facts = facts
        self._fact_index = fact_index
        self._context_index = context_index

    def by_type(self, fact_type: str, min_confidence: float = 0.0) -> List[Fact]:
        ids = self._fact_index.get(fact_type, [])
        facts = [
            self._facts[fid]
            for fid in ids
            if self._facts[fid].confidence >= min_confidence
        ]
        return sorted(facts, key=lambda f: f.confidence, reverse=True)

    def by_context(
        self, context_tags: Set[str], min_confidence: float = 0.0
    ) -> List[Fact]:
        relevant = set()
        for tag in context_tags:
            relevant.update(self._context_index.get(tag, []))
        return [
            self._facts[fid]
            for fid in relevant
            if self._facts[fid].confidence >= min_confidence
        ]

    def build_action_plan(self, goal: str, context_tags: Set[str]) -> ActionPlan:
        relevant = self.by_context(context_tags, min_confidence=0.7)
        verified = [f for f in relevant if f.status == FactStatus.VERIFIED]
        known_types = {f.fact_type for f in verified}
        required = self._infer_required_facts(goal, known_types)
        missing = [ft for ft in required if ft not in known_types]
        confidence = self._calculate_confidence(verified)
        tools = self._suggest_tools(missing)
        reasoning = self._generate_reasoning(goal, known_types, missing)
        from .base import ActionPlan

        return ActionPlan(
            goal=goal,
            required_facts=required,
            missing_facts=missing,
            confidence=confidence,
            reasoning=reasoning,
            suggested_tools=tools,
        )

    def context_summary(self, context_tags: Set[str]) -> Dict[str, Any]:
        relevant = self.by_context(context_tags)
        verified = [f for f in relevant if f.status == FactStatus.VERIFIED]
        assumed = [f for f in relevant if f.status == FactStatus.ASSUMED]
        strongest = max(
            (ev for f in verified for ev in f.evidences),
            key=lambda e: e.strength.value,
            default=None,
        )
        return {
            "total_relevant_facts": len(relevant),
            "verified_facts": len(verified),
            "assumed_facts": len(assumed),
            "average_confidence": (
                sum(f.confidence for f in relevant) / len(relevant) if relevant else 0
            ),
            "knowledge_gaps": self._identify_gaps(context_tags),
            "strongest_evidence": strongest,
        }

    # ---------- Internal ----------
    def _infer_required_facts(self, goal: str, known: Set[str]) -> List[str]:
        """Infer required facts using token-based scoring for better matching."""
        import re

        goal_tokens = set(re.findall(r"[a-z]+", goal.lower()))
        best_match = ["environment_ready", "permissions_available"]
        best_score = 0

        for pattern, facts in GOAL_PATTERNS.items():
            # Score by token overlap
            pattern_tokens = set(pattern.split("_"))
            score = len(goal_tokens & pattern_tokens)
            if score > best_score:
                best_match, best_score = facts, score

        return best_match

    def _suggest_tools(self, missing: List[str]) -> List[str]:
        tools = set()
        for fact in missing:
            tools.update(TOOL_MAPPING.get(fact, []))
        return list(tools)

    def _calculate_confidence(self, verified: List[Fact]) -> float:
        if not verified:
            return 0.0
        return sum(f.confidence for f in verified) / len(verified)

    def _generate_reasoning(
        self, goal: str, known: Set[str], missing: List[str]
    ) -> str:
        if not missing:
            return f"All required facts for '{goal}' are verified. Ready to proceed."
        return (
            f"For '{goal}', need to verify: {', '.join(missing)}. "
            f"Already know: {', '.join(known) or 'nothing relevant'}"
        )

    def _identify_gaps(self, context_tags: Set[str]) -> List[str]:
        gaps = []
        for ctx, potential in COMMON_GAPS.items():
            if any(tag in context_tags for tag in [ctx, "all"]):
                for gap in potential:
                    if not self.by_type(gap):
                        gaps.append(gap)
        return gaps

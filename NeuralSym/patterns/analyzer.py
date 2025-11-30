"""
Core pattern analysis logic
Blueprint 4: Statistical Self-Improvement (Patterns)

This module provides the AdvancedPatternAnalyzer which records tool interactions
and builds statistical profiles to predict future success probabilities.
"""

import threading
from collections import Counter, defaultdict
from threading import Lock

import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from .base import (
    ComplexityLevel,
    ContextSnapshot,
    Interaction,
    Outcome,
    PredictiveRecommendation,
    ToolProfile,
)
from .persistence import PatternPersistence
from .predictor import PatternPredictor
from .sequence_analyzer import SequenceAnalyzer
from .temporal_analyzer import TemporalAnalyzer


class AdvancedPatternAnalyzer:
    """
    Advanced pattern analysis with causal inference and predictive modeling

    This analyzer learns from every tool interaction to build predictive models
    that can recommend optimal approaches and warn about potential failures.
    """

    def __init__(self, persistence_path: Optional[Path] = None):
        # Core data stores
        self.interactions: Dict[str, Interaction] = {}
        self.causal_patterns: Dict[str, Any] = {}
        self.tool_profiles: Dict[str, ToolProfile] = {}
        self.sequence_patterns: Dict[Tuple[str, ...], Dict] = {}

        # Advanced analytics
        self.context_clusters: Dict[str, Any] = {}
        self.temporal_patterns: Dict[str, Any] = {}
        self.complexity_impact: Dict[ComplexityLevel, float] = {}
        self.correlation_counts = defaultdict(int)

        # Performance metrics
        self.learning_curve: List[Tuple[float, float]] = []
        self.adaptation_speed: float = 1.0

        # Persistence setup
        self.persistence_path = persistence_path
        self._lock = Lock()

        # Debounced persistence
        self._pending_persist = False
        self._last_persist_time = 0
        self._persist_debounce_seconds = 1.0

        # Bayesian priors
        self.prior_success_rate = 0.5
        self.prior_tool_preference = defaultdict(lambda: 0.1)

        # Initialize component analyzers
        self.predictor = PatternPredictor(
            self.interactions, self.tool_profiles, self.sequence_patterns
        )
        self.sequence_analyzer = SequenceAnalyzer(
            self.interactions, self.sequence_patterns, self.tool_profiles
        )
        self.temporal_analyzer = TemporalAnalyzer(
            self.interactions, self.learning_curve, self.temporal_patterns
        )
        self.persistence = PatternPersistence(
            self.interactions,
            self.tool_profiles,
            self.causal_patterns,
            self.learning_curve,
            persistence_path,
        )
        self.persistence.set_lock(self._lock)

        # Start debounce worker thread
        self._debounce_thread = threading.Thread(
            target=self._debounce_worker, daemon=True
        )
        self._debounce_thread.start()

        # Load existing data if available
        if persistence_path and persistence_path.exists():
            self._load()

    def record_interaction(
        self,
        tool_name: str,
        arguments: Dict,
        outcome: Outcome,
        execution_time: float,
        context: Dict,
        error_message: Optional[str] = None,
        result: Optional[Any] = None,
        pre_conditions: Optional[Set[str]] = None,
        post_conditions: Optional[Set[str]] = None,
        confidence: float = 1.0,
        retry_count: int = 0,
    ) -> str:
        """
        Record interaction with comprehensive analysis

        Args:
            tool_name: Name of the tool that was executed
            arguments: Arguments passed to the tool
            outcome: The outcome of the execution (SUCCESS, FAILURE, etc.)
            execution_time: How long the tool took to execute
            context: Context snapshot dictionary
            error_message: Optional error message if tool failed
            result: Optional result data from tool execution
            pre_conditions: Optional set of preconditions that were met
            post_conditions: Optional set of postconditions that resulted
            confidence: Confidence level in the outcome (0.0-1.0)
            retry_count: Number of times this was retried

        Returns:
            Unique interaction ID
        """
        interaction_id = str(uuid.uuid4())

        # Memory protection: truncate huge arguments
        if len(str(arguments)) > 10_000:
            arguments = {
                "_truncated": True,
                "_original_size": len(str(arguments)),
                "_summary": f"Large arguments truncated (original size: {len(str(arguments))} chars)",
            }

        # Convert context dict to ContextSnapshot
        context_snapshot = self._create_context_snapshot(context)

        interaction = Interaction(
            id=interaction_id,
            tool_name=tool_name,
            arguments=arguments,
            outcome=outcome,
            execution_time=execution_time,
            timestamp=time.time(),
            context=context_snapshot,
            error_message=error_message,
            result=result,
            pre_conditions=pre_conditions or set(),
            post_conditions=post_conditions or set(),
            confidence=confidence,
            retry_count=retry_count,
        )

        with self._lock:
            self.interactions[interaction_id] = interaction

            # Update all analytical models
            self._update_tool_profiles(interaction)
            self._analyze_causal_relationships(interaction)
            self._update_context_clusters(interaction)
            self.temporal_analyzer.analyze_temporal_patterns(interaction)
            self._update_learning_curve(interaction)

            # Advanced pattern detection
            self.sequence_analyzer.detect_sequence_patterns(interaction_id)
            self._analyze_complexity_impact(interaction)
            self._detect_anti_patterns(interaction)

            # Cap sequence_patterns memory
            if len(self.sequence_patterns) > 10_000:
                top = sorted(
                    self.sequence_patterns.items(),
                    key=lambda kv: kv[1].get("total_count", 0),
                    reverse=True,
                )[:5000]
                self.sequence_patterns.clear()
                self.sequence_patterns.update(top)

            # Update component data references
            self.predictor.interactions = self.interactions
            self.predictor.tool_profiles = self.tool_profiles
            self.predictor.sequence_patterns = self.sequence_patterns

            # Memory management
            if len(self.interactions) % 250 == 0 or len(self.interactions) > 2000:
                self._manage_memory()

        self._persist()
        return interaction_id

    def on_knowledge_event(self, event: Dict[str, Any]) -> None:
        """
        Handle knowledge graph events for pattern learning.

        This method serves as the telemetry callback from KnowledgeGraph.
        It translates knowledge events (fact additions, evidence changes)
        into pattern interactions for statistical learning.

        Args:
            event: Event dictionary from KnowledgeGraph containing:
                - event_type: "fact_added" or "evidence_added"
                - fact_type, value, status, etc.
        """
        event_type = event.get("event_type")

        if event_type == "fact_added":
            self._handle_fact_added(event)
        elif event_type == "evidence_added":
            self._handle_evidence_added(event)

    def _handle_fact_added(self, event: Dict[str, Any]) -> None:
        """
        Handle fact_added events from knowledge graph.

        Converts knowledge facts into pattern interactions.
        """
        fact_type = event.get("fact_type")
        value = event.get("value", {})

        # Extract tool information if this is a tool-related fact
        if fact_type == "tool_success" and isinstance(value, dict):
            tool_name = value.get("tool")
            arguments = value.get("arguments", {})
            context = value.get("context", {})
            result = value.get("result")

            if tool_name:
                # Record as successful interaction
                self.record_interaction(
                    tool_name=tool_name,
                    arguments=arguments,
                    outcome=Outcome.SUCCESS,
                    execution_time=value.get("execution_time", 0),
                    context=context,
                    result=result,
                )

        elif fact_type == "tool_rejection" and isinstance(value, dict):
            tool_name = value.get("tool")
            arguments = value.get("args", {})
            reason = value.get("reason", "Unknown")
            context = value.get("context", {})

            if tool_name:
                # Record as failed interaction
                self.record_interaction(
                    tool_name=tool_name,
                    arguments=arguments,
                    outcome=Outcome.FAILURE,
                    execution_time=0,
                    context=context,
                    error_message=reason,
                )

    def _handle_evidence_added(self, event: Dict[str, Any]) -> None:
        """
        Handle evidence_added events from knowledge graph.

        Evidence changes can affect pattern confidence and learning.
        """
        # For now, evidence changes don't directly create interactions
        # They could be used to adjust confidence in existing patterns
        # This is a hook for future enhancement
        pass

    def _create_context_snapshot(self, context: Dict) -> ContextSnapshot:
        """Create enriched context snapshot from context dictionary"""
        return ContextSnapshot(
            conversation_length=context.get("conversation_length", 0),
            recent_tools=context.get("recent_tools", [])[-5:],
            task_type=context.get("task_type", "unknown"),
            complexity=ComplexityLevel(context.get("complexity", "moderate")),
            user_expertise=context.get("user_expertise", "intermediate"),
            time_of_day=time.strftime("%H:%M"),
            working_memory_usage=context.get("working_memory_usage", 0.5),
            emotional_tone=context.get("emotional_tone"),
            urgency_level=context.get("urgency_level", 1),
        )

    def _update_tool_profiles(self, interaction: Interaction) -> None:
        """Update comprehensive tool performance profiles"""
        tool_name = interaction.tool_name

        if tool_name not in self.tool_profiles:
            self.tool_profiles[tool_name] = ToolProfile(
                name=tool_name,
                success_rate=0.5,
                average_execution_time=interaction.execution_time,
                reliability_score=0.5,
                context_preferences={},
                common_failure_modes={},
                prerequisite_sensitivity=0.5,
                learning_curve=0.5,
            )

        profile = self.tool_profiles[tool_name]

        # Update success rate with Bayesian smoothing
        total_uses = sum(
            1 for i in self.interactions.values() if i.tool_name == tool_name
        )
        successes = sum(
            1
            for i in self.interactions.values()
            if i.tool_name == tool_name and i.outcome == Outcome.SUCCESS
        )

        # Bayesian success rate estimate: (successes + 1) / (total + 2)
        profile.success_rate = (successes + 1) / (total_uses + 2)

        # Update execution time with exponential moving average
        alpha = 0.1
        profile.average_execution_time = (
            alpha * interaction.execution_time
            + (1 - alpha) * profile.average_execution_time
        )

        # Update context preferences
        context_key = self._get_context_signature(interaction.context)
        current_score = profile.context_preferences.get(context_key, 0.5)
        success_bonus = 0.1 if interaction.outcome == Outcome.SUCCESS else -0.05
        profile.context_preferences[context_key] = max(
            0.1, min(0.9, current_score + success_bonus)
        )

        # Update failure modes
        if interaction.outcome == Outcome.FAILURE and interaction.error_message:
            error_type = self._categorize_error(interaction.error_message)
            profile.common_failure_modes[error_type] = (
                profile.common_failure_modes.get(error_type, 0) + 1
            )

    def _analyze_causal_relationships(self, interaction: Interaction) -> None:
        """Perform causal analysis using Granger causality"""
        # Analyze Granger causality for sequences
        if len(interaction.context.recent_tools) >= 1:
            self.sequence_analyzer.analyze_granger_causality(interaction)

    def _update_context_clusters(self, interaction: Interaction) -> None:
        """Update context clusters - stub implementation"""
        pass

    def _update_learning_curve(self, interaction: Interaction) -> None:
        """Update learning curve - stub implementation"""
        pass

    def _analyze_complexity_impact(self, interaction: Interaction) -> None:
        """Analyze complexity impact - stub implementation"""
        pass

    def _detect_anti_patterns(self, interaction: Interaction) -> None:
        """Detect anti-patterns - stub implementation"""
        pass

    def _get_context_signature(self, context: ContextSnapshot) -> str:
        """Generate signature for context matching"""
        parts = [
            f"len_{context.conversation_length}",
            f"complex_{context.complexity.value}",
            f"expert_{context.user_expertise}",
            f"urg_{context.urgency_level}",
        ]

        if context.recent_tools:
            parts.append(f"last_{context.recent_tools[-1]}")

        return "_".join(parts)

    def _categorize_error(self, error_message: str) -> str:
        """Categorize error messages for pattern analysis"""
        error_lower = error_message.lower()

        if "permission" in error_lower:
            return "permission_denied"
        elif "not found" in error_lower or "no such" in error_lower:
            return "resource_not_found"
        elif "timeout" in error_lower:
            return "timeout"
        elif "connection" in error_lower:
            return "connection_error"
        elif "syntax" in error_lower:
            return "syntax_error"
        elif "memory" in error_lower:
            return "memory_error"
        else:
            return "unknown_error"

    def _manage_memory(self) -> None:
        """Keep the 2000 most informative interactions"""
        if len(self.interactions) <= 2000:
            return

        # Score = rarity × complexity × recency
        scored = [
            (iid, self._calculate_interaction_value(interaction))
            for iid, interaction in self.interactions.items()
        ]

        # Keep top 2000
        scored.sort(key=lambda t: t[1], reverse=True)
        keep = {iid for iid, _ in scored[:2000]}

        # Delete the rest
        for iid in list(self.interactions.keys()):
            if iid not in keep:
                del self.interactions[iid]

    def _calculate_interaction_value(self, interaction: Interaction) -> float:
        """Calculate the informational value of an interaction"""
        import math

        # Rare outcomes are more valuable
        outcome_rarity = self._calculate_outcome_rarity(interaction.outcome)

        # Complex contexts are more valuable
        complexity_value = {
            ComplexityLevel.SIMPLE: 0.5,
            ComplexityLevel.MODERATE: 1.0,
            ComplexityLevel.COMPLEX: 1.5,
            ComplexityLevel.VERY_COMPLEX: 2.0,
        }.get(interaction.context.complexity, 1.0)

        # Recent interactions are more valuable (exponential decay)
        age_hours = (time.time() - interaction.timestamp) / 3600
        recency_factor = math.exp(-age_hours / 24)  # 24-hour half-life

        return outcome_rarity * complexity_value * recency_factor

    def _calculate_outcome_rarity(self, outcome: Outcome) -> float:
        """Calculate how rare an outcome is"""
        outcome_counts = Counter(i.outcome for i in self.interactions.values())
        total = sum(outcome_counts.values())

        if total == 0:
            return 1.0

        frequency = outcome_counts[outcome] / total
        return 1.0 - frequency

    # ========== PUBLIC API METHODS ==========

    def predict_best_approach(self, intent: str, context: Dict) -> List[str]:
        """Predict best approach based on intent and context"""
        return self.predictor.predict_best_approach(intent, context)

    def identify_common_mistakes(self, intent: str) -> List[str]:
        """Identify common mistakes for given intent"""
        return self.predictor.identify_common_mistakes(intent)

    def get_success_sequence(self, goal: str) -> List[str]:
        """Get successful tool sequence for goal"""
        return self.predictor.get_success_sequence(goal)

    def get_predictive_recommendations(
        self,
        current_context: Dict,
        available_tools: List[str],
        goal: str,
        constraints: Dict[str, Any] = None,
    ) -> List[PredictiveRecommendation]:
        """Get predictive recommendations with risk assessment"""
        return self.predictor.get_predictive_recommendations(
            current_context, available_tools, goal, constraints
        )

    def get_comprehensive_insights(self) -> Dict[str, Any]:
        """Get comprehensive analytical insights"""
        with self._lock:
            return {
                "performance_metrics": self._calculate_performance_metrics(),
                "pattern_effectiveness": self._evaluate_pattern_effectiveness(),
                "learning_progress": self.temporal_analyzer.analyze_learning_progress(),
                "context_sensitivity": self._analyze_context_sensitivity(),
                "risk_landscape": self._analyze_risk_landscape(),
                "optimization_opportunities": self._identify_optimization_opportunities(),
            }

    def _calculate_performance_metrics(self) -> Dict[str, float]:
        """Calculate advanced performance metrics"""
        total_interactions = len(self.interactions)
        if total_interactions == 0:
            return {}

        successes = sum(
            1 for i in self.interactions.values() if i.outcome == Outcome.SUCCESS
        )

        return {
            "overall_success_rate": successes / total_interactions,
            "weighted_success_rate": self._calculate_weighted_success_rate(),
            "adaptation_efficiency": self._calculate_adaptation_efficiency(),
            "tool_diversity_index": self._calculate_tool_diversity(),
            "context_adaptation_score": self._calculate_context_adaptation(),
            "learning_velocity": self.temporal_analyzer.calculate_learning_velocity(),
        }

    def _calculate_weighted_success_rate(self) -> float:
        """Calculate success rate weighted by complexity and importance"""
        total_weight = 0
        weighted_successes = 0

        for interaction in self.interactions.values():
            weight = self._calculate_interaction_weight(interaction)
            total_weight += weight
            if interaction.outcome == Outcome.SUCCESS:
                weighted_successes += weight

        return weighted_successes / total_weight if total_weight > 0 else 0

    def _calculate_interaction_weight(self, interaction: Interaction) -> float:
        """Calculate importance weight for an interaction"""
        complexity_weights = {
            ComplexityLevel.SIMPLE: 0.5,
            ComplexityLevel.MODERATE: 1.0,
            ComplexityLevel.COMPLEX: 1.5,
            ComplexityLevel.VERY_COMPLEX: 2.0,
        }

        base_weight = complexity_weights.get(interaction.context.complexity, 1.0)
        urgency_factor = 1.0 + (interaction.context.urgency_level - 1) * 0.2
        time_factor = 1.0 + min(interaction.execution_time / 60, 1.0)

        return base_weight * urgency_factor * time_factor

    def optimize_approach(
        self, current_plan: List[str], context: ContextSnapshot, goal: str
    ) -> Dict[str, Any]:
        """Optimize action plan based on learned patterns"""
        return self.sequence_analyzer.optimize_approach(current_plan, context, goal)

    # ========== STUB METHODS ==========

    def _evaluate_pattern_effectiveness(self) -> Dict:
        """Evaluate pattern effectiveness - stub"""
        return {}

    def _analyze_context_sensitivity(self) -> Dict:
        """Analyze context sensitivity - stub"""
        return {}

    def _analyze_risk_landscape(self) -> Dict:
        """Analyze risk landscape - stub"""
        return {}

    def _identify_optimization_opportunities(self) -> List[str]:
        """Identify optimization opportunities - stub"""
        return []

    def _calculate_adaptation_efficiency(self) -> float:
        """Calculate adaptation efficiency - stub"""
        return 0.8

    def _calculate_tool_diversity(self) -> float:
        """Calculate tool diversity index - stub"""
        return 0.7

    def _calculate_context_adaptation(self) -> float:
        """Calculate context adaptation score - stub"""
        return 0.6

    # ========== PERSISTENCE ==========

    def _persist(self, force: bool = False) -> None:
        """Save analyzer state with compression and debouncing"""
        self.persistence.persist(force)

    def _debounce_worker(self) -> None:
        """Background thread to flush pending persists at regular intervals"""
        while True:
            time.sleep(self._persist_debounce_seconds)
            if self._pending_persist:
                self._persist(force=True)
                self._pending_persist = False

    def _load(self) -> None:
        """Load analyzer state"""
        self.persistence.load()

    def close(self) -> None:
        """Ensure persistence on cleanup"""
        self.persistence.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

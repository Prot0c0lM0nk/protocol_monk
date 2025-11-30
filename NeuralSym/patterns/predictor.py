"""
Predictive recommendations and risk assessment
Blueprint 4: Statistical Self-Improvement (Patterns)
"""

from collections import defaultdict

from typing import Any, Dict, List, Optional

from .base import (
    ComplexityLevel,
    ContextSnapshot,
    Outcome,
    PredictiveRecommendation,
    ToolProfile,
)


class PatternPredictor:
    """Predictive recommendations and risk assessment engine"""

    def __init__(
        self, interactions: Dict, tool_profiles: Dict, sequence_patterns: Dict
    ):
        self.interactions = interactions
        self.tool_profiles = tool_profiles
        self.sequence_patterns = sequence_patterns
        self.prior_success_rate = 0.5

    def predict_best_approach(self, intent: str, context: Dict) -> List[str]:
        """Predict best approach based on intent and context"""
        recommendations = []

        # Map intent to likely tools
        intent_to_tools = {
            "FILE_READ_INTENT": ["show_file", "read_file", "execute_command"],
            "FILE_WRITE_INTENT": ["create_file", "edit_file"],
            "FILE_SEARCH_INTENT": ["execute_command", "search_files"],
            "COMMAND_EXECUTION_INTENT": ["execute_command", "run_python"],
            "CODE_ANALYSIS_INTENT": ["show_file", "read_file", "execute_command"],
        }

        relevant_tools = intent_to_tools.get(intent, [])

        # Analyze success rates for each relevant tool
        for tool_name in relevant_tools:
            if tool_name in self.tool_profiles:
                profile = self.tool_profiles[tool_name]
                success_rate = profile.success_rate
                avg_time = profile.average_execution_time

                # Check if we have context-specific performance data
                context_key = self._extract_context_key_from_dict(context)
                context_score = profile.context_preferences.get(
                    context_key, success_rate
                )

                recommendation = (
                    f"{tool_name}: {context_score:.1%} success rate "
                    f"(avg {avg_time:.1f}s, {self._count_tool_uses(tool_name)} uses)"
                )
                recommendations.append(recommendation)

        # Add sequence recommendations if we have pattern data
        if len(relevant_tools) >= 2:
            for i, tool1 in enumerate(relevant_tools):
                for tool2 in relevant_tools[i + 1 :]:
                    sequence = (tool1, tool2)
                    if sequence in self.sequence_patterns:
                        pattern = self.sequence_patterns[sequence]
                        total = pattern.get("successes", 0) + pattern.get("failures", 0)
                        if total >= 3:
                            success_rate = pattern.get("successes", 0) / total
                            if success_rate > 0.7:
                                recommendations.append(
                                    f"Sequence pattern: {tool1} → {tool2} = {success_rate:.1%} "
                                    f"({pattern.get('successes')} successes)"
                                )

        # If no data, provide general guidance
        if not recommendations:
            recommendations.append(
                f"No historical data for {intent}, proceed with caution"
            )

        return recommendations

    def identify_common_mistakes(self, intent: str) -> List[str]:
        """Identify common mistakes for given intent"""
        mistakes = []

        # Map intent to likely tools
        intent_to_tools = {
            "FILE_READ_INTENT": ["show_file", "read_file", "execute_command"],
            "FILE_WRITE_INTENT": ["create_file", "edit_file"],
            "FILE_SEARCH_INTENT": ["execute_command", "search_files"],
            "COMMAND_EXECUTION_INTENT": ["execute_command", "run_python"],
        }

        relevant_tools = intent_to_tools.get(intent, [])

        # Analyze common failure modes for each tool
        for tool_name in relevant_tools:
            if tool_name in self.tool_profiles:
                profile = self.tool_profiles[tool_name]

                # Get common failure modes
                for error_type, count in profile.common_failure_modes.items():
                    total_uses = self._count_tool_uses(tool_name)
                    if total_uses > 0:
                        failure_rate = count / total_uses
                        if failure_rate > 0.1:  # More than 10% failure rate
                            mistakes.append(
                                f"{error_type} with {tool_name} ({failure_rate:.0%} failure rate)"
                            )

        # Add general pattern-based mistakes
        if intent == "FILE_READ_INTENT":
            # Check if files are often not found
            not_found_count = sum(
                1
                for i in self.interactions.values()
                if i.tool_name in ["show_file", "read_file", "execute_command"]
                and i.outcome == Outcome.FAILURE
                and "not found" in (i.error_message or "").lower()
            )
            if not_found_count >= 3:
                mistakes.append(
                    f"File not found errors ({not_found_count} occurrences)"
                )

        return mistakes[:5]  # Top 5 mistakes

    def get_success_sequence(self, goal: str) -> List[str]:
        """Get successful tool sequence for goal"""
        goal_lower = goal.lower()

        # Check our sequence patterns for high-success sequences
        successful_sequences = []

        for sequence, pattern in self.sequence_patterns.items():
            total = pattern.get("successes", 0) + pattern.get("failures", 0)
            if total >= 3:  # Minimum sample size
                success_rate = pattern.get("successes", 0) / total
                if success_rate >= 0.7:  # High success rate
                    successful_sequences.append(
                        {
                            "sequence": sequence,
                            "success_rate": success_rate,
                            "count": total,
                        }
                    )

        # Sort by success rate
        successful_sequences.sort(key=lambda x: x["success_rate"], reverse=True)

        # Build recommended sequence
        if successful_sequences:
            best = successful_sequences[0]
            tool1, tool2 = best["sequence"]
            return [
                f"1. {tool1} - initial step",
                f"2. {tool2} - follow-up",
                f"Confidence: {best['success_rate']:.0%} (based on {best['count']} uses)",
            ]

        # Fallback: provide generic best practices based on goal
        if "read" in goal_lower or "show" in goal_lower:
            return [
                "1. list_files - verify location",
                "2. read_file - read content",
                "Confidence: 50% (general best practice)",
            ]
        elif "create" in goal_lower or "write" in goal_lower:
            return [
                "1. list_files - verify location",
                "2. create_file - create new file",
                "Confidence: 50% (general best practice)",
            ]
        else:
            return ["No specific sequence pattern identified for this goal"]

    def get_predictive_recommendations(
        self,
        current_context: Dict,
        available_tools: List[str],
        goal: str,
        constraints: Dict[str, Any] = None,
    ) -> List[PredictiveRecommendation]:
        """Get predictive recommendations with risk assessment"""
        recommendations = []
        context_snapshot = self._create_context_snapshot(current_context)
        constraints = constraints or {}

        # Predict optimal tools
        for tool in available_tools:
            if tool in self.tool_profiles:
                profile = self.tool_profiles[tool]

                # Calculate success probability
                success_prob = profile.success_rate

                # Check constraints
                if constraints.get("max_execution_time"):
                    if (
                        profile.average_execution_time
                        > constraints["max_execution_time"]
                    ):
                        continue

                # Build risk factors
                risk_factors = []
                for error_type, count in profile.common_failure_modes.items():
                    total_uses = self._count_tool_uses(tool)
                    if total_uses > 0:
                        risk_prob = count / total_uses
                        if risk_prob > 0.05:
                            risk_factors.append((error_type, risk_prob))

                recommendation = PredictiveRecommendation(
                    action=f"Use tool '{tool}'",
                    reasoning=f"Predicted success: {success_prob:.1%} based on historical data",
                    confidence=success_prob,
                    expected_success_probability=success_prob,
                    expected_time_savings=0.0,
                    risk_factors=risk_factors[:3],
                    prerequisites=[],
                    fallback_strategies=[],
                    similar_success_cases=[],
                    similar_failure_cases=[],
                )
                recommendations.append(recommendation)

        return sorted(
            recommendations, key=lambda r: r.expected_success_probability, reverse=True
        )[:5]

    # Helper methods

    def _extract_context_key_from_dict(self, context: Dict) -> str:
        """Extract context key from context dictionary"""
        return f"len_{context.get('conversation_length', 0)}_complex_{context.get('complexity', 'moderate')}"

    def _count_tool_uses(self, tool_name: str) -> int:
        """Count number of times a tool was used"""
        return sum(1 for i in self.interactions.values() if i.tool_name == tool_name)

    def _create_context_snapshot(self, context: Dict) -> ContextSnapshot:
        """Create ContextSnapshot from dictionary"""
        import time

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

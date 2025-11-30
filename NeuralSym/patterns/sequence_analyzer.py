"""
Tool sequence analysis and optimization
Blueprint 4: Statistical Self-Improvement (Patterns)
"""

from collections import defaultdict

from typing import Any, Dict, List, Optional, Tuple

from .base import ContextSnapshot, Interaction, Outcome


class SequenceAnalyzer:
    """Tool sequence analysis and optimization"""

    def __init__(
        self, interactions: Dict, sequence_patterns: Dict, tool_profiles: Dict
    ):
        self.interactions = interactions
        self.sequence_patterns = sequence_patterns
        self.tool_profiles = tool_profiles

    def analyze_granger_causality(self, interaction: Interaction) -> None:
        """Analyze tool sequences to find predictive patterns (simplified Granger)"""
        if not interaction.context.recent_tools:
            return

        last_tool = interaction.context.recent_tools[-1]
        current_tool = interaction.tool_name
        sequence = (last_tool, current_tool)

        # Initialize if sequence is new
        if sequence not in self.sequence_patterns:
            self.sequence_patterns[sequence] = {
                "successes": 0,
                "failures": 0,
                "total_count": 0,
            }

        # Update counts for the sequence
        pattern = self.sequence_patterns[sequence]
        pattern["total_count"] += 1
        if interaction.outcome == Outcome.SUCCESS:
            pattern["successes"] += 1
        else:
            pattern["failures"] += 1

    def detect_sequence_patterns(self, interaction_id: str) -> None:
        """Detect sequence patterns - enhanced implementation"""
        if interaction_id not in self.interactions:
            return

        interaction = self.interactions[interaction_id]
        if len(interaction.context.recent_tools) < 2:
            return

        # Look for longer sequence patterns (3+ tools)
        recent_tools = interaction.context.recent_tools[-3:]  # Last 3 tools
        if len(recent_tools) >= 2:
            # Check pairwise sequences
            for i in range(len(recent_tools) - 1):
                tool_pair = (recent_tools[i], recent_tools[i + 1])

                # Initialize pattern if new
                if tool_pair not in self.sequence_patterns:
                    self.sequence_patterns[tool_pair] = {
                        "successes": 0,
                        "failures": 0,
                        "total_count": 0,
                        "context_conditions": defaultdict(int),
                    }

                # Update pattern with current interaction outcome
                pattern = self.sequence_patterns[tool_pair]
                pattern["total_count"] += 1

                if interaction.outcome == Outcome.SUCCESS:
                    pattern["successes"] += 1
                else:
                    pattern["failures"] += 1

                # Add context conditions for more specific patterns
                context_key = f"complexity:{interaction.context.complexity.value}"
                pattern["context_conditions"][context_key] += 1

    def optimize_approach(
        self, current_plan: List[str], context: ContextSnapshot, goal: str
    ) -> Dict[str, Any]:
        """Optimize action plan based on learned patterns"""
        optimized_plan = current_plan.copy()
        optimizations = []

        # Sequence optimization
        for i in range(len(current_plan) - 1):
            tool_pair = (current_plan[i], current_plan[i + 1])
            if tool_pair in self.sequence_patterns:
                pattern = self.sequence_patterns[tool_pair]
                total = pattern.get("successes", 0) + pattern.get("failures", 0)
                if total > 0:
                    success_rate = pattern.get("successes", 0) / total
                    pattern["success_rate"] = success_rate

                    if success_rate < 0.3:
                        # Suggest alternative for problematic sequence
                        alternative = self._suggest_sequence_alternative(
                            tool_pair, context
                        )
                        if alternative:
                            optimized_plan[i + 1] = alternative
                            optimizations.append(
                                {
                                    "position": i + 1,
                                    "original": tool_pair[1],
                                    "replacement": alternative,
                                    "reason": f"Low success sequence: {success_rate:.1%}",
                                }
                            )

        # Tool substitution optimization
        for i, tool in enumerate(optimized_plan):
            if tool in self.tool_profiles:
                profile = self.tool_profiles[tool]
                if profile.success_rate < 0.4:
                    alternative = self._suggest_tool_alternative(tool, context, goal)
                    if alternative and alternative != tool:
                        optimized_plan[i] = alternative
                        optimizations.append(
                            {
                                "position": i,
                                "original": tool,
                                "replacement": alternative,
                                "reason": f"Low success tool: {profile.success_rate:.1%}",
                            }
                        )

        return {
            "optimized_plan": optimized_plan,
            "optimizations": optimizations,
            "confidence": self._calculate_optimization_confidence(optimizations),
        }

    def _suggest_sequence_alternative(
        self, problematic_sequence: Tuple[str, str], context: ContextSnapshot
    ) -> Optional[str]:
        """Suggest alternative for problematic sequence"""
        tool1, tool2 = problematic_sequence

        # Find alternative tools that work well with tool1
        alternatives = []

        # Look for sequences starting with tool1 that have high success rates
        for sequence, pattern in self.sequence_patterns.items():
            if sequence[0] == tool1 and sequence != problematic_sequence:
                total = pattern.get("successes", 0) + pattern.get("failures", 0)
                if total >= 3:
                    success_rate = pattern.get("successes", 0) / total
                    if success_rate > 0.7:  # High success rate
                        alternatives.append((sequence[1], success_rate))

        # Return the best alternative
        if alternatives:
            best_alternative = max(alternatives, key=lambda x: x[1])
            return best_alternative[0]

        return None

    def _suggest_tool_alternative(
        self, problematic_tool: str, context: ContextSnapshot, goal: str
    ) -> Optional[str]:
        """Suggest alternative tool for problematic tool"""
        # Find tools with similar purpose but better success rates
        candidates = []

        for tool_name, profile in self.tool_profiles.items():
            if tool_name != problematic_tool:
                # Simple relevance check (could be enhanced with semantic similarity)
                if self._tools_similar(problematic_tool, tool_name):
                    total_uses = sum(
                        1
                        for i in self.interactions.values()
                        if i.tool_name == tool_name
                    )
                    if total_uses >= 3 and profile.success_rate > 0.7:
                        candidates.append((tool_name, profile.success_rate))

        # Return best candidate
        if candidates:
            best_candidate = max(candidates, key=lambda x: x[1])
            return best_candidate[0]

        return None

    def _tools_similar(self, tool1: str, tool2: str) -> bool:
        """Check if two tools are similar in purpose"""
        # Simple heuristic based on tool names
        tool_categories = {
            "file_read": ["show_file", "read_file", "cat_file"],
            "file_write": ["create_file", "edit_file", "write_file"],
            "command": ["execute_command", "run_command", "exec"],
            "search": ["search_files", "find_files", "grep"],
            "list": ["list_files", "ls", "dir"],
        }

        for category, tools in tool_categories.items():
            if tool1 in tools and tool2 in tools:
                return True

        # Check for common substrings
        common_terms = ["file", "command", "search", "list", "edit"]
        for term in common_terms:
            if term in tool1.lower() and term in tool2.lower():
                return True

        return False

    def _calculate_optimization_confidence(self, optimizations: List[Dict]) -> float:
        """Calculate confidence in the optimizations"""
        if not optimizations:
            return 1.0  # No changes = high confidence in original plan

        # Confidence decreases with number of changes
        base_confidence = 0.8
        confidence_penalty = 0.1 * len(optimizations)

        return max(0.3, base_confidence - confidence_penalty)

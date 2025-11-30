"""
Foundation data classes and enums for pattern analysis
Blueprint 4: Statistical Self-Improvement (Patterns)
"""

import math
from enum import Enum

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

# Optional dependencies - fall back to basic implementations if not available
try:
    from scipy import stats

    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False


class Outcome(Enum):
    """Enumeration of possible tool execution outcomes"""

    SUCCESS = "success"
    FAILURE = "failure"
    PARTIAL_SUCCESS = "partial_success"
    TIMEOUT = "timeout"
    ERROR = "error"
    UNCLEAR = "unclear"


class ComplexityLevel(Enum):
    """Enumeration of task complexity levels"""

    SIMPLE = "simple"
    MODERATE = "moderate"
    COMPLEX = "complex"
    VERY_COMPLEX = "very_complex"


@dataclass
class ContextSnapshot:
    """Comprehensive context capture for pattern analysis"""

    conversation_length: int
    recent_tools: List[str]
    task_type: str
    complexity: ComplexityLevel
    user_expertise: str  # "beginner", "intermediate", "expert"
    time_of_day: str
    working_memory_usage: float  # 0.0-1.0
    emotional_tone: Optional[str] = None
    urgency_level: int = 1  # 1-5 scale


@dataclass
class Interaction:
    """Enhanced interaction recording with causal analysis"""

    id: str
    tool_name: str
    arguments: Dict[str, Any]
    outcome: Outcome
    execution_time: float
    timestamp: float
    context: ContextSnapshot
    error_message: Optional[str] = None
    result: Optional[Any] = None
    pre_conditions: Optional[Set[str]] = None
    post_conditions: Optional[Set[str]] = None
    confidence: float = 1.0
    retry_count: int = 0
    alternative_approaches_considered: Optional[List[str]] = None

    def to_dict(self) -> Dict:
        """Convert interaction to dictionary for serialization"""
        return asdict(self)


@dataclass
class ToolProfile:
    """Comprehensive tool performance profile"""

    name: str
    success_rate: float
    average_execution_time: float
    reliability_score: float
    context_preferences: Dict[str, float]  # context -> performance score
    common_failure_modes: Dict[str, float]  # failure type -> frequency
    prerequisite_sensitivity: float  # How sensitive to preconditions
    learning_curve: float  # How performance improves with use


@dataclass
class PredictiveRecommendation:
    """Predictive recommendation with risk assessment"""

    action: str
    reasoning: str
    confidence: float
    expected_success_probability: float
    expected_time_savings: float  # seconds
    risk_factors: List[Tuple[str, float]]  # risk -> probability
    prerequisites: List[str]
    fallback_strategies: List[str]
    similar_success_cases: List[str]  # IDs of similar successful interactions
    similar_failure_cases: List[str]  # IDs of similar failed interactions


def calculate_confidence_interval(
    successes: int, total: int, confidence: float = 0.95
) -> Tuple[float, float]:
    """
    Calculate Wilson score interval for binomial proportion

    Args:
        successes: Number of successful trials
        total: Total number of trials
        confidence: Confidence level (default 0.95 for 95% CI)

    Returns:
        Tuple of (lower_bound, upper_bound)
    """
    if total == 0:
        return (0.0, 1.0)

    if not SCIPY_AVAILABLE:
        # Simple fallback: use basic proportion with margin
        p = successes / total
        margin = 1.96 * math.sqrt(p * (1 - p) / total)  # 95% CI approximation
        return (max(0.0, p - margin), min(1.0, p + margin))

    # Wilson score interval (more accurate for small samples)
    z = stats.norm.ppf(1 - (1 - confidence) / 2)
    p = successes / total

    denominator = 1 + z**2 / total
    centre = (p + z**2 / (2 * total)) / denominator
    half_width = z * math.sqrt((p * (1 - p) + z**2 / (4 * total)) / total) / denominator

    return (centre - half_width, centre + half_width)

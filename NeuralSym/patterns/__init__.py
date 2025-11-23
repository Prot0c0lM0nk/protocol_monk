"""
Pattern analysis module for statistical self-improvement
Blueprint 4: Statistical Self-Improvement (Patterns)

This module learns from tool interaction history to predict success probabilities,
recommend optimal approaches, and warn about potential failures.
"""

from .base import (
    Outcome,
    ComplexityLevel,
    ContextSnapshot,
    Interaction,
    ToolProfile,
    PredictiveRecommendation,
    calculate_confidence_interval
)

from .analyzer import AdvancedPatternAnalyzer

__all__ = [
    "Outcome",
    "ComplexityLevel",
    "ContextSnapshot",
    "Interaction",
    "ToolProfile",
    "PredictiveRecommendation",
    "calculate_confidence_interval",
    "AdvancedPatternAnalyzer"
]

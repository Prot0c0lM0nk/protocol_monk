"""Observation helpers for NeuralSym."""

from __future__ import annotations

from .models import Observation


def sort_parameter_keys(parameters: dict[str, object] | None) -> list[str]:
    """Normalize structured parameter keys for observation payloads."""

    if not parameters:
        return []
    return sorted(str(key) for key in parameters.keys())


def observation_ids(observations: list[Observation]) -> list[str]:
    """Collect observation IDs from a batch."""

    return [observation.id for observation in observations]

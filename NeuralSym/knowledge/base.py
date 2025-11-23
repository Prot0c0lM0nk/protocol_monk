"""
Core data models for the knowledge graph.

Defines Fact, Evidence, ActionPlan and their supporting enums.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, asdict, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set


class FactStatus(Enum):
    """Status of a fact in the knowledge graph."""
    VERIFIED = "verified"
    ASSUMED = "assumed"
    REFUTED = "refuted"
    UNCERTAIN = "uncertain"


class EvidenceStrength(Enum):
    """Strength of evidence supporting a fact."""
    WEAK = 0.3
    MODERATE = 0.7
    STRONG = 0.9
    CONCLUSIVE = 1.0


@dataclass
class Evidence:
    """Evidence supporting or refuting a fact."""
    id: str
    source: str
    content: str
    timestamp: float
    strength: EvidenceStrength
    tool_used: Optional[str] = None
    tool_args: Optional[Dict[str, Any]] = None
    tool_result: Optional[Any] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize Evidence to dictionary."""
        data = asdict(self)
        # Convert enum to its name for JSON serialization
        data['strength'] = self.strength.name
        return data

    @classmethod
    def new(
        cls,
        source: str,
        content: str,
        strength: EvidenceStrength = EvidenceStrength.MODERATE,
        tool_used: Optional[str] = None,
        tool_args: Optional[Dict[str, Any]] = None,
        tool_result: Optional[Any] = None,
    ) -> Evidence:
        """Factory helper to create Evidence with auto-generated ID and timestamp."""
        return cls(
            id=str(uuid.uuid4()),
            source=source,
            content=content,
            timestamp=time.time(),
            strength=strength,
            tool_used=tool_used,
            tool_args=tool_args,
            tool_result=tool_result,
        )

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Evidence:
        """Deserialize Evidence from dictionary."""
        # Convert strength string back to enum
        strength = data.get("strength")
        if isinstance(strength, str):
            strength = EvidenceStrength[strength]  # Direct lookup by name
        elif isinstance(strength, (int, float)):
            # Backward compatibility: match by value for old data
            for es in EvidenceStrength:
                if es.value == strength:
                    strength = es
                    break
        elif strength is None:
            strength = EvidenceStrength.MODERATE  # Default fallback

        return cls(
            id=data["id"],
            source=data["source"],
            content=data["content"],
            timestamp=data["timestamp"],
            strength=strength,
            tool_used=data.get("tool_used"),
            tool_args=data.get("tool_args"),
            tool_result=data.get("tool_result"),
        )


@dataclass
class Fact:
    """Enhanced fact with evidence chain and relationships."""
    id: str
    fact_type: str
    value: Any
    status: FactStatus
    confidence: float
    created_at: float
    updated_at: float
    evidences: List[Evidence]
    depends_on: List[str] = field(default_factory=list)
    required_for: List[str] = field(default_factory=list)
    context_tags: Set[str] = field(default_factory=set)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize Fact to dictionary."""
        # Manually serialize to ensure proper enum handling
        return {
            'id': self.id,
            'fact_type': self.fact_type,
            'value': self.value,
            'status': self.status.name,  # Serialize enum as name
            'confidence': self.confidence,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
            'evidences': [ev.to_dict() for ev in self.evidences],  # Use Evidence.to_dict()
            'depends_on': self.depends_on,
            'required_for': self.required_for,
            'context_tags': list(self.context_tags),  # Convert set to list
        }

    @classmethod
    def new(
        cls,
        fact_type: str,
        value: Any,
        evidence: Evidence,
        status: FactStatus = FactStatus.VERIFIED,
        context_tags: Optional[Set[str]] = None,
        depends_on: Optional[List[str]] = None,
    ) -> Fact:
        """Factory helper to create Fact with auto-generated ID and timestamps."""
        return cls(
            id=str(uuid.uuid4()),
            fact_type=fact_type,
            value=value,
            status=status,
            confidence=evidence.strength.value,
            created_at=time.time(),
            updated_at=time.time(),
            evidences=[evidence],
            depends_on=depends_on or [],
            required_for=[],
            context_tags=context_tags or set(),
        )

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Fact:
        """Deserialize Fact from dictionary."""
        # Convert status string back to enum
        status = data.get("status")
        if isinstance(status, str):
            # Try value first (lowercase like "verified"), then name (uppercase like "VERIFIED")
            try:
                status = FactStatus(status.lower())
            except ValueError:
                status = FactStatus[status.upper()]

        # Convert evidences list back to Evidence objects
        evidences = [Evidence.from_dict(ev) for ev in data.get("evidences", [])]

        # Convert context_tags back to set
        context_tags = data.get("context_tags", [])
        if isinstance(context_tags, list):
            context_tags = set(context_tags)

        return cls(
            id=data["id"],
            fact_type=data["fact_type"],
            value=data["value"],
            status=status,
            confidence=data["confidence"],
            created_at=data["created_at"],
            updated_at=data["updated_at"],
            evidences=evidences,
            depends_on=data.get("depends_on", []),
            required_for=data.get("required_for", []),
            context_tags=context_tags,
        )


@dataclass
class ActionPlan:
    """Plan derived from knowledge state."""
    goal: str
    required_facts: List[str]
    missing_facts: List[str]
    confidence: float
    reasoning: str
    suggested_tools: List[str]

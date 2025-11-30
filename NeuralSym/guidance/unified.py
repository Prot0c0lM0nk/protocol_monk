from dataclasses import dataclass
import re
from typing import Dict, List, Tuple, Literal, Optional
from pathlib import Path
import logging


@dataclass
class ModelProfile:
    name: str
    max_facts: int
    max_risks: int
    guidance_style: Literal["direct", "structured", "verbose"]


class UnifiedGuidanceSystem:
    def __init__(self, kg, patterns):
        self.kg = kg
        self.patterns = patterns
        self.PROFILES = {
            "basic": ModelProfile(
                name="basic", max_facts=2, max_risks=2, guidance_style="direct"
            ),
            "standard": ModelProfile(
                name="standard", max_facts=5, max_risks=5, guidance_style="structured"
            ),
            "advanced": ModelProfile(
                name="advanced", max_facts=10, max_risks=10, guidance_style="verbose"
            ),
        }

    def _resolve_profile(self, model_name: str) -> ModelProfile:
        model_name = model_name.lower()
        if re.search(r"\b[1-3]b\b", model_name):
            return self.PROFILES["basic"]
        elif re.search(r"\b([7-9]|1[0-2])b\b", model_name):
            return self.PROFILES["standard"]
        else:
            return self.PROFILES["advanced"]

    def get_guidance(
        self, intent: str, context_tags: set, model_name: str = "large"
    ) -> Tuple[str, Dict]:
        profile = self._resolve_profile(model_name)
        risks = self.patterns.identify_common_mistakes(intent)
        facts_dict = self.kg.get_relevant_context(intent)
        risks = risks[: profile.max_risks]
        # Convert facts_dict to a list of strings for slicing
        facts_list = []
        if facts_dict.get("current_state"):
            for fact_type, value in facts_dict["current_state"].items():
                facts_list.append(f"{fact_type}: {value}")
        if facts_dict.get("verified_assumptions"):
            for fact in facts_dict["verified_assumptions"]:
                facts_list.append(f"{fact['type']}: {fact['value']}")
        if facts_dict.get("potential_issues"):
            for issue in facts_dict["potential_issues"]:
                facts_list.append(issue["warning"])
        facts = facts_list[: profile.max_facts]
        formatted = self._format_guidance(
            intent, risks, facts, profile.guidance_style, model_name
        )
        return formatted, {
            "model": model_name,
            "profile": profile.name,
            "risks": len(risks),
            "facts": len(facts),
        }

    def _format_guidance(self, intent, risks, facts, style, model_name) -> str:
        if style == "direct":
            return f"CRITICAL: Avoid {', '.join(risks)}. Do {', '.join(facts)}."
        elif style == "structured":
            return f"Context: {intent}\nRisks: {', '.join(risks)}\nPlan: {', '.join(facts)}"
        else:  # "verbose"
            return f"Model: {model_name}\nContext: {intent}\nRisks: {', '.join(risks)}\nPlan: {', '.join(facts)}"


# For testing/debugging
if __name__ == "__main__":
    pass

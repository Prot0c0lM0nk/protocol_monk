"""
guidance.py
The 'Pre-frontal Cortex' that decides how to instruct the LLM
based on data from the Knowledge Graph and Pattern Analyzer.
"""

import time
from typing import Dict, Tuple, List


class GuidanceSystem:
    def __init__(self, knowledge_graph, pattern_analyzer):
        self.kg = knowledge_graph
        self.patterns = pattern_analyzer
        # Store recent decision traces for the dashboard
        self.decision_log = []

    def get_guidance(self, intent: str, context_tags: set) -> Tuple[str, Dict]:
        """
        Returns:
            1. The prompt string to inject into the LLM.
            2. The 'trace' dict explaining the decision logic.
        """
        start_time = time.time()
        trace = {
            "timestamp": start_time,
            "intent": intent,
            "inputs": {},
            "logic_path": [],
            "final_output": "",
        }

        # --- STEP 1: GATHER INTELLIGENCE ---

        # A. Ask Pattern Analyzer for High-Level Risks (Intent-based)
        risks = self.patterns.identify_common_mistakes(intent)

        # Also check specifically if we have Refuted facts in the KG for this intent
        # (This bridges the gap if the Pattern Analyzer hasn't synced yet)
        relevant_context = self.kg.get_relevant_context(intent)
        for failure in relevant_context.get("known_failures", []):
            risks.append(f"Avoid {failure['tool']}: {failure['reason']}")

        trace["inputs"]["risks"] = risks

        # B. Ask Pattern Analyzer for Successes (Opportunity)
        recommendations = self.patterns.predict_best_approach(intent, {})
        trace["inputs"]["recommendations"] = recommendations

        # C. Ask Knowledge Graph for Hard Facts (Constraints)
        # e.g., "File does not exist" is a hard constraint
        context_facts = self.kg.get_relevant_context(intent)
        trace["inputs"]["facts"] = context_facts

        # --- STEP 2: THE DECISION LOGIC (Your Playground) ---

        guidance_lines = ["\n### 🧠 SYSTEM GUIDANCE"]

        # Logic Rule 1: Safety First
        # If we have high-confidence risks, they define the prompt.
        if risks:
            trace["logic_path"].append("Risk Detected -> Enforcing Constraints")
            guidance_lines.append("!!! CRITICAL WARNINGS (PAST FAILURES) !!!")
            for risk in risks:
                guidance_lines.append(f"🚫 {risk}")
        else:
            trace["logic_path"].append("No Immediate Risks -> Checking Optimizations")

        # Logic Rule 2: Optimization Second
        # If safe, suggest the most efficient path.
        if recommendations and not risks:
            trace["logic_path"].append("Pattern Found -> Suggesting Optimization")
            guidance_lines.append("\n✅ RECOMMENDED STRATEGY:")
            for rec in recommendations[:2]:
                guidance_lines.append(f"- {rec}")

        # Logic Rule 3: Fact Injection
        # Always explicitly state verified facts to prevent hallucination
        if context_facts.get("verified_assumptions"):
            guidance_lines.append("\n[VERIFIED CONTEXT]")
            for fact in context_facts["verified_assumptions"]:
                guidance_lines.append(f"✓ {fact['type']}: {fact['value']}")

        guidance_lines.append("### END GUIDANCE\n")

        # --- STEP 3: FINALIZE ---
        final_prompt = "\n".join(guidance_lines)
        trace["final_output"] = final_prompt

        # Keep log size manageable (last 50 decisions)
        self.decision_log.append(trace)
        if len(self.decision_log) > 50:
            self.decision_log.pop(0)

        return final_prompt, trace

    def get_small_model_guidance(
        self, intent: str, context_tags: set
    ) -> Tuple[str, Dict]:
        """
        Generate optimized guidance for small models (8B).
        Returns structured, concise prompts suitable for small models.
        """
        start_time = time.time()
        trace = {
            "timestamp": start_time,
            "intent": intent,
            "model_type": "8b",
            "inputs": {},
            "logic_path": [],
            "final_output": "",
        }

        # Gather intelligence with focus on critical constraints
        risks = self.patterns.identify_common_mistakes(intent)
        relevant_context = self.kg.get_relevant_context(intent)

        # Add refuted facts as critical constraints
        for failure in relevant_context.get("known_failures", []):
            risks.append(f"{failure['tool']}: {failure['reason']}")

        trace["inputs"]["risks"] = risks[:3]  # Limit to top 3 for small models

        # Get recommendations
        recommendations = self.patterns.predict_best_approach(intent, {})
        trace["inputs"]["recommendations"] = recommendations[
            :2
        ]  # Limit for small models

        # Get verified facts
        context_facts = self.kg.get_relevant_context(intent)
        verified_assumptions = context_facts.get("verified_assumptions", [])
        trace["inputs"]["facts"] = verified_assumptions[:3]  # Limit for small models

        # Generate concise, structured guidance
        guidance_lines = [f"TASK: {intent}"]

        # Critical constraints (most important for small models)
        if risks:
            trace["logic_path"].append("Risk Detected -> Enforcing Constraints")
            guidance_lines.append("\nCRITICAL CONSTRAINTS:")
            for risk in risks[:3]:  # Only top 3 for small models
                guidance_lines.append(f"- AVOID: {risk}")

        # Recommended approach
        if recommendations:
            trace["logic_path"].append("Pattern Found -> Suggesting Optimization")
            guidance_lines.append("\nRECOMMENDED STEPS:")
            for i, rec in enumerate(recommendations[:2], 1):  # Only top 2
                guidance_lines.append(f"{i}. {rec}")

        # Verified facts
        if verified_assumptions:
            guidance_lines.append("\nVERIFIED CONTEXT:")
            for fact in verified_assumptions[:3]:  # Only top 3
                if isinstance(fact, dict):
                    fact_type = fact.get("type", "fact")
                    fact_value = fact.get("value", "")
                    guidance_lines.append(f"- {fact_type}: {fact_value}")
                else:
                    guidance_lines.append(f"- {fact}")

        final_prompt = "\n".join(guidance_lines)
        trace["final_output"] = final_prompt

        # Keep log size manageable
        self.decision_log.append(trace)
        if len(self.decision_log) > 50:
            self.decision_log.pop(0)

        return final_prompt, trace

    def get_structured_context(self, intent: str, max_items: int = 5) -> Dict:
        """
        Get structured context optimized for small models.
        Returns a simplified context view with prioritized information.
        """
        context = self.kg.get_relevant_context(intent)

        # Extract and prioritize critical information
        structured = {
            "constraints": [],
            "recommendations": [],
            "facts": [],
            "intent": intent,
        }

        # Critical constraints (from known failures)
        known_failures = context.get("known_failures", [])
        for failure in known_failures[:max_items]:
            structured["constraints"].append(
                {
                    "type": "avoid",
                    "tool": failure.get("tool", "unknown"),
                    "reason": failure.get("reason", "unknown reason"),
                    "priority": "high",
                }
            )

        # Verified facts
        verified_assumptions = context.get("verified_assumptions", [])
        for fact in verified_assumptions[:max_items]:
            structured["facts"].append(
                {
                    "type": fact.get("type", "fact"),
                    "value": fact.get("value", ""),
                    "priority": "medium",
                }
            )

        return structured

    def get_critical_constraints(
        self, intent: str, max_constraints: int = 3
    ) -> List[str]:
        """
        Get the most critical constraints for a given intent.
        Prioritizes verified failures and high-risk patterns.
        """
        constraints = []

        # Get known failures from knowledge graph
        context = self.kg.get_relevant_context(intent)
        known_failures = context.get("known_failures", [])

        # Format failures as constraints
        for failure in known_failures[:max_constraints]:
            constraints.append(
                f"{failure.get('tool', 'unknown tool')}: {failure.get('reason', 'unknown reason')}"
            )

        # Add pattern-based constraints
        pattern_constraints = self.patterns.identify_common_mistakes(intent)
        for constraint in pattern_constraints[: max_constraints - len(constraints)]:
            if constraint not in constraints:
                constraints.append(constraint)

        return constraints[:max_constraints]

    def get_verification_checklist(self, intent: str, max_items: int = 5) -> List[str]:
        """
        Generate a verification checklist for validating results.
        Useful for small models that may need explicit validation steps.
        """
        checklist = []

        # Get context for this intent
        context = self.kg.get_relevant_context(intent)

        # Add verification items based on context
        verified_facts = context.get("verified_assumptions", [])
        for fact in verified_facts[:max_items]:
            fact_type = fact.get("type", "fact")
            fact_value = fact.get("value", "")
            checklist.append(f"Verify {fact_type}: {fact_value}")

        # Add pattern-based verification items
        # Since there's no get_verification_patterns method, we'll use common mistakes
        # but phrase them as verification checks
        pattern_constraints = self.patterns.identify_common_mistakes(intent)
        for constraint in pattern_constraints[: max_items - len(checklist)]:
            # Convert constraint to verification check
            constraint_cleaned = (
                constraint.replace("Avoid", "")
                .replace("avoid", "")
                .replace("Don't", "")
                .replace("don't", "")
                .strip()
            )
            if "avoid" in constraint.lower() or "don't" in constraint.lower():
                checklist.append(f"Verify that you {constraint_cleaned}")
            else:
                checklist.append(f"Verify that you avoid: {constraint}")

        # Add generic verification items if needed
        if not checklist:
            checklist.extend(
                [
                    "Verify output format matches requirements",
                    "Check for syntax errors",
                    "Confirm file paths exist if referenced",
                    "Validate tool parameters are correct",
                ]
            )

        return checklist[:max_items]

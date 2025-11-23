"""
small_model_guidance.py
Enhanced guidance system specifically optimized for small LLMs (8B models)
"""

from typing import Dict, Tuple, List
import time

# Local imports
import guidance_templates
from guidance_templates import (
    SMALL_MODEL_TEMPLATES, 
    format_risks_for_small_models,
    format_recommendations_for_small_models,
    format_facts_for_small_models
)


class SmallModelGuidanceSystem:
    def __init__(self, knowledge_graph, pattern_analyzer):
        self.kg = knowledge_graph
        self.patterns = pattern_analyzer
        self.decision_log = []
    
    def get_guidance(self, intent: str, context_tags: set) -> Tuple[str, Dict]:
        """
        Generate optimized guidance for small models
        """
        import time
        start_time = time.time()
        
        trace = {
            "timestamp": start_time,
            "intent": intent,
            "inputs": {},
            "logic_path": [],
            "final_output": ""
        }
        
        # Gather intelligence
        risks = self.patterns.identify_common_mistakes(intent)
        relevant_context = self.kg.get_relevant_context(intent)
        
        # Add refuted facts as risks
        for failure in relevant_context.get("known_failures", []):
            risks.append(f"{failure['tool']}: {failure['reason']}")
        
        trace["inputs"]["risks"] = risks
        
        # Get recommendations
        recommendations = self.patterns.predict_best_approach(intent, {})
        trace["inputs"]["recommendations"] = recommendations
        
        # Get verified facts
        context_facts = self.kg.get_relevant_context(intent)
        trace["inputs"]["facts"] = context_facts
        
        # Generate structured guidance
        guidance = self._generate_structured_guidance(
            intent, risks, recommendations, context_facts
        )
        
        trace["final_output"] = guidance
        
        # Maintain decision log
        self.decision_log.append(trace)
        if len(self.decision_log) > 50:
            self.decision_log.pop(0)
            
        return guidance, trace
    
    def _generate_structured_guidance(
        self, 
        intent: str, 
        risks: List[str], 
        recommendations: List[str], 
        context_facts: Dict
    ) -> str:
        """
        Generate structured guidance optimized for small models
        """
        # Format components for small models
        risks_formatted = format_risks_for_small_models(risks)
        recommendations_formatted = format_recommendations_for_small_models(recommendations)
        
        verified_assumptions = context_facts.get("verified_assumptions", [])
        facts_formatted = format_facts_for_small_models(verified_assumptions)
        
        # Use the structured template
        guidance = SMALL_MODEL_TEMPLATES["structured_guidance"].format(
            intent=intent,
            risks_formatted=risks_formatted,
            recommendations_formatted=recommendations_formatted,
            facts_formatted=facts_formatted
        )
        
        return guidance.strip()
    
    def get_adaptive_guidance(self, intent: str, context_tags: set, model_capability: str = "basic") -> Tuple[str, Dict]:
        """
        Generate guidance that adapts based on model capability
        """
        guidance, trace = self.get_guidance(intent, context_tags)
        
        # For basic models, simplify even further
        if model_capability == "basic":
            # Extract only the most critical information
            simplified = self._simplify_for_basic_model(trace)
            trace["final_output"] = simplified
            return simplified, trace
        
        return guidance, trace
    
    def _simplify_for_basic_model(self, trace: Dict) -> str:
        """
        Simplify guidance for the most basic models
        """
        inputs = trace.get("inputs", {})
        risks = inputs.get("risks", [])
        recommendations = inputs.get("recommendations", [])
        
        lines = ["CRITICAL GUIDANCE FOR NEXT STEP:"]
        
        # Critical constraints
        if risks:
            lines.append("\nAVOID THESE MISTAKES:")
            for risk in risks[:2]:  # Only top 2 risks
                lines.append(f"- {risk}")
        
        # Primary recommendation
        if recommendations:
            lines.append("\nRECOMMENDED ACTION:")
            lines.append(f"- {recommendations[0]}")
            
        return "\n".join(lines)
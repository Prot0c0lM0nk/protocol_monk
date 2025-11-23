"""
integrated_small_model_guidance.py
Fully integrated guidance system for small LLMs
"""

from typing import Dict, Tuple, List
import time

from small_model_knowledge import SmallModelKnowledgeInterface
from small_model_patterns import SmallModelPatternAnalyzer
from small_model_guidance import SmallModelGuidanceSystem


class IntegratedSmallModelGuidance:
    def __init__(self, knowledge_graph, pattern_analyzer):
        self.kg = knowledge_graph
        self.patterns = pattern_analyzer
        
        # Initialize specialized interfaces
        self.knowledge_interface = SmallModelKnowledgeInterface(knowledge_graph)
        self.pattern_interface = SmallModelPatternAnalyzer(pattern_analyzer)
        self.guidance_system = SmallModelGuidanceSystem(knowledge_graph, pattern_analyzer)
        
        self.decision_log = []
    
    def get_guidance(self, intent: str, context_tags: set, model_type: str = "8b_standard") -> Tuple[str, Dict]:
        """
        Get fully integrated guidance optimized for small models
        """
        start_time = time.time()
        
        trace = {
            "timestamp": start_time,
            "intent": intent,
            "model_type": model_type,
            "inputs": {},
            "logic_path": [],
            "final_output": ""
        }
        
        # Get model capability profile
        capability_profile = self.pattern_interface.get_model_capability_profile(model_type)
        trace["capability_profile"] = capability_profile
        
        # Gather critical intelligence
        critical_constraints = self.knowledge_interface.get_critical_constraints(intent)
        critical_facts = self.knowledge_interface.get_critical_facts(intent)
        simplified_recommendations = self.pattern_interface.get_simplified_recommendations(intent, {})
        
        trace["inputs"] = {
            "constraints": critical_constraints,
            "facts": critical_facts,
            "recommendations": simplified_recommendations
        }
        
        # Generate step-by-step guidance
        step_by_step = self.pattern_interface.get_step_by_step_guidance(intent, {})
        trace["step_by_step"] = step_by_step
        
        # Generate final guidance
        guidance = self._generate_integrated_guidance(
            intent, 
            critical_constraints, 
            critical_facts, 
            simplified_recommendations,
            step_by_step,
            capability_profile
        )
        
        trace["final_output"] = guidance
        trace["logic_path"].append("Generated integrated small model guidance")
        
        # Maintain decision log
        self.decision_log.append(trace)
        if len(self.decision_log) > 50:
            self.decision_log.pop(0)
            
        return guidance, trace
    
    def _generate_integrated_guidance(
        self,
        intent: str,
        constraints: List[str],
        facts: List[Dict],
        recommendations: List[str],
        step_by_step: List[str],
        capability_profile: Dict
    ) -> str:
        """
        Generate integrated guidance based on capability profile
        """
        guidance_style = capability_profile.get("guidance_style", "structured")
        
        if guidance_style == "direct":
            # Very simple, direct guidance
            lines = [f"TASK: {intent}"]
            
            if constraints:
                lines.append("\nCRITICAL CONSTRAINTS:")
                for constraint in constraints[:capability_profile["risk_count"]]:
                    lines.append(f"- {constraint}")
            
            if recommendations:
                lines.append("\nRECOMMENDED ACTION:")
                lines.append(f"- {recommendations[0]}")
                
            return "\n".join(lines)
            
        elif guidance_style == "structured":
            # Structured but concise guidance
            lines = [f"=== GUIDANCE FOR: {intent} ==="]
            
            if constraints:
                lines.append("\n🔴 MUST AVOID:")
                for constraint in constraints[:capability_profile["risk_count"]]:
                    lines.append(f"  • {constraint}")
            
            if recommendations:
                lines.append("\n🟢 RECOMMENDED:")
                for i, rec in enumerate(recommendations[:capability_profile["recommendation_count"]], 1):
                    lines.append(f"  {i}. {rec}")
                    
            if facts:
                lines.append("\n✅ VERIFIED FACTS:")
                for fact in facts[:3]:
                    lines.append(f"  • {fact['type']}: {fact['value']}")
                    
            if step_by_step:
                lines.append("\n📋 STEP-BY-STEP:")
                for step in step_by_step[:5]:  # Limit steps
                    lines.append(f"  {step}")
                    
            lines.append("\n=== END GUIDANCE ===")
            return "\n".join(lines)
            
        else:  # detailed
            # More detailed guidance
            return self.guidance_system.get_guidance(intent, set())[0]
    
    def get_verification_guidance(self, intent: str) -> str:
        """
        Get verification guidance for checking results
        """
        checklist = self.knowledge_interface.get_verification_checklist(intent)
        
        lines = ["=== VERIFICATION CHECKLIST ==="]
        for i, item in enumerate(checklist, 1):
            lines.append(f"{i}. {item}")
        lines.append("=== END CHECKLIST ===")
        
        return "\n".join(lines)
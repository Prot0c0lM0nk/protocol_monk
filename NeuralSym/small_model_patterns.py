"""
small_model_patterns.py
Enhanced pattern recognition optimized for small LLMs
"""

from typing import Dict, List, Tuple
from collections import defaultdict


class SmallModelPatternAnalyzer:
    def __init__(self, base_analyzer):
        self.base_analyzer = base_analyzer
        
    def get_simplified_recommendations(self, intent: str, context: Dict) -> List[str]:
        """
        Get simplified recommendations optimized for small models
        """
        # Get base recommendations
        base_recs = self.base_analyzer.predictor.predict_best_approach(intent, context)
        
        # Simplify for small models
        simplified = []
        for rec in base_recs[:2]:  # Only top 2 recommendations
            if "success rate" in rec:
                # Extract just the tool name and success rate
                parts = rec.split(":")
                if len(parts) >= 2:
                    tool_name = parts[0].strip()
                    success_info = parts[1].split("success rate")[0].strip()
                    simplified.append(f"Use {tool_name} ({success_info})")
                else:
                    simplified.append(rec)
            else:
                simplified.append(rec)
                
        return simplified
    
    def get_critical_risks(self, intent: str) -> List[str]:
        """
        Get only the most critical risks for small models
        """
        # Get all risks
        all_risks = self.base_analyzer.predictor.identify_common_mistakes(intent)
        
        # Filter to only critical/high-frequency risks
        critical_risks = []
        for risk in all_risks:
            # Look for high failure rates or critical error types
            if "100%" in risk or "memory" in risk.lower() or "permission" in risk.lower():
                critical_risks.append(risk)
                
        return critical_risks[:2]  # Only top 2 critical risks
    
    def get_step_by_step_guidance(self, intent: str, context: Dict) -> List[str]:
        """
        Generate step-by-step guidance for small models
        """
        steps = []
        
        # 1. Check for critical risks
        critical_risks = self.get_critical_risks(intent)
        if critical_risks:
            steps.append("FIRST: AVOID THESE CRITICAL MISTAKES")
            for risk in critical_risks:
                steps.append(f"  - {risk}")
        
        # 2. Get recommended approach
        recommendations = self.get_simplified_recommendations(intent, context)
        if recommendations:
            steps.append("THEN: FOLLOW THIS APPROACH")
            for i, rec in enumerate(recommendations, 1):
                steps.append(f"  {i}. {rec}")
                
        # 3. Add verification step
        steps.append("FINALLY: VERIFY YOUR RESULTS")
        steps.append("  - Check that the output matches your expectations")
        
        return steps
    
    def get_model_capability_profile(self, model_type: str) -> Dict:
        """
        Get capability profile for different model types
        """
        profiles = {
            "8b_basic": {
                "max_context_length": 4096,
                "complexity_limit": "low",
                "guidance_style": "direct",
                "recommendation_count": 1,
                "risk_count": 2
            },
            "8b_standard": {
                "max_context_length": 8192,
                "complexity_limit": "medium",
                "guidance_style": "structured",
                "recommendation_count": 2,
                "risk_count": 3
            },
            "8b_advanced": {
                "max_context_length": 16384,
                "complexity_limit": "high",
                "guidance_style": "detailed",
                "recommendation_count": 3,
                "risk_count": 5
            }
        }
        
        return profiles.get(model_type, profiles["8b_standard"])
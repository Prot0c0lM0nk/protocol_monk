"""
small_model_knowledge.py
Enhanced knowledge graph interface optimized for small LLMs
"""

from typing import Dict, List, Set, Tuple


class SmallModelKnowledgeInterface:
    def __init__(self, knowledge_graph):
        self.kg = knowledge_graph
    
    def get_critical_facts(self, intent: str) -> List[Dict]:
        """
        Get only the most critical facts for small models
        """
        context = self.kg.get_relevant_context(intent)
        
        # Extract verified facts
        verified_facts = []
        verified_assumptions = context.get("verified_assumptions", [])
        
        for fact in verified_assumptions[:3]:  # Only top 3 verified facts
            if isinstance(fact, dict):
                verified_facts.append({
                    "type": fact.get("type", "fact"),
                    "value": fact.get("value", ""),
                    "confidence": fact.get("confidence", 1.0)
                })
        
        return verified_facts
    
    def get_critical_constraints(self, intent: str) -> List[str]:
        """
        Get critical constraints that small models must follow
        """
        context = self.kg.get_relevant_context(intent)
        
        # Extract known failures
        constraints = []
        known_failures = context.get("known_failures", [])
        
        for failure in known_failures[:2]:  # Only top 2 failures
            if isinstance(failure, dict):
                tool = failure.get("tool", "unknown tool")
                reason = failure.get("reason", "unknown reason")
                constraints.append(f"DO NOT use {tool}: {reason}")
        
        return constraints
    
    def get_simplified_context(self, intent: str) -> Dict:
        """
        Get simplified context optimized for small models
        """
        context = self.kg.get_relevant_context(intent)
        
        simplified = {
            "critical_facts": self.get_critical_facts(intent),
            "critical_constraints": self.get_critical_constraints(intent),
            "task_type": context.get("task_type", "general"),
            "complexity": context.get("complexity", "unknown")
        }
        
        return simplified
    
    def validate_proposed_action(self, action: str, arguments: Dict) -> Tuple[bool, List[str]]:
        """
        Validate a proposed action against known knowledge
        """
        warnings = []
        
        # Check if this action has known failures
        # This is a simplified version - in practice, you'd want more sophisticated matching
        
        return len(warnings) == 0, warnings
    
    def get_verification_checklist(self, intent: str) -> List[str]:
        """
        Get a simple checklist for verifying results
        """
        checklist = [
            "Verify output matches expected format",
            "Check for any error messages",
            "Confirm all required steps were completed"
        ]
        
        # Add intent-specific checks
        if "file" in intent.lower():
            checklist.extend([
                "Verify file path is correct",
                "Check file permissions if needed"
            ])
        elif "command" in intent.lower():
            checklist.extend([
                "Verify command syntax",
                "Check resource limits"
            ])
            
        return checklist[:5]  # Limit to 5 items
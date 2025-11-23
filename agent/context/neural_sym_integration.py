"""
neural_sym_integration.py
Integration of NeuralSym guidance system with the agent context manager
"""

import asyncio
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Import NeuralSym components
try:
    from NeuralSym.knowledge.graph import KnowledgeGraph
    from NeuralSym.patterns.analyzer import AdvancedPatternAnalyzer
    from NeuralSym.guidance import GuidanceSystem
    NEURALSYM_AVAILABLE = True
except ImportError:
    NEURALSYM_AVAILABLE = False
    logging.warning("NeuralSym components not available. Guidance features will be disabled.")


class NeuralSymContextManager:
    """
    Enhanced context manager that integrates NeuralSym guidance system.
    Provides small model optimized guidance for LLM interactions.
    """
    
    def __init__(self, working_dir: Path = None):
        self.working_dir = working_dir or Path.cwd()
        self.logger = logging.getLogger(__name__)
        
        if NEURALSYM_AVAILABLE:
            try:
                # Initialize NeuralSym components
                self.kg = KnowledgeGraph(persistence_path=self.working_dir / ".neuralsym" / "knowledge.json")
                self.patterns = AdvancedPatternAnalyzer(persistence_path=self.working_dir / ".neuralsym" / "patterns.json")
                self.guidance_system = GuidanceSystem(self.kg, self.patterns)
                
                # Wire telemetry for learning
                self.kg.telemetry_callback = self.patterns.on_knowledge_event
                
                # Ensure the directory exists
                (self.working_dir / ".neuralsym").mkdir(exist_ok=True)
                
                self.logger.info("NeuralSym guidance system initialized successfully")
            except Exception as e:
                self.logger.error(f"Failed to initialize NeuralSym guidance system: {e}")
                self.guidance_system = None
        else:
            self.guidance_system = None
    
    def get_guidance_for_intent(self, intent: str, context_tags: set, model_size: str = "large") -> Tuple[str, Dict]:
        """
        Get guidance for a specific intent, optimized for model size.
        
        Args:
            intent: The intent or task to get guidance for
            context_tags: Context tags to help guide the analysis
            model_size: Size of the model ("large", "8b_standard", "8b_basic")
        
        Returns:
            Tuple of (guidance_text, trace_dict)
        """
        if not self.guidance_system:
            return "", {}
        
        # For small models, use the optimized guidance methods
        if model_size.startswith("8b"):
            return self.guidance_system.get_small_model_guidance(intent, context_tags)
        else:
            # For large models, use standard guidance
            return self.guidance_system.get_guidance(intent, context_tags)
    
    def get_structured_context_for_model(self, intent: str, model_size: str = "large") -> Dict:
        """
        Get structured context optimized for the model size.
        """
        if not self.guidance_system or not hasattr(self.guidance_system, 'get_structured_context'):
            return {}
        
        return self.guidance_system.get_structured_context(intent)
    
    def get_critical_constraints_for_model(self, intent: str, model_size: str = "large") -> List[str]:
        """
        Get critical constraints optimized for the model size.
        """
        if not self.guidance_system or not hasattr(self.guidance_system, 'get_critical_constraints'):
            return []
        
        return self.guidance_system.get_critical_constraints(intent)
    
    def get_verification_checklist_for_model(self, intent: str, model_size: str = "large") -> List[str]:
        """
        Get verification checklist optimized for the model size.
        """
        if not self.guidance_system or not hasattr(self.guidance_system, 'get_verification_checklist'):
            return []
        
        return self.guidance_system.get_verification_checklist(intent)
    
    def record_interaction_outcome(self, tool_name: str, arguments: Dict, success: bool, 
                                 error_message: str = None, context_summary: str = None):
        """
        Record the outcome of a tool interaction for learning.
        """
        if not self.guidance_system:
            return
        
        try:
            if success:
                # Record success
                from NeuralSym.knowledge.base import Evidence, EvidenceStrength
                ev = Evidence.new(
                    source="tool_execution",
                    content=f"Successfully executed {tool_name} with args {arguments}",
                    strength=EvidenceStrength.STRONG
                )
                
                self.kg.add_fact(
                    fact_type="tool_success",
                    value={
                        "tool": tool_name,
                        "arguments": arguments
                    },
                    evidence=ev,
                    context_tags={"tool_execution"}
                )
            else:
                # Record failure
                self.kg.record_failure(
                    tool_name=tool_name,
                    arguments=arguments,
                    error_message=error_message or "Unknown error",
                    context_summary=context_summary or "Tool execution failed"
                )
        except Exception as e:
            self.logger.warning(f"Failed to record interaction outcome: {e}")
    
    async def get_enhanced_context(self, base_context: List[Dict], model_name: str) -> List[Dict]:
        """
        Enhance the base context with NeuralSym guidance when appropriate.
        """
        # For now, we're not modifying the context directly but this could be extended
        # to inject guidance based on the conversation history
        return base_context
    
    def close(self):
        """
        Clean up resources and save state.
        """
        if hasattr(self, 'patterns') and self.patterns:
            try:
                self.patterns.close()
            except Exception as e:
                self.logger.warning(f"Error closing pattern analyzer: {e}")
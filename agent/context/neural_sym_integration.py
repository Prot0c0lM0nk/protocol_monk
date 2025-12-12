"""
neural_sym_integration.py
Integration of NeuralSym guidance system with the agent context manager
"""

import logging
import re
from pathlib import Path
from typing import Dict, List, Tuple

# Import NeuralSym components
try:
    from NeuralSym.guidance.unified import UnifiedGuidanceSystem
    from NeuralSym.knowledge.graph import KnowledgeGraph
    from NeuralSym.patterns.analyzer import AdvancedPatternAnalyzer

    NEURALSYM_AVAILABLE = True
except ImportError:
    NEURALSYM_AVAILABLE = False


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
                self.kg = KnowledgeGraph(
                    persistence_path=self.working_dir / ".neuralsym" / "knowledge.json"
                )
                self.patterns = AdvancedPatternAnalyzer(
                    persistence_path=self.working_dir / ".neuralsym" / "patterns.json"
                )
                self.guidance_system = UnifiedGuidanceSystem(self.kg, self.patterns)

                # Wire telemetry for learning
                self.kg.telemetry_callback = self.patterns.on_knowledge_event

                # Ensure the directory exists
                (self.working_dir / ".neuralsym").mkdir(exist_ok=True)

                self.logger.info("NeuralSym guidance system initialized successfully")
            except Exception as e:
                self.logger.error(
                    f"Failed to initialize NeuralSym guidance system: {e}"
                )
                self.guidance_system = None
        else:
            self.guidance_system = None

    def get_guidance_for_intent(
        self, intent: str, context_tags: set, model_size: str = "large"
    ) -> Tuple[str, Dict]:
        """
        Get guidance for a specific intent, optimized for model size.

        Args:
            intent: User intent to get guidance for
            context_tags: Set of context tags for guidance
            model_size: Model size category (default: "large")

        Returns:
            Tuple[str, Dict]: Guidance text and metadata
        """
        if not self.guidance_system:
            return "", {}
        # Use the unified guidance system with model name parameter
        return self.guidance_system.get_guidance(
            intent=intent, context_tags=context_tags, model_name=model_size
        )

    def get_structured_context_for_model(
        self, intent: str, model_size: str = "large"
    ) -> Dict:
        """
        Get structured context optimized for the model size.

        Args:
            intent: User intent to get context for
            model_size: Model size category (default: "large")

        Returns:
            Dict: Structured context with guidance and trace information
        """
        if not self.guidance_system:
            return {}

        # Get guidance from the unified system
        guidance_text, trace = self.guidance_system.get_guidance(
            intent=intent, context_tags={"general"}, model_name=model_size
        )

        # Parse the guidance text into structured format
        # This is a simple implementation - you might want to enhance this
        return {"guidance": guidance_text, "trace": trace}

    def get_critical_constraints_for_model(
        self, intent: str, model_size: str = "large"
    ) -> List[str]:
        """
        Get critical constraints optimized for the model size.

        Args:
            intent: User intent to get constraints for
            model_size: Model size category (default: "large")

        Returns:
            List[str]: Critical constraint items
        """
        if not self.guidance_system:
            return []

        # Get risks from the pattern analyzer directly
        risks = self.patterns.identify_common_mistakes(intent)

        # Limit based on model profile
        profile = self.guidance_system._resolve_profile(model_size)
        return risks[: profile.max_risks]

    def get_verification_checklist_for_model(
        self, intent: str, model_size: str = "large"
    ) -> List[str]:
        """
        Get verification checklist optimized for the model size.

        Args:
            intent: User intent to get checklist for
            model_size: Model size category (default: "large")

        Returns:
            List[str]: Verification checklist items
        """
        if not self.guidance_system:
            return []

        # Get facts from the knowledge graph directly
        facts = self.kg.get_relevant_context(intent)

        # Limit based on model profile
        profile = self.guidance_system._resolve_profile(model_size)
        return facts[: profile.max_facts]

    def record_interaction_outcome(
        self,
        tool_name: str,
        arguments: Dict,
        success: bool,
        error_message: str = None,
        context_summary: str = None,
    ):
        """
        Record the outcome of a tool interaction for learning.

        Args:
            tool_name: Name of the tool that was executed
            arguments: Arguments passed to the tool
            success: Whether the execution succeeded
            error_message: Error message if execution failed
            context_summary: Summary of execution context

        Returns:
            None: Records outcome to knowledge system
        """
        if not self.guidance_system:
            return

        try:
            if success:
                # Record success using Evidence
                from NeuralSym.knowledge.base import (
                    Evidence,
                    EvidenceStrength,
                    FactStatus,
                )

                evidence = Evidence.new(
                    source="tool_execution",
                    content=f"Successfully executed {tool_name}",
                    strength=EvidenceStrength.MODERATE,
                )
                self.kg.add_fact(
                    fact_type="tool_success",
                    value={"tool": tool_name, "arguments": arguments},
                    evidence=evidence,
                    status=FactStatus.VERIFIED,
                )
            else:
                # Record failure
                self.kg.record_failure(
                    tool_name=tool_name,
                    arguments=arguments,
                    error_message=error_message or "Unknown error",
                    context_summary=context_summary or "Tool execution failed",
                )
        except Exception as e:
            self.logger.warning(f"Failed to record interaction outcome: {e}")

    async def get_enhanced_context(
        self, base_context: List[Dict], model_name: str
    ) -> List[Dict]:
        """
        Enhance the base context with NeuralSym guidance when appropriate.

        Args:
            base_context: Original conversation context
            model_name: Name of the model for optimization

        Returns:
            List[Dict]: Enhanced context with guidance if applicable
        """
        if not self.guidance_system:
            return base_context

        # 1. Validate context suitability before enhancement
        if not self._validate_context_for_enhancement(base_context):
            return base_context

        # 2. Extract latest user intent using improved method
        user_intent = self._extract_intent(base_context)
        if not user_intent:
            return base_context

        # 3. Get Guidance
        # We use context tags to help filter. "general" is default.
        guidance_text, _ = self.guidance_system.get_guidance(
            intent=user_intent, context_tags={"general"}, model_name=model_name
        )

        if guidance_text:
            # 4. Inject as System Note
            # We construct a system note containing the guidance
            system_note = {
                "role": "system",
                "content": f"[MEMORY GUIDANCE]\nRelevant past patterns and constraints:\n{guidance_text}",
            }

            # Create a new list to avoid mutating the input list in place
            new_context = list(base_context)

            # Insert after the main system prompt (index 1), or at index 0
            # if list is empty/weird
            insert_idx = 1 if len(new_context) > 0 else 0
            new_context.insert(insert_idx, system_note)

            return new_context

        return base_context
        return base_context

    def close(self):
        """
        Clean up resources and save state.
        """
        if hasattr(self, "patterns") and self.patterns:
            try:
                self.patterns.close()
            except Exception as e:
                self.logger.warning(f"Error closing pattern analyzer: {e}")

    def _extract_intent(self, base_context: List[Dict]) -> str:
        """
        NEW method for better intent extraction using sentence boundaries and word limits.

        Args:
            base_context: List of context messages

        Returns:
            str: Extracted user intent
        """
        # Find the last message from the user
        last_user_msg = next(
            (m for m in reversed(base_context) if m.get("role") == "user"), None
        )

        if not last_user_msg:
            return ""

        user_content = last_user_msg.get("content", "")
        if not user_content:
            return ""

        # Use regex to find sentence boundaries
        sentences = re.split(r'[.!?]+', user_content)
        
        # Take the first sentence or first 50 words if no clear sentence boundary
        if sentences and sentences[0].strip():
            intent = sentences[0].strip()
        else:
            # Split by spaces and take first 50 words
            words = user_content.split()
            intent = ' '.join(words[:50])
        
        # Limit to 200 characters max
        return intent[:200]

    def _validate_context_for_enhancement(self, base_context: List[Dict]) -> bool:
        """
        NEW validation method to ensure context is suitable for NeuralSym enhancement.

        Args:
            base_context: List of context messages to validate

        Returns:
            bool: True if context is suitable for enhancement, False otherwise
        """
        # Check if context is empty or too short
        if not base_context or len(base_context) < 2:
            return False
        
        # Check if system message is properly initialized
        system_msg = next((msg for msg in base_context if msg.get('role') == 'system'), None)
        if not system_msg or '[ERROR]' in system_msg.get('content', ''):
            return False
        
        # Check if there's at least one user message
        user_msg = next((msg for msg in base_context if msg.get('role') == 'user'), None)
        if not user_msg:
            return False
        
        return True

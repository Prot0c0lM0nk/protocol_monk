"""
example_usage.py
Simple example demonstrating how to use the enhanced NeuralSym guidance system
"""

from pathlib import Path
from knowledge.graph import KnowledgeGraph
from patterns.analyzer import AdvancedPatternAnalyzer
from integrated_small_model_guidance import IntegratedSmallModelGuidance
from knowledge.base import Evidence, EvidenceStrength, FactStatus
from knowledge.graph import KnowledgeGraph
from patterns.analyzer import AdvancedPatternAnalyzer
from integrated_small_model_guidance import IntegratedSmallModelGuidance
from knowledge.base import Evidence, EvidenceStrength, FactStatus


def main():
    print("=== NeuralSym Enhanced Guidance System Example ===\n")

    # 1. Initialize the system
    print("1. Initializing NeuralSym components...")
    kg = KnowledgeGraph(persistence_path=Path("./example_knowledge.json"))
    patterns = AdvancedPatternAnalyzer(persistence_path=Path("./example_patterns.json"))

    # Wire telemetry for learning
    kg.telemetry_callback = patterns.on_knowledge_event

    # Initialize enhanced guidance system
    guidance_system = IntegratedSmallModelGuidance(kg, patterns)
    print("   ✓ Components initialized successfully\n")

    # 2. Record a failure (simulating a model making a mistake)
    print("2. Recording a common mistake...")
    kg.record_failure(
        tool_name="execute_command",
        arguments={"command": "cat /var/log/huge_file.log"},
        error_message="MemoryError: Output exceeds buffer size. Use 'head' or 'tail'.",
        context_summary="Attempted to read large file without pagination",
    )
    print("   ✓ Failure recorded and learned\n")

    # 3. Record a success (simulating a model doing something right)
    print("3. Recording a successful approach...")
    ev = Evidence.new(
        source="tool_execution",
        content="Successfully read first 50 lines with head command",
        strength=EvidenceStrength.STRONG,
    )

    kg.add_fact(
        fact_type="tool_success",
        value={
            "tool": "execute_command",
            "execution_time": 0.3,
            "arguments": {"command": "head -50 /var/log/huge_file.log"},
        },
        evidence=ev,
        status=FactStatus.VERIFIED,
        context_tags={"file_system", "large_files"},
    )
    print("   ✓ Success recorded and learned\n")

    # 4. Get guidance for a similar task
    print("4. Getting guidance for a similar task...")
    intent = "FILE_READ_INTENT"
    context_tags = {"file_system"}

    # Try different guidance levels
    for model_type in ["8b_basic", "8b_standard", "8b_advanced"]:
        print(f"\n   --- {model_type.upper()} Guidance ---")
        guidance, trace = guidance_system.get_guidance(intent, context_tags, model_type)
        print(guidance)

    print("\n5. Getting verification guidance...")
    verification = guidance_system.get_verification_guidance(intent)
    print(verification)

    print("\n=== Example Complete ===")
    print("The system has learned from one failure and one success,")
    print("and can now provide better guidance for similar tasks.")


if __name__ == "__main__":
    main()

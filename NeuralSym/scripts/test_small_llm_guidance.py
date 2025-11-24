#!/usr/bin/env python3
"""
Test script to evaluate how the guidance system performs with constraints
that simulate smaller LLM capabilities (8B models).
"""

import time
import shutil
from pathlib import Path

# Import our modules
from knowledge.graph import KnowledgeGraph
from patterns.analyzer import AdvancedPatternAnalyzer
from guidance import GuidanceSystem


def test_small_llm_guidance():
    """Test guidance system with scenarios relevant to smaller LLMs"""
    
    # Setup
    data_dir = Path("./test_data_small_llm")
    if data_dir.exists():
        shutil.rmtree(data_dir)
    data_dir.mkdir()
    
    print("🚀 Testing Guidance System for Smaller LLMs...")
    
    # Initialize systems
    kg = KnowledgeGraph(persistence_path=data_dir / "knowledge.json")
    patterns = AdvancedPatternAnalyzer(persistence_path=data_dir / "patterns.json")
    kg.telemetry_callback = patterns.on_knowledge_event
    guidance_sys = GuidanceSystem(kg, patterns)
    
    # Test 1: Complex file operations that smaller LLMs often get wrong
    print("\n=== Test 1: File Operation Guidance ===")
    
    # First attempt - no guidance yet
    intent = "FILE_READ_INTENT"
    prompt, trace = guidance_sys.get_guidance(intent, {"file_system"})
    print(f"Initial guidance:\n{prompt}")
    
    # Record a failure for reading large files without pagination
    kg.record_failure(
        tool_name="execute_command",
        arguments={"command": "cat huge_log_file.txt"},
        error_message="MemoryError: Output exceeds buffer size. Use 'head' or 'tail'.",
        context_summary="Attempted to read large file without pagination"
    )
    
    # Second attempt - should now have guidance
    prompt, trace = guidance_sys.get_guidance(intent, {"file_system"})
    print(f"\nGuidance after failure:\n{prompt}")
    
    # Check if critical warnings are present
    if "CRITICAL WARNINGS" in prompt and "MemoryError" in prompt:
        print("✅ PASS: System correctly identified and warned about memory error pattern")
    else:
        print("❌ FAIL: System did not generate appropriate warning")
    
    # Test 2: Command execution with dependencies
    print("\n=== Test 2: Command Execution Guidance ===")
    
    intent = "COMMAND_EXECUTION_INTENT"
    prompt, trace = guidance_sys.get_guidance(intent, {"system_admin"})
    print(f"Initial command guidance:\n{prompt}")
    
    # Record a dependency failure
    kg.record_failure(
        tool_name="execute_command",
        arguments={"command": "pip install missing_package"},
        error_message="ERROR: No module named 'missing_package'",
        context_summary="Missing dependency for command execution"
    )
    
    # Get guidance after failure
    prompt, trace = guidance_sys.get_guidance(intent, {"system_admin"})
    print(f"\nGuidance after dependency failure:\n{prompt}")
    
    # Test 3: Code modification guidance
    print("\n=== Test 3: Code Modification Guidance ===")
    
    intent = "CODE_WRITE_INTENT"
    prompt, trace = guidance_sys.get_guidance(intent, {"code_editing"})
    print(f"Code modification guidance:\n{prompt}")
    
    # Record a syntax error
    kg.record_failure(
        tool_name="execute_command",
        arguments={"command": "python script.py"},
        error_message="SyntaxError: invalid syntax at line 10",
        context_summary="Code modification resulted in syntax error"
    )
    
    # Get guidance after error
    prompt, trace = guidance_sys.get_guidance(intent, {"code_editing"})
    print(f"\nGuidance after syntax error:\n{prompt}")
    
    # Test 4: Simulate learning curve
    print("\n=== Test 4: Learning Curve Simulation ===")
    # Simulate multiple successful interactions to build pattern
    from patterns.base import Outcome
    for i in range(5):
        patterns.record_interaction(
            tool_name="read_file",
            arguments={"path": "log.txt", "lines": 50},
            outcome=Outcome.SUCCESS,
            execution_time=0.3,
            context={"complexity": "simple", "task_type": "file_read"}
        )
        time.sleep(0.01)  # Small delay for timestamp ordering
    
    # Now check if system recommends the successful approach
    intent = "FILE_READ_INTENT"
    prompt, trace = guidance_sys.get_guidance(intent, {"file_system"})
    # Now check if system recommends the successful approach
    intent = "FILE_READ_INTENT"
    prompt, trace = guidance_sys.get_guidance(intent, {"file_system"})
    print(f"\nGuidance after pattern learning:\n{prompt}")
    
    # For smaller LLMs, we want to make sure we're not overwhelming them with too much information
    # The system should prioritize critical warnings over recommendations when both are present
    if "CRITICAL WARNINGS" in prompt:
        print("✅ PASS: System prioritized critical warnings (appropriate for smaller LLMs)")
    elif "RECOMMENDED STRATEGY" in prompt:
        print("✅ PASS: System recommended optimized approach based on learned patterns")
    else:
        print("⚠️  INFO: No specific guidance provided")

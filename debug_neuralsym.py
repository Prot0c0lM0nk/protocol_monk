#!/usr/bin/env python3
"""
Debug script to isolate the NeuralSym error.
"""

import sys
import os

# Add the project root to the path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

try:
    # Try to import NeuralSym components
    from NeuralSym.knowledge.graph import KnowledgeGraph
    from NeuralSym.patterns.analyzer import AdvancedPatternAnalyzer
    from NeuralSym.guidance.unified import UnifiedGuidanceSystem
    from pathlib import Path
    print("✓ NeuralSym components imported successfully")
    
    # Try to initialize components
    project_path = Path(project_root)
    kg = KnowledgeGraph(persistence_path=project_path / ".neuralsym" / "knowledge.json")
    patterns = AdvancedPatternAnalyzer(persistence_path=project_path / ".neuralsym" / "patterns.json")
    guidance_system = UnifiedGuidanceSystem(kg, patterns)
    print("✓ NeuralSym components initialized successfully")
    # Try the specific call that's failing
    intent = "Create a simple Python function to calculate factorial"[:200]
    context_tags = {"general"}
    model_name = "qwen3-vl:4b-instruct-q4_K_M"
    
    print(f"Calling get_guidance with:")
    print(f"  intent: {repr(intent)}")
    print(f"  context_tags: {context_tags}")
    print(f"  model_name: {model_name}")
    
    guidance_text, trace = guidance_system.get_guidance(
        intent=intent,
        context_tags=context_tags,
        model_name=model_name
    )
    
    print(f"✓ get_guidance succeeded")
    print(f"  guidance_text: {repr(guidance_text)}")
    print(f"  trace: {trace}")
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
print("\nDone.")
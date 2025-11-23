"""
small_model_simulation.py
Simulation testing the enhanced guidance system for small LLMs
"""

import time
import shutil
from pathlib import Path

# Import our modules
from knowledge.graph import KnowledgeGraph
from patterns.analyzer import AdvancedPatternAnalyzer
from patterns.base import Outcome
from integrated_small_model_guidance import IntegratedSmallModelGuidance
from guidance import GuidanceSystem
from dashboard import DashboardGenerator
# --- CONFIGURATION ---
DATA_DIR = Path("./data_simulation")
REPORT_FILE = "small_model_simulation_report.html"

def clean_start():
    """Wipes previous memory to start fresh."""
    if DATA_DIR.exists():
        shutil.rmtree(DATA_DIR)
    DATA_DIR.mkdir()
    print("🧹 Cleaned up old memory.")

def print_box(title, content):
    print(f"\n{'='*50}")
    print(f" {title}")
    print(f"{'='*50}")
    print(content)

# --- THE SIMULATION ---

def run_small_model_simulation():
    clean_start()
    
    print("🚀 Initializing NeuralSym Modules for Small Models...")
    
    # 1. Initialize Systems
    kg = KnowledgeGraph(persistence_path=DATA_DIR / "knowledge.json")
    patterns = AdvancedPatternAnalyzer(persistence_path=DATA_DIR / "patterns.json")
    
    # 2. Wire Telemetry (The "Nervous System")
    kg.telemetry_callback = patterns.on_knowledge_event
    
    # 3. Initialize Enhanced Small Model Guidance
    small_model_guidance = IntegratedSmallModelGuidance(kg, patterns)
    
    # 3. Initialize Enhanced Small Model Guidance and Traditional Guidance for Dashboard
    small_model_guidance = IntegratedSmallModelGuidance(kg, patterns)
    traditional_guidance = GuidanceSystem(kg, patterns)  # For dashboard compatibility
    # 4. Dashboard for visualization
    dash = DashboardGenerator(patterns, kg, traditional_guidance)  # Using traditional guidance for dashboard
    
    # ========================================================
    # SCENARIO 1: The Naive Mistake (Same as before)
    # ========================================================
    
    intent = "FILE_READ_INTENT"
    
    # Step 1: Ask for guidance (Should be generic initially)
    print("\n--- 🤖 ROUND 1: Naive Attempt ---")
    guidance, trace = small_model_guidance.get_guidance(intent, {"file_system"}, "8b_basic")
    print(f"Guidance Style: {trace.get('capability_profile', {}).get('guidance_style', 'unknown')}")
    
    # Step 2: Simulate the Tool Execution (FAILURE)
    tool_name = "execute_command"
    args = {"command": "cat /var/log/huge_server_log.txt"}
    error_msg = "MemoryError: Output exceeds buffer size. Use 'head' or 'tail'."
    
    print(f"Action: Running '{tool_name}'...")
    print(f"Result: ❌ FAILED ({error_msg})")
    
    # Step 3: Record the Trauma to Knowledge Graph
    kg.record_failure(
        tool_name=tool_name,
        arguments=args,
        error_message=error_msg,
        context_summary="User attempted to read large file without pagination"
    )
    
    # ========================================================
    # SCENARIO 2: The System Reacts with Small Model Guidance
    # ========================================================
    
    print("\n--- 🤖 ROUND 2: Small Model Guidance Adapts ---")
    
    # Step 1: Ask for guidance with different model types
    for model_type in ["8b_basic", "8b_standard", "8b_advanced"]:
        print(f"\n--- Testing {model_type} Guidance ---")
        guidance, trace = small_model_guidance.get_guidance(intent, {"file_system"}, model_type)
        print_box(f"GENERATED GUIDANCE ({model_type})", guidance)
    
    # ========================================================
    # SCENARIO 3: Verification Guidance
    # ========================================================
    
    print("\n--- 🤖 ROUND 3: Verification Guidance ---")
    
    verification_guidance = small_model_guidance.get_verification_guidance(intent)
    print_box("VERIFICATION GUIDANCE", verification_guidance)
    
    # ========================================================
    # SCENARIO 4: The Success Path
    # ========================================================
    
    print("\n--- 🤖 ROUND 4: Doing it Right ---")
    
    # Simulate success with 'read_file'
    tool_name = "read_file"
    args = {"path": "/var/log/huge_server_log.txt", "lines": 50}
    
    print(f"Action: Running '{tool_name}'...")
    
    # Record Success to Knowledge Graph
    from knowledge.base import Evidence, EvidenceStrength, FactStatus
    
    ev = Evidence.new(
        source="tool_execution",
        content="Successfully read first 50 lines",
        strength=EvidenceStrength.CONCLUSIVE
    )
    
    kg.add_fact(
        fact_type="tool_success",
        value={
            "tool": tool_name,
            "execution_time": 0.5,
            "arguments": args
        },
        evidence=ev,
        status=FactStatus.VERIFIED,
        context_tags={"file_system"}
    )
    print("Result: ✅ SUCCESS (Recorded to memory)")
    
    # ========================================================
    # SCENARIO 5: Statistical Learning
    # ========================================================
    print("\n--- 📈 Simulating Repetition (Learning Curve) ---")
    for i in range(5):
        time.sleep(0.1)  # Tiny sleep to ensure timestamp ordering
        patterns.record_interaction(
            tool_name="read_file",
            arguments=args,
            outcome=Outcome.SUCCESS,
            execution_time=0.4,
            context={"complexity": "simple"}
        )
        print(".", end="", flush=True)
    print(" Done.")
    
    # ========================================================
    # FINAL GUIDANCE AFTER LEARNING
    # ========================================================
    print("\n--- 🎯 FINAL GUIDANCE AFTER LEARNING ---")
    
    final_guidance, trace = small_model_guidance.get_guidance(intent, {"file_system"}, "8b_standard")
    print_box("FINAL GUIDANCE", final_guidance)
    
    # ========================================================
    # GENERATE REPORT
    # ========================================================
    print(f"\n📊 Generating Dashboard...")
    path = dash.generate(REPORT_FILE)
    print(f"Done! Open this file in your browser:\n👉 {path}")

if __name__ == "__main__":
    run_small_model_simulation()
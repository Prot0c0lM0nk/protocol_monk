"""
simulation.py
A standalone test harness for the NeuralSym system.
Simulates a conversation loop without needing an actual LLM.
"""

import time
import shutil
import os
from pathlib import Path

# Import our modules
from knowledge.graph import KnowledgeGraph
from patterns.analyzer import AdvancedPatternAnalyzer
from patterns.base import Outcome
from guidance import GuidanceSystem
from dashboard import DashboardGenerator

# --- CONFIGURATION ---
DATA_DIR = Path("./data_simulation")
REPORT_FILE = "simulation_report.html"

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

def run_simulation():
    clean_start()

    print("🚀 Initializing NeuralSym Modules...")
    
    # 1. Initialize Systems
    kg = KnowledgeGraph(persistence_path=DATA_DIR / "knowledge.json")
    patterns = AdvancedPatternAnalyzer(persistence_path=DATA_DIR / "patterns.json")
    
    # 2. Wire Telemetry (The "Nervous System")
    kg.telemetry_callback = patterns.on_knowledge_event
    
    # 3. Initialize Brains
    guidance_sys = GuidanceSystem(kg, patterns)
    dash = DashboardGenerator(patterns, kg, guidance_sys)

    # ========================================================
    # SCENARIO 1: The Naive Mistake
    # We try to cat a massive file. This is a "bad practice".
    # ========================================================
    
    intent = "FILE_READ_INTENT"
    
    # Step 1: Ask for guidance (Should be generic initially)
    print("\n--- 🤖 ROUND 1: Naive Attempt ---")
    prompt, trace = guidance_sys.get_guidance(intent, {"file_system"})
    print(f"Guidance Logic: {trace['logic_path']}")
    
    # Step 2: Simulate the Tool Execution (FAILURE)
    # The user (or LLM) tries to 'cat' a huge log file.
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
    # SCENARIO 2: The System Reacts
    # We try the EXACT SAME intent. Does the Guidance change?
    # ========================================================
    
    print("\n--- 🤖 ROUND 2: The System Adapts ---")
    
    # Step 1: Ask for guidance again
    prompt, trace = guidance_sys.get_guidance(intent, {"file_system"})
    
    # Step 2: Check the Prompt content
    print_box("GENERATED PROMPT", prompt)
    
    if "CRITICAL WARNINGS" in prompt:
        print("✅ TEST PASSED: System inserted a warning prompt!")
    else:
        print("❌ TEST FAILED: System ignored the previous failure.")

    # ========================================================
    # SCENARIO 3: The Success Path
    # We do it the right way.
    # ========================================================
    
    print("\n--- 🤖 ROUND 3: Doing it Right ---")
    
    # Simulate success with 'read_file'
    tool_name = "read_file"
    args = {"path": "/var/log/huge_server_log.txt", "lines": 50}
    
    print(f"Action: Running '{tool_name}'...")
    
    # Record Success to Knowledge Graph (Patterns listens automatically)
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
    # SCENARIO 4: Statistical Learning
    # Run success 5 more times to boost the "Learning Curve"
    # ========================================================
    print("\n--- 📈 Simulating Repetition (Learning Curve) ---")
    for i in range(5):
        time.sleep(0.1) # Tiny sleep to ensure timestamp ordering
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
    # GENERATE REPORT
    # ========================================================
    print(f"\n📊 Generating Dashboard...")
    path = dash.generate(REPORT_FILE)
    print(f"Done! Open this file in your browser:\n👉 {path}")

if __name__ == "__main__":
    run_simulation()
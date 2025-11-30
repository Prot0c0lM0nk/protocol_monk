#!/usr/bin/env python3
"""
example_integration.py
Example of how to use the integrated NeuralSym guidance system
"""

import asyncio
import tempfile
from pathlib import Path

# Add the project root to the path
import sys

sys.path.append(str(Path(__file__).parent.parent))

from agent.context.manager import ContextManager


async def example_neuralsym_usage():
    print("=== NeuralSym Integration Example ===\n")

    # Create a temporary directory for testing
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Initialize context manager with NeuralSym integration
        context_manager = ContextManager(max_tokens=16384, working_dir=temp_path)

        # Check if NeuralSym is available
        if not context_manager.neural_sym:
            print(
                "NeuralSym is not available. Make sure all dependencies are installed."
            )
            return

        print("1. Simulating a file read task...")

        # Define task intent and context
        intent = "FILE_READ_INTENT"
        context_tags = {"file_system", "read_operation"}
        model_name = "llama3.1-8b"

        # Get initial guidance
        print("   Getting initial guidance...")
        guidance, trace = context_manager.get_guidance_for_task(
            intent, context_tags, model_name
        )

        print(f"   Initial guidance:\n{guidance}\n")

        # Add guidance to context (this will be logged meaningfully)
        if guidance:
            await context_manager.add_message(
                "system", f"NEURALSYM GUIDANCE: {guidance}"
            )

        # Show current context
        context = await context_manager.get_context()
        print(f"   Current context has {len(context)} messages")
        print()

        # Simulate recording a failure
        print("2. Recording a failure to read a large file...")
        context_manager.record_tool_execution_outcome(
            tool_name="execute_command",
            arguments={"command": "cat huge_file.log"},
            success=False,
            error_message="MemoryError: Output exceeds buffer size. Use 'head' or 'tail'.",
            context_summary="Attempted to read large file without pagination",
        )

        # Get updated guidance
        print("   Getting updated guidance after failure...")
        guidance, trace = context_manager.get_guidance_for_task(
            intent, context_tags, model_name
        )

        print(f"   Updated guidance:\n{guidance}\n")

        # Add updated guidance to context
        if guidance:
            await context_manager.add_message(
                "system", f"UPDATED NEURALSYM GUIDANCE: {guidance}"
            )

        # Get verification checklist
        print("3. Getting verification checklist...")
        checklist = context_manager.neural_sym.get_verification_checklist_for_model(
            intent, "8b_standard"
        )

        checklist_text = "VERIFICATION CHECKLIST:\n" + "\n".join(
            f"{i+1}. {item}" for i, item in enumerate(checklist)
        )
        print(f"   {checklist_text}\n")

        # Get critical constraints
        print("4. Getting critical constraints...")
        constraints = context_manager.neural_sym.get_critical_constraints_for_model(
            intent, "8b_standard"
        )

        if constraints:
            constraints_text = "CRITICAL CONSTRAINTS:\n" + "\n".join(
                f"- {constraint}" for constraint in constraints
            )
            print(f"   {constraints_text}\n")
        else:
            print("   No critical constraints identified.\n")

        print("=== Example Complete ===")
        print("The NeuralSym system has learned from the failure and will provide")
        print("better guidance for similar tasks in the future.")


if __name__ == "__main__":
    asyncio.run(example_neuralsym_usage())

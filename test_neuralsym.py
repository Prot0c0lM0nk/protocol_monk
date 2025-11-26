#!/usr/bin/env python3
"""
Test script to verify NeuralSym integration is working.
"""

import asyncio
import sys
import os

# Add the project root to the path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

from agent.context.manager import ContextManager

async def test_neuralsym_integration():
    """Test that NeuralSym integration works with small models."""
    print("Testing NeuralSym integration...")
    
    # Create a context manager
    context_manager = ContextManager()
    
    # Check if NeuralSym is available
    if context_manager.neural_sym:
        print("✓ NeuralSym is available")
        
        # Test with a small model that should trigger NeuralSym
        small_model = "qwen3-vl:4b-instruct-q4_K_M"
        print(f"Testing with model: {small_model}")
        
        # Add a user message
        await context_manager.add_user_message("Create a simple Python function to calculate factorial")
        
        # Get context - this should trigger NeuralSym enhancement
        context = await context_manager.get_context(small_model)
        
        print(f"Context length: {len(context)}")
        print("Context messages:")
        for i, msg in enumerate(context):
            print(f"  {i}: {msg['role']} - {msg['content'][:100]}...")
            
        # Check if NeuralSym guidance was added
        if len(context) > 1:
            # Look for the system note with guidance
            for msg in context:
                if msg['role'] == 'system' and 'MEMORY GUIDANCE' in msg['content']:
                    print("✓ NeuralSym guidance found in context!")
                    print(f"Guidance content: {msg['content'][:200]}...")
                    return True
        
        print("⚠️ NeuralSym guidance not found in context")
        return False
    else:
        print("⚠️ NeuralSym is not available")
        return False

async def main():
    """Run the test."""
    print("Running NeuralSym integration test...")
    
    try:
        result = await test_neuralsym_integration()
        if result:
            print("\n✅ NeuralSym integration test passed!")
            return 0
        else:
            print("\n❌ NeuralSym integration test failed!")
            return 1
    except Exception as e:
        print(f"\n❌ NeuralSym integration test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
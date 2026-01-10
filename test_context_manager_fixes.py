#!/usr/bin/env python3
"""
Test Script for Context Manager Fixes
=====================================

This script tests the new context manager functionality that ensures
proper tool call-result pairing for OpenRouter compatibility.
"""

import asyncio
from pathlib import Path
import sys
import os

# Add project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from agent.context.manager import ContextManager
from agent.context.message import Message


async def test_context_manager_with_tool_calls():
    """
    Test that the context manager properly handles tool call-result sequences
    which is critical for OpenRouter compatibility.
    """
    print("🧪 Testing Context Manager with Tool Calls...")

    # Initialize context manager
    cm = ContextManager(max_tokens=8192, working_dir=Path.cwd())
    await cm.async_initialize()

    # Simulate a proper tool call sequence (as OpenRouter expects)
    print("\n📝 Adding user message...")
    await cm.add_user_message("Please read the README file for me.")

    print("\n🤖 Adding assistant tool call...")
    tool_call = [
        {"function": {"name": "read_file", "arguments": {"filepath": "README.md"}}}
    ]
    await cm.add_tool_call_message(tool_call)

    print("\n🔧 Adding tool result response...")
    await cm.add_tool_result_message(
        tool_name="read_file",
        tool_call_id=None,
        content="This is the content of README.md...",
        file_path="README.md",
    )

    # Get the formatted context
    context = await cm.get_context(model_name="gpt-4", provider="openrouter")

    print(f"\n📋 Generated context has {len(context)} messages:")
    for i, msg in enumerate(context):
        role = msg.get("role", "unknown")
        content = msg.get("content", "[No content]")
        tool_calls = msg.get("tool_calls", [])
        has_tool_calls = len(tool_calls) > 0

        if role == "system":
            print(f"  {i}: [System] {content[:50]}...")
        elif role == "user":
            print(f"  {i}: [User] {content[:50]}...")
        elif role == "assistant":
            if has_tool_calls:
                print(
                    f"  {i}: [Assistant] tool call: {tool_calls[0]['function']['name'] if tool_calls else 'none'}"
                )
            else:
                print(f"  {i}: [Assistant] {content[:50]}...")
        elif role == "tool":
            print(f"  {i}: [Tool Result] {content[:50]}...")

    # Verify the sequence is correct (User -> Assistant Tool Call -> Tool Result)
    messages = cm.conversation
    expected_sequence = [
        "user",
        "assistant",
        "tool",
    ]  # User query, assistant tool call, tool result
    actual_sequence = [msg.role for msg in messages]

    print(f"\n✅ Expected sequence: {expected_sequence}")
    print(f"✅ Actual sequence:   {actual_sequence}")

    success = expected_sequence == actual_sequence
    print(
        f"\n🎯 Test {'PASSED' if success else 'FAILED'}: Context sequence is {'correct' if success else 'incorrect'}"
    )

    return success


async def test_remove_last_message():
    """
    Test the new remove_last_message functionality for handling cancellations.
    """
    print("\n\n🧪 Testing Remove Last Message Functionality...")

    # Initialize context manager
    cm = ContextManager(max_tokens=8192, working_dir=Path.cwd())
    await cm.async_initialize()

    # Add some messages
    await cm.add_user_message("First user message")
    await cm.add_assistant_message("First assistant response")
    await cm.add_user_message("Second user message")

    print(f"Before removal: {len(cm.conversation)} messages")

    # Remove the last message
    await cm.remove_last_message()

    print(f"After removal: {len(cm.conversation)} messages")

    # Check the last message is now the first assistant response
    if len(cm.conversation) > 0:
        last_message = cm.conversation[-1]
        success = last_message.role == "assistant" and "First assistant response" in (
            last_message.content or ""
        )
        print(f"🎯 Last message is correct: {'PASSED' if success else 'FAILED'}")
        return success

    return False


async def test_token_calculation_after_removal():
    """
    Test that token accounting remains accurate after message removal.
    """
    print("\n\n🧪 Testing Token Calculation After Message Removal...")

    # Initialize context manager
    cm = ContextManager(max_tokens=8192, working_dir=Path.cwd())
    await cm.async_initialize()

    # Add some messages
    await cm.add_user_message("Hello, how are you?")
    await cm.add_assistant_message("I'm doing well, thank you for asking!")
    original_tokens = cm.get_total_tokens()
    print(f"Original token count: {original_tokens}")

    # Remove the last message
    await cm.remove_last_message()
    tokens_after_removal = cm.get_total_tokens()
    print(f"Token count after removal: {tokens_after_removal}")

    # The token count should be lower after removal
    success = tokens_after_removal < original_tokens
    print(f"🎯 Token calculation test: {'PASSED' if success else 'FAILED'}")

    return success


async def main():
    """
    Run all tests for the context manager fixes.
    """
    print("🚀 Running Context Manager Fix Tests")
    print("=" * 50)

    all_tests_passed = True

    # Test 1: Basic tool call-result sequence
    success1 = await test_context_manager_with_tool_calls()
    all_tests_passed &= success1

    # Test 2: Remove last message functionality
    success2 = await test_remove_last_message()
    all_tests_passed &= success2

    # Test 3: Token calculation accuracy
    success3 = await test_token_calculation_after_removal()
    all_tests_passed &= success3

    print("\n" + "=" * 50)
    print(f"🏁 All Tests {'PASSED' if all_tests_passed else 'FAILED'}")
    print("=" * 50)

    if all_tests_passed:
        print("\n✨ The context manager refactor appears to be working correctly!")
        print("   - Tool call-result sequences are properly formatted")
        print("   - Message cancellation works without breaking chains")
        print("   - Token accounting remains accurate after modifications")
    else:
        print("\n❌ Some tests failed - review the context manager implementation")

    return all_tests_passed


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)

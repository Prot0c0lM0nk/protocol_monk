#!/usr/bin/env python3
"""
Quick test script for SDK-based provider clients
================================================

This script tests both Ollama and OpenRouter SDK clients with simple prompts.
Run this to verify the SDK migration is working correctly.
"""

import asyncio
import sys
import os

# Add the project root to the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.providers.ollama_model_client_sdk import OllamaModelClientSDK
from agent.providers.openrouter_model_client_sdk import OpenRouterModelClient


async def test_ollama():
    """Test Ollama SDK client."""
    print("\n" + "="*60)
    print("Testing Ollama SDK Client")
    print("="*60)

    try:
        # Use a cloud model to avoid downloading local models
        client = OllamaModelClientSDK("ministral-3:8b-cloud")

        messages = [{"role": "user", "content": "Hello, can you count to 3?"}]
        print("\nSending request to Ollama...")
        print(f"Model: {client.model_name}")
        print(f"Message: {messages[0]['content']}\n")

        response_parts = []
        async for chunk in client.get_response_async(messages, stream=True):
            if isinstance(chunk, str):
                response_parts.append(chunk)
                print(chunk, end="", flush=True)

        full_response = "".join(response_parts)
        print(f"\n\n✓ Ollama test passed!")
        print(f"  Total response length: {len(full_response)} characters")

        await client.close()
        return True

    except Exception as e:
        print(f"\n✗ Ollama test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_openrouter():
    """Test OpenRouter SDK client."""
    print("\n" + "="*60)
    print("Testing OpenRouter SDK Client")
    print("="*60)

    try:
        client = OpenRouterModelClient("mistralai/ministral-14b-2512")

        messages = [{"role": "user", "content": "Hello, can you count to 3?"}]

        print("\nSending request to OpenRouter...")
        print(f"Model: {client.model_name}")
        print(f"Message: {messages[0]['content']}\n")

        response_parts = []
        async for chunk in client.get_response_async(messages, stream=True):
            if isinstance(chunk, str):
                response_parts.append(chunk)
                print(chunk, end="", flush=True)

        full_response = "".join(response_parts)
        print(f"\n\n✓ OpenRouter test passed!")
        print(f"  Total response length: {len(full_response)} characters")

        await client.close()
        return True

    except Exception as e:
        print(f"\n✗ OpenRouter test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("SDK Provider Client Test Suite")
    print("="*60)

    # Test Ollama
    ollama_passed = await test_ollama()

    # Test OpenRouter
    openrouter_passed = await test_openrouter()

    # Summary
    print("\n" + "="*60)
    print("Test Summary")
    print("="*60)
    print(f"Ollama:      {'✓ PASSED' if ollama_passed else '✗ FAILED'}")
    print(f"OpenRouter:  {'✓ PASSED' if openrouter_passed else '✗ FAILED'}")
    print("="*60)

    if ollama_passed and openrouter_passed:
        print("\n✓ All tests passed! SDK migration is working correctly.")
        return 0
    else:
        print("\n✗ Some tests failed. Check the error messages above.")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
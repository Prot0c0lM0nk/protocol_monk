#!/usr/bin/env python3
"""
Comprehensive test script for the new OpenRouter SDK implementation
"""

import asyncio
import os
import sys
from typing import List, Dict

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agent.providers.openrouter_model_client_sdk import OpenRouterModelClient

async def test_comprehensive():
    """Comprehensive test of OpenRouter functionality"""
    print("🧪 Comprehensive OpenRouter SDK Testing")
    
    # Check if API key is available
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        print("❌ OPENROUTER_API_KEY environment variable not set")
        return
    
    print(f"✅ API key found: {api_key[:10]}...")
    
    try:
        # Test 1: Different models
        models_to_test = [
            "openai/gpt-3.5-turbo",
            "anthropic/claude-3-haiku-20240307",
        ]
        
        for model_name in models_to_test:
            print(f"\n🔄 Testing model: {model_name}")
            client = OpenRouterModelClient(model_name=model_name)
            
            conversation = [
                {"role": "user", "content": f"Hello! I'm testing the {model_name} model. Please respond with 'Hello from {model_name}!'"}
            ]
            
            response_chunks = []
            async for chunk in client.get_response_async(conversation, stream=True):
                if isinstance(chunk, str):
                    response_chunks.append(chunk)
            
            response = "".join(response_chunks)
            print(f"✅ Response from {model_name}: {response[:100]}...")
            
            await client.close()
        
        # Test 2: Long conversation
        print(f"\n🔄 Testing long conversation...")
        client = OpenRouterModelClient(model_name="openai/gpt-3.5-turbo")
        
        long_conversation = [
            {"role": "user", "content": "What is the capital of France?"},
            {"role": "assistant", "content": "The capital of France is Paris."},
            {"role": "user", "content": "What is the population of that city?"},
            {"role": "assistant", "content": "Paris has a population of approximately 2.1 million people within the city limits."},
            {"role": "user", "content": "What about the metropolitan area?"},
        ]
        
        response_chunks = []
        async for chunk in client.get_response_async(long_conversation, stream=True):
            if isinstance(chunk, str):
                response_chunks.append(chunk)
        
        response = "".join(response_chunks)
        print(f"✅ Long conversation response: {response[:150]}...")
        
        # Test 3: Error handling - invalid model
        print(f"\n🔄 Testing error handling...")
        try:
            bad_client = OpenRouterModelClient(model_name="invalid/model/name")
            conversation = [{"role": "user", "content": "test"}]
            async for chunk in bad_client.get_response_async(conversation):
                pass
            print("❌ Should have failed with invalid model")
        except Exception as e:
            print(f"✅ Correctly caught error: {type(e).__name__}: {str(e)[:100]}")
        
        # Test 4: Configuration options
        print(f"\n🔄 Testing configuration options...")
        config_client = OpenRouterModelClient(
            model_name="openai/gpt-3.5-turbo",
            provider_config={
                "timeout": 30,
                "max_retries": 1,
            }
        )
        
        # Test with different model options
        config_client.model_options = {
            "temperature": 0.1,
            "max_tokens": 100,
            "top_p": 0.9,
        }
        
        conversation = [{"role": "user", "content": "Generate a creative story about a robot learning to paint. Keep it under 50 words."}]
        
        response_chunks = []
        async for chunk in config_client.get_response_async(conversation, stream=True):
            if isinstance(chunk, str):
                response_chunks.append(chunk)
        
        response = "".join(response_chunks)
        print(f"✅ Low temperature response (should be more focused): {response[:100]}...")
        print(f"✅ Response length: {len(response)} characters")
        
        await config_client.close()
        
        print(f"\n🎉 All comprehensive tests passed!")
        
    except Exception as e:
        print(f"❌ Error during comprehensive testing: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_comprehensive())
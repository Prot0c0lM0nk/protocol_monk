#!/usr/bin/env python3
"""
Test script for the new OpenRouter SDK implementation
"""

import asyncio
import os
import sys
from typing import List, Dict

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agent.providers.openrouter_model_client_sdk import OpenRouterModelClient

async def test_basic_chat():
    """Test basic chat functionality"""
    print("🧪 Testing OpenRouter SDK Implementation")
    
    # Check if API key is available
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        print("❌ OPENROUTER_API_KEY environment variable not set")
        return
    
    print(f"✅ API key found: {api_key[:10]}...")
    
    try:
        # Initialize client with a simple model
        client = OpenRouterModelClient(
            model_name="openai/gpt-3.5-turbo",
            provider_config={
                "timeout": 60,
                "max_retries": 2,
                "retry_delay": 1.0,
            }
        )
        
        print(f"✅ Client initialized with model: {client.model_name}")
        
        # Test conversation
        conversation = [
            {"role": "user", "content": "Hello! Can you hear me? Please respond with 'Yes, I can hear you!'"}
        ]
        
        print("📝 Testing streaming response...")
        response_chunks = []
        
        async for chunk in client.get_response_async(conversation, stream=True):
            if isinstance(chunk, str):
                response_chunks.append(chunk)
                print(f"📝 Chunk: {chunk}")
            elif isinstance(chunk, dict) and "tool_calls" in chunk:
                print(f"🔧 Tool call: {chunk}")
        
        full_response = "".join(response_chunks)
        print(f"✅ Full response: {full_response}")
        
        # Test non-streaming response
        print("\n📝 Testing non-streaming response...")
        non_stream_chunks = []
        
        async for chunk in client.get_response_async(conversation, stream=False):
            if isinstance(chunk, str):
                non_stream_chunks.append(chunk)
        
        non_stream_response = "".join(non_stream_chunks)
        print(f"✅ Non-streaming response: {non_stream_response}")
        
        # Test with tools
        print("\n🔧 Testing tool support...")
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "Get weather information",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "location": {"type": "string", "description": "City name"}
                        },
                        "required": ["location"]
                    }
                }
            }
        ]
        
        conversation_with_tools = [
            {"role": "user", "content": "What's the weather in New York?"}
        ]
        
        tool_response_chunks = []
        async for chunk in client.get_response_async(conversation_with_tools, stream=True, tools=tools):
            if isinstance(chunk, str):
                tool_response_chunks.append(chunk)
                print(f"📝 Tool response chunk: {chunk}")
            elif isinstance(chunk, dict) and "tool_calls" in chunk:
                print(f"🔧 Tool call detected: {chunk}")
        
        tool_response = "".join(tool_response_chunks)
        print(f"✅ Tool response: {tool_response}")
        
        # Test client info
        print(f"\n📊 Client info: {client.get_model_info()}")
        print(f"📊 Supports tools: {client.supports_tools()}")
        
        # Close client
        await client.close()
        print("✅ Client closed successfully")
        
        print("\n🎉 All tests passed!")
        
    except Exception as e:
        print(f"❌ Error during testing: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_basic_chat())
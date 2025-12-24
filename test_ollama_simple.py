#!/usr/bin/env python3
"""
Simple direct Ollama API test
"""

import json
import subprocess

def test_simple():
    print("🧪 Simple Ollama API Test")
    
    # Simple test with tools
    request = {
        "model": "qwen3:4b",
        "messages": [{"role": "user", "content": "What files are here?"}],
        "stream": False,
        "tools": [{
            "type": "function",
            "function": {
                "name": "execute_command",
                "description": "Execute shell command",
                "parameters": {
                    "type": "object",
                    "required": ["command"],
    curl_cmd = [
        "curl", "-s", "http://localhost:11434/api/chat",
        "-H", "Content-Type: application/json",
        "-d", json.dumps(request)
    ]
    
    print(f"Running: curl ...")
    result = subprocess.run(curl_cmd, capture_output=True, text=True)
    
    if result.returncode == 0:
        try:
            response = json.loads(result.stdout)
            print("\n📊 Response Analysis:")
            print(f"Message keys: {list(response.get('message', {}).keys())}")
            if 'tool_calls' in response.get('message', {}):
                print(f"🎉 TOOL CALLS: {response['message']['tool_calls']}")
            else:
                print(f"❌ No tool_calls")
                print(f"Full response: {json.dumps(response, indent=2)}")
                print(f"Raw stdout: {result.stdout[:500]}")
                print(f"Raw stderr: {result.stderr[:200]}")
        print(f"Full response: {json.dumps(response, indent=2)}")
        print(f"Raw stdout: {result.stdout[:500]}")
        print(f"Raw stderr: {result.stderr[:200]}")
    
    if result.returncode == 0:
        try:
            response = json.loads(result.stdout)
            print("\n📊 Response Analysis:")
            print(f"Message keys: {list(response.get('message', {}).keys())}")
            if 'tool_calls' in response.get('message', {}):
                print(f"🎉 TOOL CALLS: {response['message']['tool_calls']}")
            else:
                print(f"❌ No tool_calls")
                print(f"Content: {response.get('message', {}).get('content', 'No content')}")
        except Exception as e:
            print(f"❌ Error: {e}")
            print(f"Raw response: {result.stdout[:200]}")
    else:
        print(f"❌ Curl failed: {result.stderr}")

if __name__ == "__main__":
    test_simple()
#!/usr/bin/env python3
"""
Clean Ollama API test for IT models
"""

import json
import subprocess

def test_clean():
    print("🧪 Clean Ollama API Test")
    
    request = {
        "model": "functiongemma:270m-it-fp16",  # Explicitly an IT model for functions
        "messages": [{"role": "user", "content": "List files"}],
        "stream": False,
        "tools": [{
            "type": "function",
            "function": {
                "name": "execute_command",
                "description": "Execute shell command",
                "parameters": {
                    "type": "object",
                    "required": ["command"],
                    "properties": {
                        "command": {"type": "string"}
                    }
                }
            }
        }]
    }
        "tools": [{
            "type": "function",
            "function": {
                "name": "execute_command",
                "description": "Execute shell command",
                "parameters": {
                    "type": "object",
                    "required": ["command"],
                    "properties": {
                        "command": {"type": "string"}
                    }
                }
            }
        }]
    }
    
    cmd = [
        "curl", "-s", "http://localhost:11434/api/chat",
        "-H", "Content-Type: application/json",
        "-d", json.dumps(request)
    ]
    
    print(f"Running: {' '.join(cmd[:3])}...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode == 0:
        try:
            response = json.loads(result.stdout)
            print("\n📊 Response:")
            print(f"Message keys: {list(response.get('message', {}).keys())}")
            
            if 'tool_calls' in response.get('message', {}):
                print(f"🎉 TOOL CALLS FOUND!")
                print(f"Tool calls: {response['message']['tool_calls']}")
            else:
                print(f"❌ No tool_calls field")
                print(f"Content: {response.get('message', {}).get('content', 'No content')}")
                
            # Show raw response for analysis
            print(f"\nRaw response (first 300 chars): {result.stdout[:300]}")
            
        except Exception as e:
            print(f"❌ Error: {e}")
            print(f"Raw output: {result.stdout[:200]}")
    else:
        print(f"❌ Curl failed: {result.stderr}")

if __name__ == "__main__":
    test_clean()
#!/usr/bin/env python3
"""
Test without system prompt tool instructions - let API handle it
"""

import json
import subprocess

def test_no_prompt():
    print("🧪 Testing without system prompt tool instructions")
    
    # Clean request - no system prompt about tools, just regular conversation
    request = {
        "model": "glm-4.6:cloud",  # Your GLM model that we know works
        "messages": [{"role": "user", "content": "What files are in the current directory?"}],
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
    
    cmd = [
        "curl", "-s", "http://localhost:11434/api/chat",
        "-H", "Content-Type: application/json",
        "-d", json.dumps(request)
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode == 0:
        try:
            response = json.loads(result.stdout)
            has_tool_calls = 'tool_calls' in response.get('message', {})
            content = response.get('message', {}).get('content', '')
            
            print(f"✅ Tool calls in API: {has_tool_calls}")
            print(f"Content field: '{content[:50]}...'")
            
            if has_tool_calls:
                print(f"🎉 SUCCESS: API tool calling works without system prompt!")
                print(f"Tool calls: {response['message']['tool_calls']}")
            else:
                print(f"❌ Model puts tools in text content")
                print(f"Full message: {json.dumps(response.get('message', {}), indent=2)[:300]}...")
                
        except Exception as e:
            print(f"❌ Error: {e}")
    else:
        print(f"❌ Failed: {result.stderr}")

if __name__ == "__main__":
    test_no_prompt()
#!/usr/bin/env python3
"""
Final clean Ollama API test for IT models
"""

import json
import subprocess

def test_final():
    print("🧪 Final Ollama API Test")
    
    request = {
        "model": "functiongemma:270m-it-fp16",
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
    
    cmd = [
        "curl", "-s", "http://localhost:11434/api/chat",
        "-H", "Content-Type: application/json", 
        "-d", json.dumps(request)
    ]
    
    print(f"Running: curl ...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode == 0:
        try:
            response = json.loads(result.stdout)
            print("\n📊 Response Analysis:")
            print(f"Message keys: {list(response.get('message', {}).keys())}")
            
            if 'tool_calls' in response.get('message', {}):
                print(f"🎉 TOOL CALLS FOUND!")
                print(f"Tool calls: {response['message']['tool_calls']}")
            else:
                print(f"❌ No tool_calls field")
                print(f"Content: {response.get('message', {}).get('content', 'No content')}")
                
            print(f"\nRaw response structure: {json.dumps(response, indent=2)[:400]}...")
            
        except Exception as e:
            print(f"❌ Error: {e}")
            print(f"Raw output: {result.stdout[:200]}")
    else:
        print(f"❌ Curl failed: {result.stderr}")

if __name__ == "__main__":
    test_final()
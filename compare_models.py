#!/usr/bin/env python3
"""
Compare different IT models for tool calling
"""

import json
import subprocess

def test_model(model_name, description):
    print(f"\n🧪 Testing {description}: {model_name}")
    
    request = {
        "model": model_name,
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
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode == 0:
        try:
            response = json.loads(result.stdout)
            has_tool_calls = 'tool_calls' in response.get('message', {})
            content = response.get('message', {}).get('content', '')
            
            print(f"✅ Tool calls in API: {has_tool_calls}")
            print(f"Content field: '{content[:50]}...'")
            
            if has_tool_calls:
                print(f"🎉 SUCCESS: Model uses API tool_calls!")
            else:
                print(f"❌ Model puts tools in text content")
                
        except Exception as e:
            print(f"❌ Error: {e}")
    else:
        print(f"❌ Model not available or failed")

if __name__ == "__main__":
    # Test different IT models
    test_model("functiongemma:270m-it-fp16", "Function-specific IT model")
    test_model("gemma3:270m-it-bf16", "General IT model") 
    test_model("glm-4.6:cloud", "GLM 4.6 IT model")
#!/usr/bin/env python3
"""
Direct Ollama API testing to understand IT model tool calling behavior
"""

import json
import subprocess
import sys

def test_ollama_direct():
    """Test Ollama API directly with curl to see raw responses"""
    
    print("🧪 Testing Ollama API Directly with IT Models")
    print("=" * 50)
    
    # Test 1: Basic request without tools (baseline)
    print("\n📋 Test 1: Basic request (no tools)")
    basic_request = {
        "model": "qwen3:4b",
        "messages": [{"role": "user", "content": "What files are in the current directory?"}],
        "stream": False
    }
    
    # Test 2: Request with tools (what we're trying to achieve)
    print("\n🔧 Test 2: Request with tools")
    tool_request = {
        "model": "qwen3:4b", 
        "messages": [{"role": "user", "content": "What files are in the current directory?"}],
        "stream": False,
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "execute_command",
                    "description": "Execute a shell command in the working directory",
                    "parameters": {
                        "type": "object",
                        "required": ["command"],
                        "properties": {
                            "command": {"type": "string", "description": "The shell command to execute"}
                        }
                    }
                }
            }
        ]
    }
    
    # Test 3: Explicit instruction with tools
    print("\n🎯 Test 3: Explicit instruction with tools")
    explicit_request = {
        "model": "qwen3:4b",
        "messages": [
            {"role": "system", "content": "You have access to execute_command tool. Use the tool_calls field, not text JSON."},
            {"role": "user", "content": "List the files in the current directory using the execute_command tool."}
        ],
        "stream": False,
        "tools": [
            {
                "type": "function", 
                "function": {
                    "name": "execute_command",
                    "description": "Execute a shell command in the working directory", 
                    "parameters": {
                        "type": "object",
                        "required": ["command"],
                        "properties": {
                            "command": {"type": "string", "description": "The shell command to execute"}
                        }
                    }
                    print(f"✅ Response received")
                    print(f"Full response structure: {json.dumps(response, indent=2)[:500]}...")
                    print(f"\nMessage keys: {list(response.get('message', {}).keys())}")
                    if 'tool_calls' in response.get('message', {}):
                        print(f"🎉 TOOL CALLS FOUND: {response['message']['tool_calls']}")
                    else:
                        print(f"❌ No tool_calls field")
                        print(f"Message content: {response.get('message', {}).get('content', 'No content')}")
                        print(f"Message structure: {json.dumps(response.get('message', {}), indent=2)}")
                        print(f"Message structure: {json.dumps(response.get('message', {}), indent=2)}")
            except json.JSONDecodeError:
                print(f"❌ Invalid JSON response: {result.stdout[:200]}")
        else:
            print(f"❌ Curl failed: {result.stderr}")
                
        except Exception as e:
            print(f"❌ Test failed: {e}")
    
    tests = [
        ("Basic", basic_request),
        ("With Tools", tool_request), 
        ("Explicit", explicit_request)
    ]
    
    for test_name, request_data in tests:
        print(f"\n{'='*20} {test_name} {'='*20}")
        
        try:
            # Convert to curl command
            curl_cmd = [
                "curl", "-s", "http://localhost:11434/api/chat",
                "-H", "Content-Type: application/json",
                "-d", json.dumps(request_data)
            ]
            
            print(f"Command: {' '.join(curl_cmd[:3])} ...")
            result = subprocess.run(curl_cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                try:
                    response = json.loads(result.stdout)
                    print(f"✅ Response received")
                    print(f"Message keys: {list(response.get('message', {}).keys())}")
                    if 'tool_calls' in response.get('message', {}):
                        print(f"🎉 TOOL CALLS FOUND: {response['message']['tool_calls']}")
                    else:
                        print(f"❌ No tool_calls field")
                        print(f"Content preview: {str(response.get('message', {}).get('content', ''))[:100]}...")
                except json.JSONDecodeError:
                    print(f"❌ Invalid JSON response: {result.stdout[:200]}")
            else:
                print(f"❌ Curl failed: {result.stderr}")
                
        except Exception as e:
            print(f"❌ Test failed: {e}")

if __name__ == "__main__":
    test_ollama_direct()
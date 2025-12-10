import aiohttp
import asyncio
import json
import os
import sys

# CONFIGURATION
OLLAMA_URL = "http://localhost:11434/api/chat"
# MODEL_NAME = "ministral-3:14b-cloud"  # Change this to test different models
MODEL_NAME = "ministral-3:14b-cloud"


async def run_chat():
    print(f"🧪 Starting Sandbox Test with {MODEL_NAME}...")

    # 1. Setup Session
    async with aiohttp.ClientSession() as session:
        messages = [
            {
                "role": "system",
                "content": "You are a helper. If asked to list files, output a JSON tool call for 'ls'.",
            }
        ]

        while True:
            user_input = input("\n👤 User (or 'exit'): ")
            if user_input.lower() in ["exit", "quit"]:
                break

            messages.append({"role": "user", "content": user_input})

            # 2. Prepare Payload (The Fixed Version)
            payload = {
                "model": MODEL_NAME,
                "messages": messages,
                "stream": True,
                "options": {
                    "temperature": 0.7,
                    # NOTICE: No num_ctx, no keep_alive. Pure clean request.
                },
            }

            print(f"\n🚀 Sending Request to {MODEL_NAME}...")

            try:
                full_response = ""
                async with session.post(OLLAMA_URL, json=payload) as response:
                    # 3. DIRECT STATUS CHECK
                    if response.status != 200:
                        error_text = await response.text()
                        print(f"\n❌ CRITICAL SERVER ERROR: {response.status}")
                        print(f"Response Body: {error_text}")
                        continue

                    # 4. Stream Handler
                    print("🤖 Model: ", end="", flush=True)
                    async for line in response.content:
                        if not line:
                            continue
                        try:
                            data = json.loads(line)
                            chunk = data.get("message", {}).get("content", "")
                            print(chunk, end="", flush=True)
                            full_response += chunk
                        except:
                            pass
                    print("\n")

                    # 5. Simple Tool Simulation (The "Tool Loop" Test)
                    if "ls" in full_response or "list files" in full_response.lower():
                        if "{" in full_response:  # Rough check for JSON tool call
                            print("\n⚙️ SIMULATING TOOL EXECUTION...")
                            # Fake a large directory listing to stress test the context window
                            fake_tree = "root/\n" + "\n".join(
                                [f"  file_{i}.py" for i in range(50)]
                            )

                            tool_msg = {
                                "role": "tool",
                                "content": f"Command 'ls' output:\n{fake_tree}",
                            }
                            messages.append(
                                {"role": "assistant", "content": full_response}
                            )
                            messages.append(tool_msg)
                            print(
                                f"   Added {len(fake_tree)} chars of tool output. Sending back..."
                            )

                            # Recursively call the model again (The Loop)
                            # We just continue the while loop, forcing the model to read the tool output next turn
                            # In a real loop we'd trigger generation immediately, but this tests the context.
                            print(
                                "   (Press Enter to let the model react to the tool output)"
                            )

            except Exception as e:
                print(f"\n💥 CLIENT CRASH: {e}")


if __name__ == "__main__":
    try:
        asyncio.run(run_chat())
    except KeyboardInterrupt:
        print("\n\nTest Closed.")

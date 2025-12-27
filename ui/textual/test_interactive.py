import sys
import os
import asyncio
from textual import work

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from ui.textual.client import TextualUI
from ui.base import UI
from ui.textual.app import ProtocolMonkApp

# --- THE MOCK AGENT ---
async def interactive_mock_agent(ui: UI):
    """
    Simulates the TAOR loop:
    1. Asks user for input
    2. 'Thinks'
    3. Responds based on input
    """
    # Wait for UI to come up
    await asyncio.sleep(1)
    await ui.print_info("Interactive Mock Agent Connected.")
    
    # Loop 3 times to prove interaction works
    for i in range(3):
        # 1. PROMPT (Blocks here until you type in UI)
        # Note: In the real app, this prompt string would appear in the chat.
        # For now, we just log it.
        await ui.print_info(f"TURN {i+1}/3: Waiting for input...")
        
        user_input = await ui.prompt_user(f"Turn {i+1}")
        
        # 2. THINK
        await ui.start_thinking()
        await asyncio.sleep(1) # Fake processing time
        
        # 3. RESPOND
        response = f"I heard you say: '{user_input}'"
        await ui.print_stream(response)
        await ui.print_stream("\n") 
        
        await ui.stop_thinking()

    await ui.print_info("Test Complete. You can Ctrl+C to exit.")

# --- CUSTOM TEST APP ---
class TestApp(ProtocolMonkApp):
    """
    Subclassing the main app just to inject our test agent.
    """
    def __init__(self, ui_bridge):
        super().__init__()
        self.ui_bridge = ui_bridge

    def on_mount(self):
        super().on_mount()
        # Correct way to launch a background worker in Textual
        self.run_worker(interactive_mock_agent(self.ui_bridge))

# --- LAUNCHER ---
if __name__ == "__main__":
    # 1. Create the Bridge
    # We pass None initially because we create the App in the next step
    ui = TextualUI()
    
    # 2. Create the Test App and link it to the Bridge
    app = TestApp(ui)
    ui.app = app  # Link back so the bridge talks to THIS app
    
    # 3. Run the App
    app.run()
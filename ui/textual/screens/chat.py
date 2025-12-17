from textual import on, work
from textual.containers import Container, VerticalScroll
from textual.reactive import reactive, var
from textual.screen import Screen
from textual.widgets import Label, Static

from ui.textual.widgets.inputs import InputPanel
from ui.textual.widgets.messages import ChatMessage

# Define the greeting banner for Textual UI
TEXTUAL_GREETING = """☦ P R O T O C O L   M O N K ☦

"The Protocol is a path. A discipline.
A way of seeing code not as chaos,
but as sacred geometry waiting to be understood."

Type /help for guidance.
Type /quit to return to the desert of the real.
"""

class ChatScreen(Screen):
    """Main chat interface with proper widget composition."""


    # Reactive properties
    pending_actions = var(list)
    current_status = reactive("Ready")
    current_model = reactive("default")
    is_thinking = reactive(False)

    def compose(self):
        """Create proper widget composition."""
        with Container(id="main-container"):
            # Status bar
            with Container(id="status-bar"):
                yield Label("Status: Ready", id="status")
                yield Static("Model: default", id="model-info")
            
            # Messages area with vertical scroll
            with VerticalScroll(id="messages-container"):
                yield Static(id="messages")
            
            # Thinking indicator
            yield Label("Thinking...", id="thinking-indicator")
            
            # Input panel at bottom
            yield InputPanel(id="input-panel")

    def on_mount(self):
        """Initialize components after mounting."""
        self.messages_area = self.query_one("#messages")
        self.status_widget = self.query_one("#status")
        self.model_widget = self.query_one("#model-info")
        self.thinking_indicator = self.query_one("#thinking-indicator")
        
        # Add greeting message
        self.add_message("assistant", TEXTUAL_GREETING, is_greeting=True)

    def add_message(self, role: str, content: str, is_greeting: bool = False, is_tool_result: bool = False):
        """Add message to message list with proper styling."""
        message = ChatMessage(role, content, is_greeting=is_greeting, is_tool_result=is_tool_result)
        
        # Mount the message
        self.messages_area.mount(message)
        
        # Auto-scroll to bottom
        messages_container = self.query_one("#messages-container")
        messages_container.scroll_end(animate=False)
        
        # Add appropriate CSS classes
        if is_greeting:
            message.add_class("greeting")
        if is_tool_result:
            message.add_class("tool-result")

    def stream_to_ui(self, text: str):
        """Stream text to UI (appends to last message)."""
        # Find the last assistant message that's not a greeting
        messages = self.query("ChatMessage")
        last_assistant_msg = None
        
        for message in reversed(messages):
            if message.role == "assistant" and not message.is_greeting:
                last_assistant_msg = message
                break
        
        if last_assistant_msg:
            last_assistant_msg.append_text(text)
            # Auto-scroll to show new content
            messages_container = self.query_one("#messages-container")
            messages_container.scroll_end(animate=False)
        else:
            self.add_message("assistant", text)

    @on(InputPanel.Submit)
    @work(thread=True)
    async def on_input_panel_submit(self, event):
        """Handle user input with proper worker."""
        worker = self.get_current_worker()
        if worker.is_cancelled:
            return

        text = event.text
        self.add_message("user", text)
        self.current_status = "Processing request..."
        
        try:
            # Process the request through the agent
            response = await self.app.agent.process_request(text)
            self.current_status = "Ready"
            
            # Handle the response (this might contain tool calls)
            await self._handle_agent_response(response)
            
        except Exception as e:
            self.current_status = "Error occurred"
            self.add_message("error", f"Error processing request: {str(e)}")
            self.log(f"Error processing request: {e}")

    async def _handle_agent_response(self, response):
        """Handle the agent's response, including tool calls."""
        if hasattr(response, 'tool_calls') and response.tool_calls:
            # Add tool calls to pending actions
            self.pending_actions.extend(response.tool_calls)
            self.current_status = f"Pending tool approvals: {len(self.pending_actions)}"
            
            # Display the tool calls
            for tool_call in response.tool_calls:
                await self.app.ui.display_tool_call(tool_call)
            
            # Start processing the actions
            self._process_next_action()
        else:
            # Direct response without tool calls
            if hasattr(response, 'content'):
                self.add_message("assistant", response.content)

    def _process_next_action(self):
        """Process pending tool actions with approval flow."""
        if not self.pending_actions:
            self.current_status = "Ready"
            return
        
        # Get the next action
        tool_call = self.pending_actions[0]
        
        # Use the UI bridge to handle approval
        self.run_worker(
            self._handle_tool_approval(tool_call),
            thread=True
        )

    @work(thread=True)
    async def _handle_tool_approval(self, tool_call):
        """Handle tool approval flow."""
        worker = self.get_current_worker()
        if worker.is_cancelled:
            return

        try:
            # Get approval from user
            approval_result = await self.app.ui.confirm_tool_call(
                tool_call, 
                auto_confirm=self.app.ui.auto_confirm
            )
            
            if approval_result:
                # Execute the tool
                self.current_status = "Executing tool..."
                tool_result = await self.app.agent.execute_tool(tool_call)
                
                # Display the result
                await self.app.ui.display_tool_result(tool_result, tool_call.get('name'))
                
                # Remove from pending actions and continue
                self.pending_actions.pop(0)
                self._process_next_action()
            else:
                # Tool was denied
                self.add_message("system", f"Tool {tool_call.get('name')} was denied by user.")
                self.pending_actions.pop(0)
                self._process_next_action()
                
        except Exception as e:
            self.current_status = "Tool execution error"
            self.add_message("error", f"Tool execution failed: {str(e)}")
            self.pending_actions.pop(0)
            self._process_next_action()

    def start_thinking(self):
        """Start the thinking indicator."""
        self.is_thinking = True

    def stop_thinking(self):
        """Stop the thinking indicator."""
        self.is_thinking = False

    def watch_current_status(self, status: str):
        """Update status bar when status changes."""
        self.status_widget.update(f"Status: {status}")

    def watch_current_model(self, model: str):
        """Update model info when model changes."""
        self.model_widget.update(f"Model: {model}")

    def watch_is_thinking(self, thinking: bool):
        """Show/hide thinking indicator."""
        if thinking:
            self.thinking_indicator.display = True
        else:
            self.thinking_indicator.display = False

    def on_chat_screen_tool_result(self, message):
        """Handle tool execution results (message handler)."""
        # This can be used if we implement a message system for tool results
        pass

"""--- End of chat.py ---

**Key Changes Made:**

1. **Added proper Textual imports**: `reactive`, `var`, `work` decorator
2. **Implemented reactive properties**: `pending_actions`, `current_status`, `current_model`, `is_thinking`
3. **Enhanced widget composition**: Used context managers for proper structure
4. **Added thinking indicator**: Visual indicator for processing states
5. **Proper worker usage**: All blocking operations use `@work(thread=True)`
6. **Enhanced message handling**: Better tool call and response processing
7. **Watch methods**: Automatic UI updates when reactive properties change
8. **Improved error handling**: Proper exception handling in async methods
9. **Tool approval flow**: Integrated with the interface's approval system

The refactored chat screen now properly follows Textual's reactive programming model and handles the complete tool approval and execution flow.

Please upload the next file: `ui/textual/screens/approval.py` so I can continue with the refactoring.
"""
from textual import on
from textual.containers import Container, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Static
from typing import Any, Dict


class ApprovalScreen(ModalScreen[Dict]):
    """Modal screen for tool call approvals with proper data flow."""

    DEFAULT_CSS = """
    ApprovalScreen {
        align: center middle;
        background: rgba(0, 0, 0, 0.7);
    }
    
    #approval-dialog {
        width: 80%;
        height: auto;
        max-height: 70%;
        background: $surface;
        border: round $primary;
        padding: 1;
    }
    
    #tool-header {
        text-align: center;
        background: $primary;
        color: $text;
        padding: 1;
        width: 100%;
    }
    
    #tool-info {
        height: 1fr;
        padding: 1;
        border: solid $secondary;
        margin: 1 0;
    }
    
    #argument-list {
        margin: 1 0;
    }
    
    .argument-item {
        margin: 0.5 0;
        padding: 0.5;
        background: $panel;
    }
    
    #button-container {
        layout: horizontal;
        height: auto;
        width: 100%;
        margin-top: 1;
    }
    
    #approve {
        width: 1fr;
        margin-right: 1;
    }
    
    #deny {
        width: 1fr;
        margin-right: 1;
    }
    
    #modify {
        width: 1fr;
    }
    """

    def __init__(self, tool_call: Dict):
        super().__init__()
        self.tool_call = tool_call
        self.approval_result = {
            "approved": False,
            "modified_args": None,
            "tool_name": tool_call.get("name", "Unknown Tool")
        }

    def compose(self):
        """Create proper layout with tool info and buttons."""
        tool_name = self.tool_call.get("name", "Unknown Tool")
        tool_args = self.tool_call.get("arguments", {})
        
        with Container(id="approval-dialog"):
            yield Label(f"Tool Execution Request", id="tool-header")
            
            with Vertical(id="tool-info"):
                yield Label(f"**Tool:** {tool_name}", classes="tool-name")
                yield Label(f"**Description:** Execute this tool with the following parameters:")
                
                with Container(id="argument-list"):
                    if tool_args:
                        for key, value in tool_args.items():
                            yield Static(f"• **{key}:** `{value}`", classes="argument-item")
                    else:
                        yield Label("No arguments required", classes="argument-item")
            
            with Container(id="button-container"):
                yield Button("✓ Approve", id="approve", variant="success")
                yield Button("✗ Deny", id="deny", variant="error")
                yield Button("✎ Modify", id="modify", variant="warning")

    @on(Button.Pressed, "#approve")
    def handle_approval(self):
        """Handle approval with proper data return."""
        self.approval_result["approved"] = True
        self.approval_result["modified_args"] = self.tool_call.get("arguments", {})
        self.dismiss(self.approval_result)

    @on(Button.Pressed, "#deny")
    def handle_denial(self):
        """Handle denial with proper data return."""
        self.approval_result["approved"] = False
        self.approval_result["modified_args"] = None
        self.dismiss(self.approval_result)

    @on(Button.Pressed, "#modify")
    def handle_modification(self):
        """Handle parameter modification (stub for future implementation)."""
        # For now, we'll just deny since modification isn't implemented
        # In a future version, this could open a parameter editor
        tool_name = self.tool_call.get("name", "Unknown Tool")
        self.app.notify(
            f"Parameter modification for {tool_name} not yet implemented. Please approve or deny.",
            title="Modification Not Available"
        )
        # Could implement a proper modification flow here:
        # self.push_screen(ParameterEditorScreen(self.tool_call))

    def on_key(self, event):
        """Handle keyboard shortcuts."""
        if event.key == "escape":
            self.handle_denial()
        elif event.key == "enter":
            self.handle_approval()

    async def on_mount(self):
        """Focus the approve button by default for keyboard navigation."""
        approve_button = self.query_one("#approve")
        approve_button.focus()

"""--- End of approval.py ---

**Key Changes Made:**

1. **Proper ModalScreen typing**: Now uses `ModalScreen[Dict]` for type-safe return values
2. **Enhanced CSS styling**: Added comprehensive styling for the modal dialog
3. **Better layout structure**: Used proper containers and vertical/horizontal layouts
4. **Improved tool information display**: Formatted arguments list with proper styling
5. **Three-button layout**: Added Modify button for future functionality
6. **Proper data return**: Returns structured approval result with tool name and modified args
7. **Keyboard shortcuts**: Escape to deny, Enter to approve
8. **Auto-focus**: Approve button gets focus for keyboard navigation
9. **Modification stub**: Prepare for future parameter editing functionality

The refactored approval screen now provides a much better user experience with proper styling, keyboard navigation, and structured data flow.

Please upload the next file: `ui/textual/widgets/messages.py` so I can continue with the refactoring.
"""
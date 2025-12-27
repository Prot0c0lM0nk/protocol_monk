"""
ui/textual/screens/tool_confirm.py
Modal for approving/rejecting tools.
Includes 'Safety Delay' to prevent accidental Enter-key approval.
"""

import json
import asyncio
from textual.screen import ModalScreen
from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal, Grid
from textual.widgets import Button, Label, TextArea, Markdown


class ToolConfirmModal(ModalScreen):
    """
    A modal that asks the user to confirm a tool execution.
    """

    def __init__(self, tool_call: dict):
        super().__init__()
        self.tool_call = tool_call
        self.tool_name = tool_call.get("action", "unknown_tool")

    def compose(self) -> ComposeResult:
        with Vertical(id="modal_dialog"):
            # HEADER
            yield Label(f"🛠️ Confirm Action: {self.tool_name}", id="title")

            # CONTENT AREA 1: The Tool Details (Read-only)
            params_json = json.dumps(self.tool_call.get("parameters", {}), indent=2)
            reasoning = self.tool_call.get("reasoning", "No reasoning provided.")

            display_text = f"""**Reasoning:**
{reasoning}

**Parameters:**
```json
{params_json}
```"""
            yield Markdown(display_text, id="tool_details")

            # CONTENT AREA 2: The Modification Input (Hidden by default)
            with Vertical(id="modification_area", classes="hidden"):
                yield Label(
                    "What change do you want to suggest?", classes="instruction"
                )
                yield TextArea(id="suggestion_input")

            # BUTTONS AREA (Approve starts DISABLED)
            with Grid(id="main_buttons", classes="button_grid"):
                yield Button(
                    "Approve (Y)", variant="success", id="btn_approve", disabled=True
                )
                yield Button("Reject (N)", variant="error", id="btn_reject")
                yield Button("Modify (M)", variant="primary", id="btn_modify")

            # MODIFICATION BUTTONS
            with Horizontal(id="mod_buttons", classes="hidden"):
                yield Button(
                    "Submit Suggestion", variant="success", id="btn_submit_mod"
                )
                yield Button("Back", variant="error", id="btn_cancel_mod")

    def on_mount(self):
        # Focus REJECT by default for safety
        self.query_one("#btn_reject").focus()

        # Enable the Approve button after 500ms (prevent ghost clicks)
        self.set_timer(0.5, self.enable_approve)

    def enable_approve(self):
        """Callback to enable the approve button."""
        btn = self.query_one("#btn_approve")
        btn.disabled = False
        # Optional: Auto-focus it now that it's safe
        btn.focus()

    def on_button_pressed(self, event: Button.Pressed):
        btn_id = event.button.id

        if btn_id == "btn_approve":
            self.dismiss(True)

        elif btn_id == "btn_reject":
            self.dismiss(False)

        elif btn_id == "btn_modify":
            self.query_one("#tool_details").add_class("hidden")
            self.query_one("#main_buttons").add_class("hidden")
            self.query_one("#modification_area").remove_class("hidden")
            self.query_one("#mod_buttons").remove_class("hidden")
            self.query_one("#suggestion_input").focus()

        elif btn_id == "btn_submit_mod":
            suggestion = self.query_one("#suggestion_input").text.strip()
            if suggestion:
                result = {
                    "modified": {
                        "action": self.tool_call["action"],
                        "parameters": self.tool_call["parameters"],
                        "reasoning": self.tool_call.get("reasoning", ""),
                        "human_suggestion": suggestion,
                    }
                }
                self.dismiss(result)
            else:
                self.notify("Please enter a suggestion.")

        elif btn_id == "btn_cancel_mod":
            self.query_one("#modification_area").add_class("hidden")
            self.query_one("#mod_buttons").add_class("hidden")
            self.query_one("#tool_details").remove_class("hidden")
            self.query_one("#main_buttons").remove_class("hidden")
            self.query_one("#btn_modify").focus()

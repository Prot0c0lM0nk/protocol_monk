#!/usr/bin/env python3
"""
Plain text async UI implementation for Protocol Monk

Uses prompt_toolkit for robust terminal interaction (history, editing)
while maintaining a "Plain" aesthetic for developer clarity.
"""
import asyncio
import sys
import re
from typing import Any, Dict, List, Union

from prompt_toolkit import PromptSession
from prompt_toolkit.patch_stdout import patch_stdout

from ui.base import UI, ToolResult


class PlainUI(UI):
    """Async plain text UI implementation with developer-focused formatting"""

    def __init__(self):
        super().__init__()  # Initialize base UI with thread safety
        self.auto_confirm = False
        self._thinking = False
        # Use PromptSession for history (up-arrow) and better input handling
        self.session = PromptSession()
        self._lock: asyncio.Lock = (
            asyncio.Lock()
        )  # Additional lock for PlainUI-specific operations

    async def start_thinking(self, message: str = "Thinking..."):
        """Indicate that the agent is processing. Thread-safe."""
        async with self._lock:
            self._thinking = True
            print(f"[SYS] {message}", end="\r", flush=True)

    async def stop_thinking(self):
        """Stop the thinking indicator. Thread-safe."""
        async with self._lock:
            if self._thinking:
                # Clear the line completely and reset cursor to start
                print("\r" + " " * 50 + "\r", end="", flush=True)
                self._thinking = False
    def _extract_think_tags(self, text: str) -> tuple[str, str]:
        """
        Extract think tag content from text.
        
        Returns:
            tuple: (think_content, visible_content)
        """
        # Match think tags and their content
        pattern = r'<think>(.*?)</think>'
        match = re.search(pattern, text, flags=re.DOTALL)
        
        if match:
            think_content = match.group(1).strip()
            visible_content = re.sub(pattern, '', text, flags=re.DOTALL).strip()
            return think_content, visible_content
        else:
            return "", text

    async def print_stream(self, text: str):
        """Stream text output with think tag formatting. Thread-safe."""
        async with self._lock:
            if self._thinking:
                # === TRANSITION: FROM THINKING TO SPEAKING ===
                # 1. Clear the "Thinking..." line
                print("\r" + " " * 50 + "\r", end="")
                self._thinking = False

                # 2. Print the requested spacing layout:
                #    (User Input was on previous line)
                #    (We are currently on the line that had 'Thinking...')
                #    We want:
                #    User: Input
                #    [Blank Line]
                #    [MONK] Response

                print()  # This creates the [new line space] (The blank line)
                print("[MONK] ", end="", flush=True)  # The Agent Prefix

            # Extract think tags and visible content
            think_content, visible_content = self._extract_think_tags(text)
            
            # Print think tags with [THINKING] prefix
            if think_content:
                print(f"[THINKING] {think_content} ", end="", flush=True)
            
            # Print visible content normally
            if visible_content:
                print(visible_content, end="", flush=True)

    async def confirm_tool_call(
        self, tool_call: Dict, auto_confirm: bool = False
    ) -> Union[bool, Dict]:
        # Ensure we aren't "thinking" when asking for confirmation
        await self.stop_thinking()

        if auto_confirm or self.auto_confirm:
            await self.display_tool_call(tool_call, auto_confirm=True)
            return True

        await self.display_tool_call(tool_call, auto_confirm=False)

        # Simple y/n/m approval
        response = await self.prompt_user(
            "Execute this action? [Y/n/m] (m = suggest modification)"
        )
        response = response.strip().lower()

        if response in ("y", "yes", ""):  # Default to yes on empty enter
            return True
        elif response == "m":
            # Modify option - get human suggestion
            await self.print_info("What would you like to suggest to the model?")
            await self.print_info("(Describe your suggestion in natural language)")
            suggestion = await self.prompt_user("Suggestion")

            if not suggestion.strip():
                return False

            return {
                "modified": {
                    "action": tool_call["action"],
                    "parameters": tool_call["parameters"],
                    "reasoning": tool_call.get("reasoning", ""),
                    "human_suggestion": suggestion,
                }
            }
        else:
            return False

    async def display_tool_call(self, tool_call: Dict, auto_confirm: bool = False):
        # Ensure clean spacing before tool display
        if self._thinking:
            await self.stop_thinking()

        action = tool_call["action"]
        parameters = tool_call["parameters"]
        reasoning = tool_call.get("reasoning", "")

        print(f"\n[TOOL] Proposed Action: {action}")

        if reasoning:
            print(f"       Reasoning: {reasoning}")

        if parameters:
            print("       Parameters:")
            for key, value in parameters.items():
                value_str = str(value)
                if len(value_str) > 200:
                    if "\n" in value_str:
                        lines = value_str.split("\n")
                        preview = "\n".join(lines[:5])
                        value_str = f"{preview}\n... ({len(lines) - 5} more lines)"
                    else:
                        value_str = value_str[:200] + "..."

                print(f"         {key}: {value_str}")

        if auto_confirm:
            print("       (Auto-executing action)")

    async def display_tool_result(self, result: ToolResult, tool_name: str):
        if result.success:
            print(f"\n[TOOL] ✓ {tool_name} completed")
            output = result.output
            if len(output) > 1000:
                lines = output.split("\n")
                if len(lines) > 20:
                    preview = "\n".join(lines[:15])
                    print(f"{preview}\n... ({len(lines) - 15} more lines)")
                else:
                    print(output[:1000] + "\n... (truncated)")
            else:
                print(output)
        else:
            print(f"\n[TOOL] ✗ {tool_name} failed")
            print(result.output)

    async def display_execution_start(self, count: int):
        print(f"\n[SYS] Executing {count} tool(s)...")

    async def display_progress(self, current: int, total: int):
        print(f"[SYS] Tool {current}/{total}")

    async def display_task_complete(self, summary: str = ""):
        print("\n[SYS] ✓ Task completed")
        if summary:
            print(summary)

    async def print_error(self, message: str):
        print(f"[ERR] {message}")

    async def print_warning(self, message: str):
        print(f"[WARN] {message}")

    async def print_info(self, message: str):
        if message.strip():
            print(f"[SYS] {message}")
        else:
            print()

    async def set_auto_confirm(self, value: bool):
        self.auto_confirm = value
        status = "enabled" if value else "disabled"
        print(f"[SYS] Auto-confirm {status}")

    async def display_startup_banner(self, greeting: str):
        print(greeting)

    async def display_startup_frame(self, frame: str):
        if frame:
            print(f"[INIT] {frame}")

    async def prompt_user(self, prompt: str) -> str:
        """Prompt user for input using prompt_toolkit for better UX"""
        # Enforce vertical separation: Always print a newline before a prompt
        print()

        # Format the prompt string to look like a standard shell prompt or query
        formatted_prompt = (
            f"{prompt}: " if not prompt.endswith(("?", ":", ">")) else f"{prompt} "
        )

        try:
            # Use patch_stdout to ensure background async prints don't mangle the prompt
            with patch_stdout():
                return await self.session.prompt_async(formatted_prompt)
        except (KeyboardInterrupt, EOFError):
            # Return empty string or handle as cancellation
            return ""

    async def print_error_stderr(self, message: str):
        print(f"[ERR] {message}", file=sys.stderr)

    async def display_model_list(self, models: List[Any], current_model: str, current_provider: str = None):
        header = f"\n=== Available Models for {current_provider}" if current_provider else "\n=== Available Models"
        print(f"{header} (Current: {current_model}) ===")
        
        for m in models:
            name = getattr(m, "name", m.get("name") if isinstance(m, dict) else str(m))
            prov = getattr(m, "provider", m.get("provider", "unknown") if isinstance(m, dict) else "unknown")
            ctx = getattr(m, "context_window", m.get("context_window", 0) if isinstance(m, dict) else 0)
            marker = "*" if name == current_model else " "
            # Added Provider column for clarity
            print(f" {marker} {name:<25} ({prov:<12}) [{ctx:,}] ")
        print()

    async def display_switch_report(
        self, report: Any, current_model: str, target_model: str
    ):
        safe = getattr(
            report,
            "safe",
            report.get("safe", False) if isinstance(report, dict) else False,
        )
        curr = getattr(report, "current_tokens", 0)
        limit = getattr(report, "target_limit", 0)

        if not safe:
            print(f"\n[WARN] Context Overflow ({curr:,} > {limit:,})")

    async def close(self):
        """Clean up PlainUI resources."""
        # PlainUI has minimal resources to clean up
        # The prompt_toolkit session will be garbage collected
        # Just ensure thinking state is cleared
        if self._thinking:
            await self.stop_thinking()

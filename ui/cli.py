"""CLI implementation using prompt_toolkit for Protocol Monk."""

import asyncio
import logging
import sys
from typing import Any

from prompt_toolkit import PromptSession
from prompt_toolkit.shortcuts import button_dialog
from prompt_toolkit.patch_stdout import patch_stdout

from protocol_monk.protocol.bus import EventBus
from protocol_monk.protocol.command_dispatcher import build_signoff_prompt, is_signoff_input
from protocol_monk.protocol.events import EventTypes
from protocol_monk.agent.structs import UserRequest, ConfirmationResponse
from protocol_monk.config.settings import Settings
from protocol_monk.exceptions.base import log_exception
from protocol_monk.ui.tool_output_presenter import build_tool_output_view
from protocol_monk.ui.rich.styles import ORTHODOX_DIALOG_STYLE
import time
import uuid

logger = logging.getLogger("PromptToolkitCLI")


# ANSI color codes for light formatting
class Colors:
    """Soft ANSI colors for CLI readability."""
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    ITALIC = "\033[3m"

    # Pastel green for agent text
    AGENT = "\033[38;5;114m"  # Light/pastel green

    # Soft colors for different content types
    REASONING = "\033[38;5;246m"  # Gray for reasoning
    TOOL = "\033[38;5;180m"       # Gold for tool info
    SUCCESS = "\033[38;5;142m"    # Olive green
    ERROR = "\033[38;5;167m"      # Soft red
    WARNING = "\033[38;5;214m"    # Orange
    INFO = "\033[38;5;117m"       # Light cyan


class PromptToolkitCLI:
    """
    CLI implementation using prompt_toolkit.

    Features:
    - Stable single-line input for day-to-day usage
    - Tool confirmation dialogs
    - State symbols in prompt
    - Buffered responses shown per pass
    """

    def __init__(self, bus: EventBus, settings: Settings):
        self._bus = bus
        self._settings = settings
        self._running = False
        self._current_state = "idle"
        self._pass_buffers: dict[str, dict[str, str]] = {}
        self._default_pass_id = "__legacy__"
        self._current_tool_call_id = None
        self._confirmation_tasks: dict[str, asyncio.Task] = {}
        self._auto_confirm = bool(getattr(settings, "auto_confirm", False))
        self._verbose_ui = (
            str(getattr(settings, "log_level", "INFO")).upper() == "DEBUG"
        )

        # Status symbols
        self._status_symbols = {
            "idle": "idle",
            "thinking": "thinking...",
            "executing": "executing",
            "paused": "paused",
            "error": "error",
        }

        # Create prompt session with default bindings for reliable editing behavior.
        self._session = PromptSession(multiline=False)

    async def start(self) -> None:
        """Subscribe to all relevant events."""
        # Status events
        await self._bus.subscribe(
            EventTypes.STATUS_CHANGED, self._handle_status_changed
        )

        # Conversation events
        await self._bus.subscribe(EventTypes.STREAM_CHUNK, self._handle_stream_chunk)
        await self._bus.subscribe(
            EventTypes.RESPONSE_COMPLETE, self._handle_response_complete
        )

        # Tool events
        await self._bus.subscribe(
            EventTypes.TOOL_CONFIRMATION_REQUESTED,
            self._handle_tool_confirmation_requested,
        )
        await self._bus.subscribe(
            EventTypes.TOOL_EXECUTION_START, self._handle_tool_start
        )
        await self._bus.subscribe(EventTypes.TOOL_RESULT, self._handle_tool_result)
        await self._bus.subscribe(
            EventTypes.TOOL_EXECUTION_COMPLETE, self._handle_tool_complete
        )

        # System events
        await self._bus.subscribe(EventTypes.ERROR, self._handle_error)
        await self._bus.subscribe(EventTypes.WARNING, self._handle_warning)
        await self._bus.subscribe(EventTypes.INFO, self._handle_info)
        await self._bus.subscribe(
            EventTypes.AUTO_CONFIRM_CHANGED, self._handle_auto_confirm_changed
        )
        await self._bus.subscribe(EventTypes.COMMAND_RESULT, self._handle_command_result)

        logger.info("PromptToolkitCLI started and listening")

    async def run(self) -> None:
        """Main REPL loop."""
        self._running = True

        print("\n" + "=" * 60)
        print("Protocol Monk CLI")
        print("Press Enter to submit")
        print(
            "Slash commands: /aa /reset /status /metrics /compact /orthocal /skills "
            "/activate-skill /deactivate-skill"
        )
        print("Type 'quit', 'exit', or 'bye' to sign off")
        print("=" * 60 + "\n")

        while self._running:
            # Block input until agent is idle
            if self._current_state != "idle":
                # Show status and wait briefly
                symbol = self._status_symbols.get(self._current_state, "?")
                await asyncio.sleep(0.1)
                continue

            try:
                # Get prompt with current state
                prompt = self._get_prompt()
                # Ensure background prints don't corrupt the current input buffer.
                with patch_stdout():
                    user_text = await self._session.prompt_async(prompt)

                normalized = user_text.strip()
                if self._is_signoff_command(normalized):
                    await self._run_signoff_and_shutdown(normalized)
                    break

                if normalized.startswith("/"):
                    await self._dispatch_slash_command(normalized)
                    continue

                if normalized:
                    # Emit user input
                    await self._emit_user_input(normalized)

            except (EOFError, KeyboardInterrupt):
                print("\nInterrupted. Exiting.")
                self._running = False
                break

    async def stop(self) -> None:
        """Stop the CLI."""
        self._running = False
        for task in list(self._confirmation_tasks.values()):
            task.cancel()
        self._confirmation_tasks.clear()
        logger.info("PromptToolkitCLI stopped")

    def _get_prompt(self) -> str:
        """Get the current prompt."""
        return "✠☦✠> "

    async def _emit_user_input(self, text: str) -> None:
        """Emit user input event."""
        request = UserRequest(
            text=text,
            source="cli",
            request_id=str(uuid.uuid4()),
            timestamp=time.time(),
        )
        await self._bus.emit(EventTypes.USER_INPUT_SUBMITTED, request)

    async def _emit_tool_confirmation(self, tool_call_id: str, decision: str) -> None:
        """Emit tool confirmation response."""
        response = ConfirmationResponse(
            tool_call_id=tool_call_id,
            decision=decision,
            timestamp=time.time(),
        )
        await self._bus.emit(EventTypes.TOOL_CONFIRMATION_SUBMITTED, response)

    @staticmethod
    def _is_signoff_command(text: str) -> bool:
        return is_signoff_input(text)

    async def _dispatch_slash_command(self, text: str) -> None:
        await self._bus.emit(
            EventTypes.SYSTEM_COMMAND_ISSUED,
            {"command": "dispatch_slash", "text": text},
        )

    async def _run_signoff_and_shutdown(self, trigger: str) -> None:
        await self._emit_user_input(build_signoff_prompt(trigger))
        await self._render_shutdown_sequence()
        self._running = False

    async def _render_shutdown_sequence(self) -> None:
        await self._typewriter_line("✠ The session is sealed.")
        await self._typewriter_line("✠ I close this terminal cell now.")

    async def _typewriter_line(self, text: str, delay: float = 0.012) -> None:
        for char in text:
            sys.stdout.write(char)
            sys.stdout.flush()
            await asyncio.sleep(delay)
        sys.stdout.write("\n")
        sys.stdout.flush()

    # Event Handlers

    async def _handle_status_changed(self, data: Any) -> None:
        """Handle STATUS_CHANGED events."""
        # Handle both AgentStatus dataclass and dict
        if hasattr(data, "status"):
            self._current_state = data.status
        else:
            self._current_state = data.get("status", "idle")

    async def _handle_stream_chunk(self, data: dict) -> None:
        """Handle STREAM_CHUNK events - buffer for later display."""
        chunk = data.get("chunk", "")
        channel = data.get("channel", "content")
        if not chunk:
            return
        pass_id = self._normalize_pass_id(data.get("pass_id"))
        buffer = self._pass_buffers.setdefault(pass_id, {"content": "", "thinking": ""})
        if channel == "thinking":
            buffer["thinking"] += chunk
        else:
            buffer["content"] += chunk

    async def _handle_response_complete(self, data: dict) -> None:
        """Handle RESPONSE_COMPLETE - display model reasoning and response for this pass."""
        pass_id = self._normalize_pass_id(data.get("pass_id"))
        buffer = self._pass_buffers.pop(pass_id, {"content": "", "thinking": ""})
        response_text = str(buffer.get("content", "")).strip()
        thinking_text = str(buffer.get("thinking", "")).strip()

        if not response_text:
            response_text = str(data.get("content", "")).strip()
        if not thinking_text:
            thinking_text = str(data.get("thinking", "")).strip()

        # Show reasoning in dimmed gray with separator
        if thinking_text:
            print(
                f"\n{Colors.DIM}{Colors.ITALIC}╭─ Reasoning ─╮{Colors.RESET}\n"
                f"{Colors.REASONING}{thinking_text}{Colors.RESET}\n"
                f"{Colors.DIM}╰─────────────╯{Colors.RESET}"
            )

        # Show agent response in pastel green
        if response_text:
            print(f"\n{Colors.AGENT}{response_text}{Colors.RESET}\n")

        if not thinking_text and not response_text:
            print(f"\n{Colors.DIM}[Empty pass]{Colors.RESET}\n")

    async def _handle_tool_confirmation_requested(self, data: dict) -> None:
        """Handle TOOL_CONFIRMATION_REQUESTED using prompt_toolkit dialog."""
        tool_name = data.get("tool_name", "")
        parameters = data.get("parameters", {})
        tool_call_id = data.get("tool_call_id", "")

        self._current_tool_call_id = tool_call_id
        task = asyncio.create_task(
            self._run_confirmation_dialog(tool_name, parameters, tool_call_id)
        )
        self._confirmation_tasks[tool_call_id] = task

        def _cleanup(_: asyncio.Task, call_id: str = tool_call_id) -> None:
            self._confirmation_tasks.pop(call_id, None)

        task.add_done_callback(_cleanup)

    def _format_parameters_for_dialog(self, parameters: dict) -> str:
        """Keep dialog payload compact to avoid sluggish full-screen redraws."""
        lines = []
        for key, value in parameters.items():
            text = str(value)
            if len(text) > 400:
                text = f"{text[:400]}... [truncated {len(text) - 400} chars]"
            lines.append(f"  {key}: {text}")
        return "\n".join(lines)

    async def _run_confirmation_dialog(
        self, tool_name: str, parameters: dict, tool_call_id: str
    ) -> None:
        """Run confirmation dialog and always emit a terminal decision."""
        params_text = self._format_parameters_for_dialog(parameters)
        result = None
        try:
            dialog_text = (
                f"Execute tool: {tool_name}\n\n"
                "Choose an action (mouse click or keyboard Tab/Enter):\n\n"
                f"Parameters:\n{params_text}"
            )
            with patch_stdout():
                result = await button_dialog(
                    title="Tool Execution",
                    text=dialog_text,
                    buttons=[
                        ("Yes", "approve"),
                        ("Yes + Auto-Approve Edits", "approve_auto"),
                        ("No (Return Control)", "reject"),
                    ],
                    style=ORTHODOX_DIALOG_STYLE,
                ).run_async()
            if result is None:
                logger.warning(
                    "Confirmation dialog closed for %s; falling back to text prompt.",
                    tool_call_id,
                )
                result = await self._prompt_confirmation_text(tool_name)
        except Exception as exc:
            log_exception(logger, logging.ERROR, "Confirmation dialog error", exc)
            result = "reject"

        if result == "approve":
            await self._emit_tool_confirmation(tool_call_id, "approved")
            return
        if result == "approve_auto":
            await self._bus.emit(
                EventTypes.SYSTEM_COMMAND_ISSUED,
                {"command": "toggle_auto_confirm", "auto_confirm": True},
            )
            await self._emit_tool_confirmation(tool_call_id, "approved")
            return

        # Deterministic fallback: if dialog closes / returns None, reject explicitly.
        await self._emit_tool_confirmation(tool_call_id, "rejected")

    async def _prompt_confirmation_text(self, tool_name: str) -> str:
        """Fallback prompt when dialog input is not being consumed."""
        print(
            f"\n[Approval Fallback] {tool_name}\n"
            "Enter: y=approve, a=approve+auto, n=reject"
        )
        choices = {
            "y": "approve",
            "yes": "approve",
            "a": "approve_auto",
            "aa": "approve_auto",
            "n": "reject",
            "no": "reject",
            "r": "reject",
        }
        while True:
            try:
                with patch_stdout():
                    raw = await self._session.prompt_async("(y/a/n) > ")
            except (EOFError, KeyboardInterrupt):
                return "reject"
            choice = raw.strip().lower()
            if choice in choices:
                return choices[choice]
            print("Invalid choice. Use y, a, or n.")

    async def _handle_tool_start(self, data: dict) -> None:
        """Handle TOOL_EXECUTION_START."""
        tool_name = data.get("tool_name", "")
        print(f"\n{Colors.TOOL}▶ {tool_name}{Colors.RESET}")

    async def _handle_tool_result(self, data: dict) -> None:
        """Handle TOOL_RESULT - show summary, not full output."""
        success = data.get("success", False)
        output = data.get("output")
        error = data.get("error")
        tool_name = str(data.get("tool_name", "") or "tool")

        # Only show truncated summary for large outputs
        if output:
            view = build_tool_output_view(tool_name, output, success=bool(success))
            summary = view.preview_text
            if len(summary) > 100:
                summary = summary[:100] + f"... ({len(summary)} chars)"
            elif not summary:
                summary = tool_name
            if view.is_structured and view.output_chars > len(summary):
                summary = f"{summary} ({view.output_chars} chars)"
            elif not view.is_structured:
                output_str = str(output)
                if len(output_str) > 100:
                    summary = output_str[:100] + f"... ({len(output_str)} chars)"
            status = Colors.SUCCESS if success else Colors.ERROR
            print(f"{status}  → {summary}{Colors.RESET}")

        if not success and error:
            print(f"{Colors.ERROR}  ✗ {error}{Colors.RESET}")

    async def _handle_tool_complete(self, data: dict) -> None:
        """Handle TOOL_EXECUTION_COMPLETE."""
        tool_name = data.get("tool_name", "")
        success = data.get("success", False)
        duration = data.get("duration", 0)
        status_color = Colors.SUCCESS if success else Colors.ERROR
        symbol = "✓" if success else "✗"
        print(f"{status_color}  {symbol} {tool_name} ({duration:.2f}s){Colors.RESET}")

    async def _handle_error(self, data: dict) -> None:
        """Handle ERROR events."""
        message = data.get("message", str(data))
        recovered = data.get("recovered", False)
        if recovered:
            print(f"{Colors.WARNING}  ⚠ {message} (recovered){Colors.RESET}")
        else:
            print(f"{Colors.ERROR}  ✗ {message}{Colors.RESET}")

    async def _handle_warning(self, data: dict) -> None:
        """Handle WARNING events."""
        message = data.get("message", str(data))
        print(f"{Colors.WARNING}  ⚠ {message}{Colors.RESET}")

    async def _handle_info(self, data: dict) -> None:
        """Handle INFO events."""
        if not self._verbose_ui:
            return
        message = data.get("message", str(data))
        print(f"{Colors.INFO}  ℹ {message}{Colors.RESET}")

    async def _handle_auto_confirm_changed(self, data: dict) -> None:
        """Track auto-confirm state updates."""
        self._auto_confirm = bool(data.get("auto_confirm", False))

    async def _handle_command_result(self, data: dict) -> None:
        if not isinstance(data, dict):
            return
        command = str(data.get("command", "") or "").strip().lower()
        ok = bool(data.get("ok", False))
        message = str(data.get("message", "") or "").strip()
        payload = data.get("data") if isinstance(data.get("data"), dict) else {}

        if command == "status" and ok:
            rows = [
                ("Provider", payload.get("provider", "")),
                ("Model", payload.get("model", "")),
                ("Working Dir", payload.get("working_directory", "")),
                ("State", payload.get("state", "")),
                ("Stored History", payload.get("stored_history_tokens", 0)),
                ("Next Request", payload.get("estimated_next_request_tokens", 0)),
                ("Reserved Output", payload.get("reserved_completion_tokens", 0)),
                ("Last Prompt", payload.get("last_prompt_tokens", "n/a")),
                ("Last Completion", payload.get("last_completion_tokens", "n/a")),
                ("Last Total", payload.get("last_total_tokens", "n/a")),
                ("Context Limit", payload.get("context_limit", 0)),
                ("Messages", payload.get("message_count", 0)),
                ("Loaded Files", payload.get("loaded_files_count", 0)),
                (
                    "Auto-Approve",
                    "enabled" if bool(payload.get("auto_confirm", False)) else "disabled",
                ),
            ]
            print()
            print(f"{Colors.INFO}Status{Colors.RESET}")
            for label, value in rows:
                print(f"{Colors.DIM}  {label:<14}{Colors.RESET} {value}")
            print()
            return

        if command == "metrics" and ok:
            rows = [
                ("Provider", payload.get("provider", "")),
                ("Model", payload.get("model", "")),
                ("State", payload.get("state", "")),
                ("Stored History", payload.get("stored_history_tokens", 0)),
                ("Next Request", payload.get("estimated_next_request_tokens", 0)),
                ("Reserved Output", payload.get("reserved_completion_tokens", 0)),
                ("Last Prompt", payload.get("last_prompt_tokens", "n/a")),
                ("Last Completion", payload.get("last_completion_tokens", "n/a")),
                ("Last Total", payload.get("last_total_tokens", "n/a")),
                ("Context Limit", payload.get("context_limit", 0)),
            ]
            print()
            print(f"{Colors.INFO}Metrics{Colors.RESET}")
            for label, value in rows:
                print(f"{Colors.DIM}  {label:<17}{Colors.RESET} {value}")
            recent_records = payload.get("recent_records")
            if isinstance(recent_records, list) and recent_records:
                print(f"{Colors.DIM}  Recent Passes{Colors.RESET}")
                for record in recent_records[:5]:
                    if not isinstance(record, dict):
                        continue
                    print(
                        "    "
                        f"{record.get('pass_id', '')}: "
                        f"prompt={record.get('prompt_tokens', 'n/a')} "
                        f"completion={record.get('completion_tokens', 'n/a')} "
                        f"total={record.get('total_tokens', 'n/a')} "
                        f"delta={record.get('prompt_token_delta', 'n/a')}"
                    )
            print()
            return

        if not message:
            return
        color = Colors.INFO if ok else Colors.WARNING
        print(f"{color}  ℹ {message}{Colors.RESET}")

    def _normalize_pass_id(self, pass_id: Any) -> str:
        text = str(pass_id).strip() if pass_id is not None else ""
        return text or self._default_pass_id

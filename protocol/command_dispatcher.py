"""Slash-command parsing and prompt-template helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

AUTO_CONFIRM_ALIASES = {"/aa", "/auto-approve", "/autoapprove"}
SIGNOFF_KEYWORDS = {"quit", "exit", "bye"}
COMPACT_PROMPT_TEMPLATE_FILENAME = "compact_system_prompt.txt"
ORTHOCAL_BRIEFING_PROMPT_TEMPLATE_FILENAME = "orthocal_briefing_prompt.txt"
SESSION_SIGNOFF_PROMPT_FILENAME = "session_signoff_prompt.txt"

_DEFAULT_SIGNOFF_PROMPT = (
    "Maintain your Protocol Monk role. This work session is complete and the user is "
    "signing off now. Offer a brief, respectful signoff blessing and mention that "
    "shutdown may proceed."
)


@dataclass
class SlashCommandParseResult:
    """Structured output from slash-command parsing."""

    raw: str = ""
    command: str | None = None
    arguments: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.command is not None and self.error is None


def parse_slash_command(text: str) -> SlashCommandParseResult:
    """Parse a raw slash command into canonical command + args."""
    normalized = str(text or "").strip()
    result = SlashCommandParseResult(raw=normalized)

    if not normalized.startswith("/"):
        result.error = "Not a slash command."
        return result

    parts = normalized.split()
    command_text = parts[0].lower()
    args = [part.lower() for part in parts[1:]]
    argument_text = normalized[len(parts[0]) :].strip()

    if command_text in AUTO_CONFIRM_ALIASES:
        if not args:
            result.command = "toggle_auto_confirm"
            result.arguments = {"mode": "toggle"}
            return result
        if len(args) == 1 and args[0] in {"on", "off"}:
            result.command = "toggle_auto_confirm"
            result.arguments = {"mode": "set", "value": args[0] == "on"}
            return result
        result.error = "Usage: /aa [on|off]"
        return result

    if command_text == "/reset":
        if args:
            result.error = "Usage: /reset"
            return result
        result.command = "reset_context"
        return result

    if command_text == "/status":
        if args:
            result.error = "Usage: /status"
            return result
        result.command = "status"
        return result

    if command_text == "/metrics":
        if args:
            result.error = "Usage: /metrics"
            return result
        result.command = "metrics"
        return result

    if command_text == "/skills":
        if args:
            result.error = "Usage: /skills"
            return result
        result.command = "skills"
        return result

    if command_text == "/activate-skill":
        if not argument_text:
            result.error = "Usage: /activate-skill <skill-name>"
            return result
        result.command = "activate_skill"
        result.arguments = {"name": argument_text}
        return result

    if command_text == "/deactivate-skill":
        if not argument_text:
            result.error = "Usage: /deactivate-skill <skill-name>"
            return result
        result.command = "deactivate_skill"
        result.arguments = {"name": argument_text}
        return result

    if command_text == "/compact":
        if args:
            result.error = "Usage: /compact"
            return result
        result.command = "compact"
        return result

    if command_text == "/orthocal":
        if not args:
            result.command = "orthocal"
            return result
        if len(args) == 1 and args[0] == "clear":
            result.command = "orthocal_clear"
            return result
        if len(args) != 1:
            result.error = "Usage: /orthocal [YYYY-MM-DD]"
            return result
        try:
            requested_date = date.fromisoformat(args[0]).isoformat()
        except ValueError:
            result.error = "Usage: /orthocal [YYYY-MM-DD]"
            return result
        result.command = "orthocal"
        result.arguments = {"date": requested_date}
        return result

    result.error = f"Unknown slash command: {command_text}"
    return result


def is_signoff_input(text: str) -> bool:
    """Return True when input should trigger model-mediated signoff."""
    return str(text or "").strip().lower() in SIGNOFF_KEYWORDS


def resolve_prompt_template_path(filename: str) -> Path:
    """Resolve prompt-template paths under protocol_monk/prompts."""
    return Path(__file__).resolve().parents[1] / "prompts" / filename


def load_prompt_template(filename: str, *, fallback: str | None = None) -> str:
    """Load a prompt template file from protocol_monk/prompts."""
    path = resolve_prompt_template_path(filename)
    text = path.read_text(encoding="utf-8").strip()
    if text:
        return text
    if fallback is not None:
        return fallback
    raise ValueError(f"Prompt template is empty: {path}")


def build_signoff_prompt(trigger: str) -> str:
    """Build a signoff prompt from template (with safe fallback)."""
    try:
        template = load_prompt_template(
            SESSION_SIGNOFF_PROMPT_FILENAME,
            fallback=_DEFAULT_SIGNOFF_PROMPT,
        )
    except Exception:
        template = _DEFAULT_SIGNOFF_PROMPT

    prompt = template.replace("{trigger}", str(trigger or "").strip().lower())
    return prompt.strip() or _DEFAULT_SIGNOFF_PROMPT

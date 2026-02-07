"""
Model-only prompts and helpers for tool error recovery.
"""

from enum import Enum
from typing import Any, Dict, Optional

try:
    from tools.base import ExecutionStatus
except Exception:  # pragma: no cover - optional dependency
    ExecutionStatus = None


class ToolErrorKind(str, Enum):
    USER_CANCELLED = "user_cancelled"
    SECURITY_BLOCKED = "security_blocked"
    INVALID_PARAMS = "invalid_params"
    TIMEOUT = "timeout"
    COMMAND_FAILED = "command_failed"
    INTERNAL_ERROR = "internal_error"
    UNKNOWN = "unknown"


def _status_value(result: Any) -> Optional[str]:
    status = getattr(result, "status", None)
    if status is None:
        return None
    if hasattr(status, "value"):
        return status.value
    return str(status)


def classify_tool_error(result: Any) -> Optional[ToolErrorKind]:
    """
    Return a ToolErrorKind if this result represents a failure.
    Returns None for success.
    """
    if result is None:
        return ToolErrorKind.UNKNOWN

    error_marker = getattr(result, "error", None)
    if error_marker == ToolErrorKind.USER_CANCELLED.value:
        return ToolErrorKind.USER_CANCELLED

    status_val = _status_value(result)
    if status_val:
        if ExecutionStatus and status_val == ExecutionStatus.SUCCESS.value:
            return None
        if status_val == "security_blocked":
            return ToolErrorKind.SECURITY_BLOCKED
        if status_val == "invalid_params":
            return ToolErrorKind.INVALID_PARAMS
        if status_val == "timeout":
            return ToolErrorKind.TIMEOUT
        if status_val == "command_failed":
            return ToolErrorKind.COMMAND_FAILED
        if status_val == "internal_error":
            return ToolErrorKind.INTERNAL_ERROR

    if getattr(result, "success", True) is True:
        return None

    output = getattr(result, "output", "") or ""
    output_lower = output.lower()
    if "security blocked" in output_lower:
        return ToolErrorKind.SECURITY_BLOCKED
    if "missing required" in output_lower or "invalid params" in output_lower:
        return ToolErrorKind.INVALID_PARAMS
    if "timed out" in output_lower or "timeout" in output_lower:
        return ToolErrorKind.TIMEOUT
    if "command failed" in output_lower:
        return ToolErrorKind.COMMAND_FAILED
    if "internal error" in output_lower or "unexpected internal" in output_lower:
        return ToolErrorKind.INTERNAL_ERROR

    return ToolErrorKind.UNKNOWN


def should_retry(kind: ToolErrorKind) -> bool:
    if kind == ToolErrorKind.USER_CANCELLED:
        return False
    return True


def should_stop(kind: ToolErrorKind) -> bool:
    return kind == ToolErrorKind.USER_CANCELLED


def build_tool_error_prompt(tool_name: str, result: Any, tool_call: Optional[Dict]) -> str:
    """
    Build a model-only instruction to repair a failed tool call.
    """
    kind = classify_tool_error(result) or ToolErrorKind.UNKNOWN
    output = getattr(result, "output", "") or ""
    data = getattr(result, "data", {}) if hasattr(result, "data") else {}
    missing = data.get("missing") if isinstance(data, dict) else None
    exit_code = data.get("exit_code") if isinstance(data, dict) else None

    header = (
        "Tool execution failed. You must correct the issue before retrying. "
        "Do not repeat the same tool call unchanged."
    )

    details = [f"Tool: {tool_name}", f"Error kind: {kind.value}"]
    if missing:
        details.append(f"Missing params: {missing}")
    if exit_code is not None:
        details.append(f"Exit code: {exit_code}")

    guidance = []
    if kind == ToolErrorKind.SECURITY_BLOCKED:
        guidance.append(
            "The prior request violated security policy. Choose a safer alternative "
            "or ask the user for a different approach."
        )
    elif kind == ToolErrorKind.INVALID_PARAMS:
        guidance.append(
            "Fix the tool parameters. Provide all required fields and valid values."
        )
    elif kind == ToolErrorKind.TIMEOUT:
        guidance.append(
            "The tool timed out. Reduce scope, add limits, or use spawn/background mode "
            "if appropriate."
        )
    elif kind == ToolErrorKind.COMMAND_FAILED:
        guidance.append(
            "The command exited non-zero. Adjust arguments or choose a safer alternative."
        )
    elif kind == ToolErrorKind.INTERNAL_ERROR:
        guidance.append(
            "Internal error. Try a simpler tool call or ask the user for guidance."
        )
    else:
        guidance.append("Provide a corrected tool call or ask the user for clarification.")

    if output:
        clipped = output[:400].replace("\n", " ")
        guidance.append(f"Tool output (clipped): {clipped}")

    if tool_call:
        guidance.append(f"Previous tool call: {tool_call}")

    return "\n".join([header] + details + guidance)


def git_commit_signoff_prompt() -> str:
    return (
        "When crafting git commit messages, include a short collaborative sign-off "
        "conveying 'A Protocol Monk Collaboration' in your own words. "
        "Avoid using a fixed phrase verbatim."
    )

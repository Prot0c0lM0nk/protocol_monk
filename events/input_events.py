"""
Input-related events for the event-driven architecture.
"""

import time
from dataclasses import dataclass
from typing import Optional, Dict, Any

from agent.events import Event


# Event type constants
USER_INPUT_SUBMITTED = "USER_INPUT_SUBMITTED"
USER_INPUT_STARTED = "USER_INPUT_STARTED"
USER_INPUT_CANCELLED = "USER_INPUT_CANCELLED"
USER_INTERRUPT_REQUESTED = "USER_INTERRUPT_REQUESTED"
USER_COMMAND_ISSUED = "USER_COMMAND_ISSUED"

AGENT_INPUT_REQUESTED = "AGENT_INPUT_REQUESTED"
AGENT_INPUT_PROVIDED = "AGENT_INPUT_PROVIDED"

INPUT_VALIDATION_REQUESTED = "INPUT_VALIDATION_REQUESTED"
INPUT_VALIDATION_COMPLETED = "INPUT_VALIDATION_COMPLETED"
INPUT_VALIDATION_FAILED = "INPUT_VALIDATION_FAILED"


def create_input_event(input_text: str, ui_type: str, ui_context: Optional[Dict[str, Any]] = None) -> Event:
    """Factory function to create appropriate input event."""
    if is_command(input_text):
        command, arguments = parse_command(input_text)
        return Event(
            type=USER_COMMAND_ISSUED,
            data={
                "command": command,
                "arguments": arguments,
                "ui_type": ui_type,
                "ui_context": ui_context
            },
            timestamp=time.time()
        )
    else:
        return Event(
            type=USER_INPUT_SUBMITTED,
            data={
                "input_text": input_text,
                "ui_type": ui_type,
                "ui_context": ui_context
            },
            timestamp=time.time()
        )


def is_command(input_text: str) -> bool:
    """Check if input is a command (starts with /)."""
    return input_text.strip().startswith('/')


def parse_command(input_text: str) -> tuple[str, Optional[str]]:
    """Parse command and arguments from input."""
    parts = input_text.strip().split(maxsplit=1)
    command = parts[0]
    arguments = parts[1] if len(parts) > 1 else None
    return command, arguments


def create_input_event(input_text: str, ui_type: str, ui_context: Optional[Dict[str, Any]] = None) -> Event:
    """Factory function to create appropriate input event."""
    if is_command(input_text):
        command, arguments = parse_command(input_text)
        return UserCommandIssuedEvent(
            command=command,
            arguments=arguments
        )
    else:
        return UserInputSubmittedEvent(
            input_text=input_text,
            ui_context=ui_context or {"ui_type": ui_type}
        )
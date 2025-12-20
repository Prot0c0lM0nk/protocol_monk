"""
Base classes and interfaces for the tool system.
"""

from enum import Enum
import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

# Handle fallback for constants
try:
    if __package__:
        from ._constants import DANGEROUS_FILE_PATTERNS
    else:
        from _constants import DANGEROUS_FILE_PATTERNS
except ImportError:
    DANGEROUS_FILE_PATTERNS = ["/etc/", ".ssh/", "../", ".env", ".git/"]


@dataclass
class ToolSchema:
    """Describes a tool's interface."""

    name: str
    description: str
    parameters: Dict[str, Any]
    required_params: List[str]


class ExecutionStatus(Enum):
    """Enumeration of possible tool execution statuses."""

    SUCCESS = "success"
    INVALID_PARAMS = "invalid_params"
    SECURITY_BLOCKED = "security_blocked"
    TIMEOUT = "timeout"
    COMMAND_FAILED = "command_failed"
    EXTERNAL_ERROR = "external_error"
    INTERNAL_ERROR = "internal_error"


class ToolResult:
    """Standardized result from tool execution."""

    def __init__(self, status_or_success, output: str, data: Dict = None):
        if isinstance(status_or_success, bool):
            self.status = (
                ExecutionStatus.SUCCESS
                if status_or_success
                else ExecutionStatus.INTERNAL_ERROR
            )
        else:
            self.status = status_or_success

        self.output = output
        self.data = data or {}
        self.success = self.status in (
            ExecutionStatus.SUCCESS,
            ExecutionStatus.COMMAND_FAILED,
        )

    @classmethod
    def success_result(cls, output: str, data: Dict = None):
        """Create a successful execution result."""
        return cls(ExecutionStatus.SUCCESS, output, data)

    @classmethod
    def command_failed(cls, output: str, exit_code: int):
        """Create a result for a failed command execution."""
        return cls(ExecutionStatus.COMMAND_FAILED, output, {"exit_code": exit_code})

    @classmethod
    def invalid_params(cls, output: str, missing_params: list = None):
        """Create a result for invalid parameters."""
        return cls(ExecutionStatus.INVALID_PARAMS, output, {"missing": missing_params})

    @classmethod
    def security_blocked(cls, reason: str):
        """Create a result for a security block."""
        return cls(
            ExecutionStatus.SECURITY_BLOCKED,
            f"Security Blocked: {reason}",
            {"reason": reason},
        )

    @classmethod
    def internal_error(cls, output: str):
        """Create a result for an internal error."""
        return cls(ExecutionStatus.INTERNAL_ERROR, output)

    @classmethod
    def timeout(cls, output: str):
        """Create a result for an execution timeout."""
        return cls(ExecutionStatus.TIMEOUT, output)


class BaseTool(ABC):
    """Abstract base class for all tools."""

    def __init__(self, working_dir: Path):
        self.logger = logging.getLogger(f"tools.{self.__class__.__name__}")
        self.working_dir = Path(working_dir).resolve()

        # Ensure working directory exists
        if not self.working_dir.exists():
            try:
                self.working_dir.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                raise OSError(f"Could not create working directory: {e}") from e

    @property
    @abstractmethod
    def schema(self) -> ToolSchema:
        """Return the tool's schema definition."""

    @abstractmethod
    def execute(self, **kwargs) -> ToolResult:
        """Execute the tool's main logic."""

    def _is_safe_file_path(self, filepath: str) -> bool:
        """
        Check if file path is within working directory and not dangerous.
        Also handles path duplication (e.g. if the input string includes the CWD).

        Args:
            filepath: The path to validate.

        Returns:
            bool: True if safe, False otherwise.
        """
        try:
            # 1. Input Validation
            if not filepath or not isinstance(filepath, (str, Path)):
                self.logger.warning("Invalid filepath provided: %s", filepath)
                return False

            # Normalize to string for initial checks
            str_path = str(filepath)

            # Block specific terminal context indicators (garbage inputs)
            if any(
                char in str_path
                for char in ["@", " protocol_core", "nicholaspitzarella"]
            ):
                self.logger.warning(
                    "Rejected path containing terminal context: %s", str_path
                )
                return False

            path_obj = Path(filepath)

            # 2. Path Resolution & Duplication Handling
            if path_obj.is_absolute():
                # If it's already an OS-level absolute path, resolve it directly.
                target_path = path_obj.resolve()
            else:
                # Check for "Duplication Error" where relative string contains the full path
                str_cwd = str(self.working_dir)

                # Enhanced duplication detection - normalize paths for comparison
                try:
                    # Normalize both paths for accurate comparison
                    normalized_input = Path(str_path).resolve()
                    normalized_cwd = self.working_dir.resolve()

                    # Check if input path is already within working directory
                    if str(normalized_input).startswith(str(normalized_cwd)):
                        # Input is already absolute within working dir - use as-is
                        target_path = normalized_input
                    elif str_path.startswith(str_cwd):
                        # The string matches the CWD but might need normalization
                        # e.g. input="C:/Work/file.txt", cwd="C:/Work" -> Target="C:/Work/file.txt"
                        target_path = Path(str_path).resolve()
                    elif (
                        str_path.startswith("auto_")
                        and str_path.replace("_", "").replace("-", "").isalnum()
                    ):
                        # Preserve special handling for 'auto_' scratchpad files
                        target_path = (
                            self.working_dir / ".scratch" / f"{str_path}.txt"
                        ).resolve()
                    else:
                        # Standard relative path handling
                        target_path = (self.working_dir / str_path).resolve()
                except Exception:
                    # Fallback to original logic if normalization fails
                    if str_path.startswith(str_cwd):
                        # The string matches the CWD. Treat it as absolute to avoid doubling.
                        target_path = Path(str_path).resolve()
                    else:
                        # Standard relative path. Join with CWD.
                        target_path = (self.working_dir / str_path).resolve()
            # 3. Security Boundary Check
            # The resolved path must start with the working directory.
            # (We use str() comparison to be safe across python versions)
            if not str(target_path).startswith(str(self.working_dir)):
                self.logger.warning(
                    "Security: Path traversal blocked: %s -> %s", filepath, target_path
                )
                return False

            # 4. Dangerous Pattern Check
            path_str = str(target_path)
            for pattern in DANGEROUS_FILE_PATTERNS:
                if pattern in path_str:
                    self.logger.warning(
                        "Security: Dangerous pattern '%s' blocked in %s",
                        pattern,
                        filepath,
                    )
                    return False

            return True

        except (OSError, ValueError) as e:
            self.logger.error("Path validation error: %s", e)
            return False


# Path Validation Resilience Helpers
# Added as part of Path Validation Healing Ritual - Section 4.4


def normalize_path_input(path: str) -> str:
    """
    Common path preprocessing to handle user input patterns.

    Handles:
    - Strip quotes (single/double)
    - Convert backslashes to forward slashes
    - Remove leading/trailing whitespace
    - Handle leading slash as relative path

    Args:
        path: Raw user input path

    Returns:
        Normalized path string
    """
    if not path or not isinstance(path, str):
        return ""

    # Strip quotes and whitespace
    normalized = path.strip().strip("\"'")

    # Convert backslashes to forward slashes (Windows compatibility)
    normalized = normalized.replace("\\", "/")

    # Handle leading slash as relative path (not absolute)
    if normalized.startswith("/") and not normalized.startswith("//"):
        # Remove leading slash to make it relative to working directory
        normalized = normalized[1:]

    return normalized


def generate_path_suggestion(original: str, error: str) -> str:
    """
    Generate user-friendly corrections for common path errors.

    Args:
        original: The original path that failed validation
        error: The error message from validation

    Returns:
        Helpful suggestion string
    """
    suggestions = []

    # Common error patterns and suggestions
    if "leading slash" in error.lower() or original.startswith("/"):
        suggestions.append(
            "Try removing the leading slash: use 'path/to/file' instead of '/path/to/file'"
        )

    if "backslash" in error.lower() or "\\" in original:
        suggestions.append(
            "Use forward slashes instead of backslashes: 'path/to/file' instead of 'path\\to\\file'"
        )

    if "quotes" in error.lower() or any(q in original for q in ['"', "'"]):
        suggestions.append(
            'Remove quotes around the path: use path/to/file instead of "path/to/file"'
        )

    if "empty" in error.lower() or not original.strip():
        suggestions.append("Provide a valid file path - empty paths are not allowed")

    if "traversal" in error.lower() or ".." in original:
        suggestions.append(
            "Check that '..' patterns don't escape the working directory"
        )

    if "dangerous pattern" in error.lower():
        suggestions.append(
            "Avoid system directories like /etc, .ssh, or .git in your path"
        )

    if "exist" in error.lower():
        suggestions.append(
            "Make sure the file exists or use create_file_tool to create it first"
        )

    # Default suggestion if no specific patterns match
    if not suggestions:
        suggestions.append(
            f"Check that the path is correct and within the working directory"
        )
        suggestions.append(f"Use forward slashes and avoid special characters")

    return "Suggestions: " + "; ".join(suggestions)


def should_retry_validation(error: str) -> bool:
    """
    Determine if validation failure is retryable.

    Some validation failures are due to temporary conditions or
    can be resolved with path normalization.

    Args:
        error: The error message from validation

    Returns:
        True if validation should be retried with normalized path
    """
    retryable_patterns = [
        "leading slash",
        "quotes",
        "backslash",
        "normalization",
        "format",
    ]

    non_retryable_patterns = [
        "traversal",
        "dangerous pattern",
        "security",
        "empty path",
        "outside working directory",
    ]

    error_lower = error.lower()

    # Check for non-retryable patterns first (security issues)
    for pattern in non_retryable_patterns:
        if pattern in error_lower:
            return False

    # Check for retryable patterns (formatting issues)
    for pattern in retryable_patterns:
        if pattern in error_lower:
            return True

    # Default to not retrying if uncertain
    return False


def extract_path_from_error(error_msg: str) -> str:
    """
    Attempt to extract the original path from an error message.

    Useful for logging and debugging validation failures.

    Args:
        error_msg: The error message that might contain a path

    Returns:
        Extracted path or empty string if not found
    """
    import re

    # Common patterns for path extraction
    patterns = [
        r"path ['\"](.*?)['\"]",
        r"file ['\"](.*?)['\"]",
        r"['\"](.*?)['\"] blocked",
        r"['\"](.*?)['\"] failed",
        r"Path (.*?) ->",
        r"path (.*?)(?:\s|$)",
    ]

    for pattern in patterns:
        match = re.search(pattern, error_msg, re.IGNORECASE)
        if match:
            return match.group(1).strip()

    return ""


def validate_path_format(path: str) -> tuple[bool, str]:
    """
    Quick format validation for paths before full validation.

    Performs lightweight checks that don't require file system access.

    Args:
        path: Path to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not path or not isinstance(path, str):
        return False, "Empty or invalid path"

    if not path.strip():
        return False, "Path cannot be empty or whitespace only"

    # Check for obvious dangerous patterns (quick reject)
    dangerous_patterns = ["/etc/", ".ssh/", ".git/", "../"]
    for pattern in dangerous_patterns:
        if pattern in path:
            return False, f"Dangerous pattern '{pattern}' detected"

    # Check for invalid characters
    invalid_chars = ["<", ">", "|", "*", "?"]
    for char in invalid_chars:
        if char in path:
            return False, f"Invalid character '{char}' in path"

    return True, ""

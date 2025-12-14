import os
import re
from pathlib import Path
from typing import Tuple, Optional, List


class PathValidator:
    """
    Centralized path validation and cleaning for secure file operations.

    Handles all path-related security checks, normalization, and working directory resolution
    in a single, consistent manner.
    """

    def __init__(self, working_dir: Path):
        """Initialize with the current working directory."""
        self.working_dir = working_dir.resolve()

    def validate_and_clean_path(self, filepath: str) -> Tuple[str, Optional[str]]:
        """
        Validate and clean a file path in one centralized operation.

        Args:
            filepath: The raw file path to validate and clean

        Returns:
            Tuple of (cleaned_path, error_message) where error_message is None if valid
        """
        # First check security before any manipulation
        is_safe, security_error = self._is_safe_path(filepath)
        if not is_safe:
            return filepath, security_error

        # Clean the path string
        cleaned_path = self._clean_path_string(filepath)

        # Resolve to working directory and perform final validation
        try:
            abs_path = self._resolve_to_working_dir(cleaned_path)
        except ValueError as e:
            return filepath, str(e)

        # Final boundary check (should never fail if previous checks passed)
        if not self._is_within_working_dir(abs_path):
            return filepath, "Path resolved outside working directory"

        return cleaned_path, None

    def _is_safe_path(self, filepath: str) -> Tuple[bool, Optional[str]]:
        """
        Comprehensive security validation for file paths.

        Returns:
            (is_safe, reason_if_unsafe)
        """
        # Check for path traversal attempts
        if "../" in filepath or "..\\" in filepath:
            return False, "Path traversal detected (../)"

        # Check for absolute paths (which might escape working directory)
        if os.path.isabs(filepath):
            abs_path = Path(filepath).resolve()
            if not self._is_within_working_dir(abs_path):
                return False, f"Absolute path outside working directory: {filepath}"

        # Check for dangerous patterns
        dangerous_patterns = [
            ("~", "Home directory reference (~)"),
            ("$HOME", "Environment variable reference"),
            ("$", "Potential variable injection"),
            ("|", "Pipe character"),
            (";", "Command separator"),
            ("&&", "Command chain operator"),
            ("`", "Command substitution"),
            (">>", "Output redirection"),
            (">", "Output redirection"),
            ("<", "Input redirection"),
        ]

        for pattern, reason in dangerous_patterns:
            if pattern in filepath:
                return (
                    False,
                    f"Potentially dangerous character in path: {reason} ({pattern})",
                )

        # Check for non-printable characters
        if not all(32 <= ord(c) <= 126 for c in filepath):
            return False, "Non-printable characters in path"

        # Check for invalid characters on current platform
        invalid_chars = ["<", ">", ":", '"', "|", "?", "*"]
        if any(char in filepath for char in invalid_chars):
            return False, f"Invalid filesystem character in path: {invalid_chars}"

        return True, None

    def _clean_path_string(self, filepath: str) -> str:
        """
        Clean and normalize the path string without resolving it.

        - Normalize slashes to current OS style
        - Remove duplicate slashes
        - Remove leading/trailing whitespace and quotes
        - Remove working directory prefix if present
        """
        # Clean up the string
        cleaned = filepath.strip().strip("\"'")

        # Normalize path separators
        cleaned = cleaned.replace("\\", "/")

        # Remove duplicate slashes
        cleaned = re.sub(r"/+", "/", cleaned)

        # Remove working directory prefix if present
        if cleaned.startswith(str(self.working_dir)):
            cleaned = cleaned[len(str(self.working_dir)) :].lstrip("/")

        # Remove leading slash that might make it absolute
        if cleaned.startswith("/"):
            cleaned = cleaned[1:]

        # Remove leading ./ if present
        if cleaned.startswith("./"):
            cleaned = cleaned[2:]

        return cleaned

    def _resolve_to_working_dir(self, filepath: str) -> Path:
        """
        Resolve a cleaned path relative to the working directory.

        Raises:
            ValueError: If the resolved path is outside the working directory
        """
        # Handle empty path as current directory
        if not filepath:
            return self.working_dir

        # Create absolute path by joining with working directory
        abs_path = (self.working_dir / filepath).resolve()

        # Final boundary check
        if not self._is_within_working_dir(abs_path):
            raise ValueError(f"Resolved path is outside working directory: {abs_path}")

        return abs_path

    def _is_within_working_dir(self, path: Path) -> bool:
        """Check if a path is within the working directory."""
        try:
            path.resolve().relative_to(self.working_dir)
            return True
        except ValueError:
            return False

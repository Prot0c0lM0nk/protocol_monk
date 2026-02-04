import hashlib
import os
import re
from pathlib import Path
from typing import Tuple, Optional, List, Dict


class PathValidator:
    """
    Centralized path validation and cleaning for secure file operations.

    Handles all path-related security checks, normalization, and working directory resolution
    in a single, consistent manner. Now with smart blessing - accepts valid paths while
    maintaining security against actual traversal attempts.
    """

    def __init__(self, working_dir: Path):
        """Initialize with the current working directory."""
        self.working_dir = working_dir.resolve()
        self.validation_cache: Dict[str, Tuple[str, Optional[str]]] = {}
        self.working_dir_hash = hashlib.md5(str(self.working_dir).encode()).hexdigest()

    def validate_and_clean_path(
        self, filepath: str, must_exist: bool = False
    ) -> Tuple[str, Optional[str]]:
        """
        Validate and clean a file path in one centralized operation.

        Smart blessing approach - accepts valid paths while maintaining security.
        Now with caching to break circular dependencies and existence checking
        for operations that require real files.

        Args:
            filepath: The raw file path to validate and clean
            must_exist: If True, path must point to an existing file/directory

        Returns:
            Tuple of (cleaned_path, error_message) where error_message is None if valid
        """
        # Check cache first to break circular dependency
        cache_key = self._get_validation_key(filepath)
        if cache_key in self.validation_cache:
            cached_path, cached_error = self.validation_cache[cache_key]
            # For cached results, we don't need existence check again
            if not must_exist or cached_error is not None:
                return cached_path, cached_error
            # If must_exist and cached as valid, check existence again (files may change)

        # Pre-normalize common patterns before validation
        normalized_path = self._normalize_leading_slash(filepath)

        # First check security before any manipulation
        is_safe, security_error = self._is_safe_path(normalized_path)
        if not is_safe:
            self.validation_cache[cache_key] = (normalized_path, security_error)
            return normalized_path, security_error

        # Clean the path string
        cleaned_path = self._clean_path_string(normalized_path)

        # Resolve to working directory and perform final validation
        try:
            abs_path = self._resolve_to_working_dir(cleaned_path)
        except ValueError as e:
            error_msg = str(e)
            self.validation_cache[cache_key] = (cleaned_path, error_msg)
            return cleaned_path, error_msg

        # Final boundary check (should never fail if previous checks passed)
        if not self._is_within_working_dir(abs_path):
            error_msg = "Path resolved outside working directory"
            self.validation_cache[cache_key] = (cleaned_path, error_msg)
            return cleaned_path, error_msg

        # Existence check if required
        if must_exist and not abs_path.exists():
            error_msg = f"Path does not exist: {cleaned_path}"
            self.validation_cache[cache_key] = (cleaned_path, error_msg)
            return cleaned_path, error_msg

        # Success - cache the blessing
        self.validation_cache[cache_key] = (cleaned_path, None)
        return cleaned_path, None

    def _is_safe_path(self, filepath: str) -> Tuple[bool, Optional[str]]:
        """
        Comprehensive security validation for file paths.

        Returns:
            (is_safe, reason_if_unsafe)
        """
        # Check for path traversal attempts - but allow harmless ones
        if "../" in filepath or "..\\" in filepath:
            # Only reject if the path would actually escape working directory
            # Test by resolving and checking boundaries
            if not self._is_harmless_traversal(filepath):
                return False, "Path traversal detected (../)"

        # Check for absolute paths - convert to relative if within working directory
        if os.path.isabs(filepath):
            try:
                abs_path = Path(filepath).resolve()
                # Check if this absolute path is actually within our working directory
                if self._is_within_working_dir(abs_path):
                    # This is actually a relative path expressed as absolute - allow it
                    return True, None
                else:
                    return False, f"Absolute path outside working directory: {filepath}"
            except (ValueError, RuntimeError):
                return False, f"Invalid absolute path: {filepath}"

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

        # Remove working directory prefix if present - but only exact matches
        # Convert both to absolute paths for safe comparison
        try:
            # Only strip if this is actually our working directory prefix
            if cleaned.startswith(str(self.working_dir)):
                # Make sure we're not accidentally stripping part of a filename
                # by checking if what follows is a path separator
                remaining = cleaned[len(str(self.working_dir)) :]
                if (
                    remaining.startswith("/")
                    or remaining.startswith("\\")
                    or not remaining
                ):
                    cleaned = remaining.lstrip("/\\")
        except (ValueError, TypeError):
            # If we can't safely process it, leave it as-is
            pass

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
        # Reject empty path explicitly - never default to working directory
        if not filepath or filepath.isspace():
            raise ValueError(
                "Empty path is not allowed. Please specify a file or directory path."
            )

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

    def _get_validation_key(self, filepath: str) -> str:
        """Generate cache key for validation results."""
        return f"{self.working_dir_hash}:{filepath}"

    def _normalize_leading_slash(self, filepath: str) -> str:
        """
        Convert leading slash to relative path for paths that appear absolute
        but are actually relative to working directory.

        /agent/file.py becomes agent/file.py (relative to working directory)
        This handles the common user input pattern of leading slashes on relative paths.
        """
        if filepath.startswith("/"):
            # Strip leading slash - let the absolute path checker in _is_safe_path
            # determine if this is truly absolute or just a relative path with leading slash
            return filepath.lstrip("/")
        return filepath

    def _is_harmless_traversal(self, filepath: str) -> bool:
        """
        Check if .. pattern actually escapes working directory.

        Returns True if the pattern is harmless (doesn't escape),
        False if it could be dangerous.
        """
        try:
            # Resolve the path to see where it actually goes
            test_path = (self.working_dir / filepath).resolve()
            return self._is_within_working_dir(test_path)
        except (ValueError, RuntimeError):
            # If we can't resolve it safely, assume it's dangerous
            return False

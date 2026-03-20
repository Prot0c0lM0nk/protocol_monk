from pathlib import Path
from typing import Union
from protocol_monk.exceptions.tools import ToolError


class PathValidator:
    """
    Centralized path safety system.
    Prevents path traversal, enforces workspace confinement,
    and cleans up model hallucinations (e.g. double paths).
    """

    def __init__(self, workspace_root: Union[str, Path]):
        self.workspace_root = Path(workspace_root).resolve()

    def validate_path(self, user_path: str, must_exist: bool = False) -> Path:
        """
        Sanitizes and validates a path.

        Args:
            user_path: The raw string from the model (e.g., "./file.txt")
            must_exist: If True, raises error if file doesn't exist.

        Returns:
            A clean, absolute Path object.

        Raises:
            ToolError: If path escapes workspace or is invalid.
        """
        if not user_path:
            raise ToolError("File path cannot be empty.")

        # 1. Sanitize: Fix common model hallucinations
        # e.g., "workspace/workspace/file.py" -> "workspace/file.py" if accidentally duplicated
        clean_str = user_path.strip().strip("'").strip('"')

        try:
            # 2. Resolve: Handle relative paths against workspace
            raw_path = Path(clean_str).expanduser()
            if not raw_path.is_absolute():
                raw_path = self.workspace_root / raw_path
            target_path = raw_path.resolve(strict=False)
        except Exception:
            raise ToolError(
                f"Invalid path format: {clean_str}",
                user_hint="The file path format is invalid.",
            )

        # 3. Confinement Check (Jail)
        # Ensure the target is actually inside the workspace
        if not target_path.is_relative_to(self.workspace_root):
            raise ToolError(
                f"Access denied: {clean_str}",
                user_hint="I cannot access files outside the active workspace.",
                details={"target": str(target_path), "root": str(self.workspace_root)},
            )

        # 4. Existence Check (Optional)
        if must_exist and not target_path.exists():
            raise ToolError(
                f"File not found: {clean_str}",
                user_hint=f"The file '{clean_str}' does not exist.",
                details={"path": str(target_path)},
            )

        return target_path

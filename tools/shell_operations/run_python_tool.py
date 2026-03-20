import sys
import logging
import shlex
import tempfile
from pathlib import Path
from typing import Dict, Any

from protocol_monk.exceptions.base import log_exception
from protocol_monk.exceptions.tools import ToolError
from protocol_monk.tools.base import BaseTool
from protocol_monk.config.settings import Settings
from protocol_monk.tools.output_contract import build_process_output, build_tool_output
from protocol_monk.tools.shell_operations.process_runner import run_exec_command


class RunPythonTool(BaseTool):
    """
    Tool for running Python code.
    Strategy: Write code to a temporary file -> Execute via subprocess -> Cleanup.
    """

    def __init__(self, settings: Settings):
        super().__init__(settings)
        self.logger = logging.getLogger(__name__)
        self.workspace_root = Path(settings.workspace_root)
        self.scratch_dir = self.workspace_root / ".scratch" / "run_python"

    @property
    def name(self) -> str:
        return "run_python"

    @property
    def description(self) -> str:
        return "Execute Python code in a temporary script."

    @property
    def parameter_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "script_content": {
                    "type": "string",
                    "description": "The Python code to execute.",
                },
                "script_name": {
                    "type": "string",
                    "description": "Optional display name for the temp script file.",
                    "default": "temp_python_script.py",
                },
            },
            "required": ["script_content"],
        }

    @property
    def requires_confirmation(self) -> bool:
        # Python execution is high-risk; always request confirmation
        return True

    async def run(self, **kwargs) -> Any:
        content = kwargs.get("script_content")
        display_name = self._sanitize_script_name(
            kwargs.get("script_name", "temp_python_script.py")
        )

        if not content:
            raise ToolError(
                "Missing parameter 'script_content'",
                user_hint="Please provide Python code in 'script_content'.",
            )

        # 1. Write Script (Safely)
        file_path = self._write_temp_script(display_name, content)
        relative_script_path = file_path.relative_to(self.workspace_root)
        command_string = (
            f"{shlex.quote(sys.executable)} {shlex.quote(str(relative_script_path))}"
        )

        # 2. Execute Script
        try:
            result = await run_exec_command(
                [sys.executable, str(relative_script_path)],
                cwd=self.workspace_root,
                timeout_seconds=30,
            )
            result_output = build_process_output(
                result_type="command_execution",
                summary="Executed Python script successfully.",
                command=command_string,
                cwd=str(self.workspace_root),
                exit_code=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
                extra_data={
                    "description": "Executing temporary Python script.",
                    "timeout_seconds": 30,
                    "shell": False,
                },
                parse_json_streams=True,
            )
            if result.returncode != 0:
                raise ToolError(
                    f"Python script failed with exit code {result.returncode}",
                    user_hint=f"Python script failed (exit {result.returncode}).",
                    details={
                        "script_name": display_name,
                        "script_path": str(file_path),
                        "exit_code": result.returncode,
                        "stdout": result.stdout,
                        "stderr": result.stderr,
                    },
                )
            return build_tool_output(
                result_type="python_execution",
                summary=f"Executed Python script {display_name}.",
                data={
                    "script_name": display_name,
                    "script_path": str(file_path),
                    "python_executable": sys.executable,
                    **result_output["data"],
                },
                pagination=None,
            )

        finally:
            # 3. Cleanup
            self._cleanup(file_path)

    def _sanitize_script_name(self, name: str) -> str:
        label = Path(str(name or "").strip() or "temp_python_script.py").name
        return label or "temp_python_script.py"

    def _write_temp_script(self, display_name: str, content: str) -> Path:
        """Safely write content to workspace."""
        try:
            self.scratch_dir.mkdir(parents=True, exist_ok=True)
            suffix = Path(display_name).suffix or ".py"
            stem = Path(display_name).stem or "temp_python_script"
            safe_stem = "".join(
                char if char.isalnum() or char in {"_", "-"} else "_"
                for char in stem
            ).strip("_") or "temp_python_script"
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                suffix=suffix,
                prefix=f"{safe_stem}_",
                dir=self.scratch_dir,
                delete=False,
            ) as handle:
                handle.write(content)
                file_path = Path(handle.name)
            self.logger.info("Created temporary Python script: %s", file_path)
            return file_path
        except Exception as e:
            log_exception(self.logger, logging.ERROR, "Failed to write temp script", e)
            raise ToolError(
                f"Failed to write script '{display_name}'",
                user_hint=f"Could not write temporary script '{display_name}' in workspace.",
                details={"script_name": display_name, "error": str(e)},
            )

    def _cleanup(self, file_path: Path):
        """Remove the temporary file."""
        if file_path and file_path.exists():
            try:
                file_path.unlink()
                self.logger.info("Cleaned up temporary script: %s", file_path)
            except OSError as e:
                self.logger.warning("Failed to clean up script %s: %s", file_path, e)

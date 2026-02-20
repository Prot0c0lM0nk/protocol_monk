import sys
import logging
from pathlib import Path
from typing import Dict, Any

from protocol_monk.exceptions.tools import ToolError
from protocol_monk.tools.base import BaseTool
from protocol_monk.config.settings import Settings
# We delegate the actual shell execution to our existing robust tool
from protocol_monk.tools.shell_operations.execute_command_tool import ExecuteCommandTool

class RunPythonTool(BaseTool):
    """
    Tool for running Python code.
    Strategy: Write code to a temporary file -> Execute via subprocess -> Cleanup.
    """

    def __init__(self, settings: Settings):
        super().__init__(settings)
        self.logger = logging.getLogger(__name__)
        # Initialize the executor delegate with the same settings
        self.command_executor = ExecuteCommandTool(settings)

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
                    "description": "Optional name for the temp script file.",
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
        # Wrapper for async execution
        return self._execute_sync(**kwargs)

    def _execute_sync(self, **kwargs) -> str:
        content = kwargs.get("script_content")
        name = kwargs.get("script_name", "temp_python_script.py")

        if not content:
            raise ToolError(
                "Missing parameter 'script_content'",
                user_hint="Please provide Python code in 'script_content'.",
            )

        # 1. Write Script (Safely)
        file_path = self._write_temp_script(name, content)

        # 2. Execute Script
        try:
            # We use the current sys.executable to ensure we use the same python environment
            # (e.g., if you are in a venv, it uses that venv)
            command = f"{sys.executable} {file_path.name}"
            
            # Delegate to the ExecuteCommandTool
            # This re-uses the shell tool's logic for timeouts and capturing output
            result_output = self.command_executor._execute_sync(
                command=command, 
                description="Executing temporary Python script."
            )
            return result_output

        finally:
            # 3. Cleanup
            self._cleanup(file_path)

    def _write_temp_script(self, name: str, content: str) -> Path:
        """Safely write content to workspace."""
        try:
            # Use path_validator from BaseTool to ensure we don't write outside workspace
            # must_exist=False because we are creating it
            file_path = self.path_validator.validate_path(name, must_exist=False)
            
            file_path.write_text(content, encoding="utf-8")
            self.logger.info("Created temporary Python script: %s", file_path)
            return file_path
        except Exception as e:
            self.logger.error("Failed to write temp script: %s", e, exc_info=True)
            raise ToolError(
                f"Failed to write script '{name}'",
                user_hint=f"Could not write temporary script '{name}' in workspace.",
                details={"script_name": name, "error": str(e)},
            )

    def _cleanup(self, file_path: Path):
        """Remove the temporary file."""
        if file_path and file_path.exists():
            try:
                file_path.unlink()
                self.logger.info("Cleaned up temporary script: %s", file_path)
            except OSError as e:
                self.logger.warning("Failed to clean up script %s: %s", file_path, e)

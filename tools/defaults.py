"""Default runtime tool registration."""

from typing import Iterable

from protocol_monk.config.settings import Settings
from protocol_monk.tools.base import BaseTool
from protocol_monk.tools.file_operations.append_to_file_tool import AppendToFileTool
from protocol_monk.tools.file_operations.create_file_tool import CreateFileTool
from protocol_monk.tools.file_operations.delete_lines_tool import DeleteLinesTool
from protocol_monk.tools.file_operations.insert_in_file_tool import InsertInFileTool
from protocol_monk.tools.file_operations.read_file_tool import ReadFileTool
from protocol_monk.tools.file_operations.replace_lines_tool import ReplaceLinesTool
from protocol_monk.tools.registry import ToolRegistry
from protocol_monk.tools.shell_operations.execute_command_tool import (
    ExecuteCommandTool,
)
from protocol_monk.tools.shell_operations.git_operation_tool import GitOperationTool
from protocol_monk.tools.shell_operations.run_python_tool import RunPythonTool


def iter_default_tools(settings: Settings) -> Iterable[BaseTool]:
    """Build the default runtime tool set."""
    return (
        ReadFileTool(settings),
        CreateFileTool(settings),
        AppendToFileTool(settings),
        InsertInFileTool(settings),
        ReplaceLinesTool(settings),
        DeleteLinesTool(settings),
        ExecuteCommandTool(settings),
        RunPythonTool(settings),
        GitOperationTool(settings),
    )


def register_default_tools(registry: ToolRegistry, settings: Settings) -> None:
    """Register all runtime tools in deterministic order."""
    for tool in iter_default_tools(settings):
        registry.register(tool)

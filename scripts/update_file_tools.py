#!/usr/bin/env python3
"""
Update all file operations tools to use centralized path validator.
"""

import os
import re
from pathlib import Path

def update_file_tool(filepath: Path) -> bool:
    """Update a single file tool to use the centralized path validator."""
    
    content = filepath.read_text()
    
    # Check if already updated
    if "from tools.path_validator import PathValidator" in content:
        print(f"✅ {filepath.name} already updated")
        return True
    
    # Add PathValidator import after BaseTool import
    if "from tools.base import BaseTool, ExecutionStatus, ToolResult, ToolSchema" in content:
        content = content.replace(
            "from tools.base import BaseTool, ExecutionStatus, ToolResult, ToolSchema",
            "from tools.base import BaseTool, ExecutionStatus, ToolResult, ToolSchema\nfrom tools.path_validator import PathValidator"
        )
    
    # Add path_validator to __init__
    init_pattern = r"(def __init__\(self, working_dir: Path\):\n\s*super\(\).__init__\(working_dir\)\n\s*self\.logger = logging\.getLogger\(__name__\))"
    if re.search(init_pattern, content):
        content = re.sub(
            init_pattern,
            r"\1\n        self.path_validator = PathValidator(working_dir)",
            content
        )
    
    # Find and replace path cleaning logic
    path_cleaning_pattern = r"# Path Cleaning\s*str_cwd = str\(self\.working_dir\)\s*if str\(filepath\)\.startswith\(str_cwd\):\s*filepath = str\(filepath\)\[len\(str_cwd\) :\]\.lstrip\(os\.sep\)"
    
    if re.search(path_cleaning_pattern, content):
        # Replace with centralized path validator
        content = re.sub(
            path_cleaning_pattern,
            "# Use centralized path validator\n        cleaned_path, error = self.path_validator.validate_and_clean_path(filepath)\n        if error:\n            return ToolResult.security_blocked(f\"Invalid path: {error}\")\n            \n        filepath = cleaned_path",
            content
        )
        
        # Remove the old security check that comes after path cleaning
        security_check_pattern = r"if not self\._is_safe_file_path\(filepath\):\s*return [^,]*, ToolResult\.security_blocked\([^)]*\)"
        content = re.sub(security_check_pattern, "", content)
        
        # Add comment about path validation being handled
        content = re.sub(
            r"# 1\..*\n.*filepath.*",
            "# 1. Path validation handled in execute()\n        # Proceed with file operation",
            content
        )
    
    # Write updated content
    filepath.write_text(content)
    print(f"✅ Updated {filepath.name}")
    return True

def main():
    """Update all file operation tools."""
    tools_dir = Path("tools/file_operations")
    
    # List of tools to update (excluding __init__.py and auto_stage_large_content.py)
    tools_to_update = [
        "delete_lines_tool.py",
        "insert_in_file_tool.py", 
        "append_to_file_tool.py",
        "replace_lines_tool.py",
        "create_file_tool.py"
    ]
    
    for tool_name in tools_to_update:
        tool_path = tools_dir / tool_name
        if tool_path.exists():
            try:
                update_file_tool(tool_path)
            except Exception as e:
                print(f"❌ Failed to update {tool_name}: {e}")
        else:
            print(f"⚠️  {tool_name} not found")

if __name__ == "__main__":
    main()
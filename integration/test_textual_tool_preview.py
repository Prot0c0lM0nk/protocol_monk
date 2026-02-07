"""Tests for Textual tool preview builder."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ui.textual.tool_preview import build_tool_preview


def test_replace_lines_preview_resolves_scratch_and_shows_diff(tmp_path: Path):
    target = tmp_path / "target.py"
    target.write_text("line 1\nline old\nline 3\n", encoding="utf-8")

    scratch_dir = tmp_path / ".scratch"
    scratch_dir.mkdir(parents=True, exist_ok=True)
    (scratch_dir / "auto_123.txt").write_text("line new", encoding="utf-8")

    preview = build_tool_preview(
        "replace_lines",
        {
            "filepath": "target.py",
            "line_start": 2,
            "line_end": 2,
            "new_content_from_scratch": "auto_123",
        },
        str(tmp_path),
    )

    assert preview.syntax_hint == "diff"
    assert "resolved to" in preview.full_text
    assert "-line old" in preview.full_text
    assert "+line new" in preview.full_text


def test_execute_command_preview_renders_shell_command(tmp_path: Path):
    preview = build_tool_preview(
        "execute_command",
        {"command": "echo hello"},
        str(tmp_path),
    )
    assert preview.syntax_hint == "bash"
    assert "$ echo hello" in preview.full_text


def test_create_file_preview_infers_python_syntax():
    preview = build_tool_preview(
        "create_file",
        {"filepath": "demo.py", "content": "print('hello')"},
    )
    assert preview.syntax_hint == "python"
    assert "print('hello')" in preview.full_text

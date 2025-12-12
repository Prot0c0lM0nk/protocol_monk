# Test suite for file tracker functionality

import tempfile

import os
import pytest
from pathlib import Path

from agent.context.file_tracker import FileTracker
from agent.context.message import Message


class TestFileTracker:
    """Test suite for file tracking functionality"""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for testing"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def file_tracker(self, temp_dir):
        """Create a FileTracker instance for testing"""
        return FileTracker(temp_dir)

    @pytest.mark.asyncio
    async def test_track_file_shown_new_file(self, file_tracker):
        """Test tracking a new file as shown"""
        result = await file_tracker.track_file_shown("test_file.txt")
        assert result == 1
        assert "test_file.txt" in file_tracker.files_shown

    @pytest.mark.asyncio
    async def test_track_file_shown_existing_file(self, file_tracker):
        """Test tracking an already shown file"""
        # Track file first time
        result1 = await file_tracker.track_file_shown("test_file.txt")
        assert result1 == 1

        # Track same file second time
        result2 = await file_tracker.track_file_shown("test_file.txt")
        assert result2 == 0
        assert len(file_tracker.files_shown) == 1

    @pytest.mark.asyncio
    async def test_get_file_shown_count(self, file_tracker):
        """Test checking if a file has been shown"""
        # File not shown yet
        count = await file_tracker.get_file_shown_count("test_file.txt")
        assert count == 0

        # Track file as shown
        await file_tracker.track_file_shown("test_file.txt")

        # File now shown
        count = await file_tracker.get_file_shown_count("test_file.txt")
        assert count == 1

    def test_exact_path_match(self, file_tracker, temp_dir):
        """Test exact path matching to prevent false positives"""
        # Create test files
        test_file = temp_dir / "test.txt"

    def test_exact_path_match(self, file_tracker, temp_dir):
        """Test exact path matching to prevent false positives"""
        # Create test files
        test_file = temp_dir / "test.txt"
        test_file.write_text("content")

        # Test exact matching - should match when path is in text
        assert file_tracker._exact_path_match(str(test_file), f"File: {test_file}")

        # Test that it doesn't match completely different paths
        assert not file_tracker._exact_path_match(
            str(test_file), "File: /completely/different/path.txt"
        )

    @pytest.mark.asyncio
    async def test_replace_old_file_content(self, file_tracker, temp_dir):
        """Test replacing old file content with placeholder"""
        # Create a test file
        test_file = temp_dir / "test.txt"
        test_file.write_text("content")

        # Create conversation with multiple references to the same file
        long_content = "A" * 300  # Make it long enough to qualify for replacement
        messages = [
            Message(role="user", content=f"Content of {test_file}: {long_content}"),
            Message(role="assistant", content="I've processed that file"),
            Message(role="user", content=f"Content of {test_file}: {long_content}"),
            Message(role="assistant", content="I've processed that file again"),
        ]

        # Replace old content
        await file_tracker.replace_old_file_content(str(test_file), messages)

        # Check that only the newest occurrence remains
        assert messages[0].content == f"[File previously shown: {test_file}]"
        assert messages[1].content == "I've processed that file"
        assert messages[2].content == f"Content of {test_file}: {long_content}"
        assert messages[3].content == "I've processed that file again"

    def test_file_existence_validation(self, file_tracker, temp_dir):
        """Test that file operations validate existence"""
        # Test with existing file
        existing_file = temp_dir / "exists.txt"
        existing_file.write_text("content")
        assert file_tracker._validate_file_exists(str(existing_file))

        # Test with non-existing file
        non_existing_file = temp_dir / "does_not_exist.txt"
        assert not file_tracker._validate_file_exists(str(non_existing_file))

    @pytest.mark.asyncio
    async def test_clear_tracker(self, file_tracker):
        """Test clearing the tracker state"""
        # Add some files to tracker
        await file_tracker.track_file_shown("file1.txt")
        await file_tracker.track_file_shown("file2.txt")
        assert len(file_tracker.files_shown) == 2

    @pytest.mark.asyncio
    async def test_clear_tracker(self, file_tracker):
        """Test clearing the tracker state"""
        # Add some files to tracker
        await file_tracker.track_file_shown("file1.txt")
        await file_tracker.track_file_shown("file2.txt")
        assert len(file_tracker.files_shown) == 2

        # Clear tracker
        await file_tracker.clear()
        assert len(file_tracker.files_shown) == 0


if __name__ == "__main__":
    pytest.main([__file__])

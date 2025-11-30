# Test suite for JSON parser functionality

import pytest

from utils.json_parser import (
    JsonParsingError,
    extract_json_from_text,
    extract_json_with_feedback,
)


class TestJsonParser:
    """Test suite for JSON parsing functionality"""

    def test_extract_json_from_text_with_valid_fenced_blocks(self):
        """Test parsing valid JSON from fenced code blocks"""
        text = """Here is some JSON:
```json
{
  "name": "John",
  "age": 30
}
```
And more text."""

        objects, errors = extract_json_from_text(text)
        assert len(objects) == 1
        assert len(errors) == 0
        assert objects[0]["name"] == "John"
        assert objects[0]["age"] == 30

    def test_extract_json_from_text_with_invalid_fenced_blocks(self):
        """Test parsing invalid JSON from fenced code blocks returns errors"""
        text = """Here is some invalid JSON:
```json
{
  "name": "John",
  "age": 30,
}
```
And more text."""  # Trailing comma makes it invalid

        objects, errors = extract_json_from_text(text)
        assert len(objects) == 0
        assert len(errors) == 1
        assert isinstance(errors[0], JsonParsingError)

    def test_extract_json_from_text_with_multiple_fenced_blocks(self):
        """Test parsing multiple JSON objects from fenced code blocks"""
        text = """First object:
```json
{
  "id": 1,
  "name": "First"
}
```
Second object:
```json
{
  "id": 2,
  "name": "Second"
}
```
And more text."""

        objects, errors = extract_json_from_text(text)
        assert len(objects) == 2
        assert len(errors) == 0
        assert objects[0]["id"] == 1
        assert objects[1]["id"] == 2

    def test_extract_json_from_text_with_multiline_fenced_blocks(self):
        """Test parsing multiline JSON from fenced code blocks"""
        text = """Complex object:
```json
{
  "user": {
    "name": "John Doe",
    "address": {
      "street": "123 Main St",
      "city": "Anytown"
    },
    "hobbies": ["reading", "swimming"]
  },
  "timestamp": "2024-01-01T00:00:00Z"
}
```
"""

        objects, errors = extract_json_from_text(text)
        assert len(objects) == 1
        assert len(errors) == 0
        assert objects[0]["user"]["name"] == "John Doe"
        assert objects[0]["user"]["address"]["city"] == "Anytown"

    def test_extract_json_from_text_with_arrays(self):
        """Test parsing JSON arrays"""
        text = """Array of objects:
```json
[
  {
    "id": 1,
    "name": "First"
  },
  {
    "id": 2,
    "name": "Second"
  }
]
```
"""

        objects, errors = extract_json_from_text(text)
        assert len(objects) == 1  # Should return the array as one object
        assert len(errors) == 0
        assert isinstance(objects[0], list)
        assert len(objects[0]) == 2

    def test_extract_json_from_text_with_bracket_counting(self):
        """Test fallback bracket counting strategy"""
        text = 'Here is some JSON: {"name": "John", "age": 30} And more text.'

        objects, errors = extract_json_from_text(text)
        assert len(objects) == 1
        assert len(errors) == 0
        assert objects[0]["name"] == "John"
        assert objects[0]["age"] == 30

    def test_extract_json_from_text_with_invalid_bracket_counting(self):
        """Test bracket counting with invalid JSON returns errors"""
        text = 'Here is some invalid JSON: {"name": "John", "age": 30,} And more text.'  # Trailing comma

        objects, errors = extract_json_from_text(text)
        assert len(objects) == 0
        assert len(errors) == 1
        assert isinstance(errors[0], JsonParsingError)

    def test_extract_json_with_feedback_backward_compatibility(self):
        """Test that extract_json_with_feedback maintains backward compatibility"""
        text = """Here is some JSON:
```json
{
  "name": "John",
  "age": 30
}
```
And more text."""

        objects, success = extract_json_with_feedback(text)
        assert isinstance(objects, list)
        assert isinstance(success, bool)
        assert success == True
        assert len(objects) == 1
        assert objects[0]["name"] == "John"


if __name__ == "__main__":
    pytest.main([__file__])

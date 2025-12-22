# Semantic JSON Parser - Context-Aware JSON Extraction

import json
import re
from typing import List, Tuple, Optional, Dict, Any
import logging
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

class ContentType(Enum):
    """Types of content we might encounter in model responses."""
    JSON = "json"
    MARKDOWN = "markdown"
    CODE_BLOCK = "code_block"
    TABLE = "table"
    ASCII_ART = "ascii_art"
    PLAIN_TEXT = "plain_text"

@dataclass
class ContentBlock:
    """Represents a block of content with its type and metadata."""
    content: str
    content_type: ContentType
    start_pos: int
    end_pos: int
    metadata: Dict[str, Any] = None


class SemanticJSONParser:
    """Context-aware JSON parser that understands content structure.
    
    Instead of relying on complex regex patterns, this parser:
    1. Analyzes the semantic structure of the text
    2. Identifies different content types
    3. Extracts JSON using context-appropriate strategies
    4. Handles nested and mixed content gracefully
    """
    
    def __init__(self, max_attempts: int = 3):
        self.max_attempts = max_attempts
        self.json_indicators = [
            '{"action"', '"action":', '"parameters"',
            '{\"action\"', '\"action\":', '\"parameters\"'
        ]


    def extract_json_objects(self, text: str) -> Tuple[List[Dict], List[str]]:
        """Extract JSON objects using semantic analysis.
        
        Args:
            text: Input text potentially containing JSON objects
            
        Returns:
            Tuple of (valid_objects, error_messages)
        """
        errors = []
        
        # Stage 1: Analyze content structure
        content_blocks = self._analyze_content_structure(text)
        
        # Stage 2: Extract JSON from appropriate blocks
        json_candidates = self._identify_json_candidates(content_blocks)
        
        # Stage 3: Validate and extract JSON
        valid_objects = []
        for candidate in json_candidates:
            try:
                parsed = self._parse_json_candidate(candidate)
                if parsed and self._validate_tool_call(parsed):
                    valid_objects.append(parsed)
            except Exception as e:
                errors.append(f"Failed to parse candidate: {str(e)}")
        
        # Stage 4: Fallback extraction if needed
        if not valid_objects:
            fallback_objects, fallback_errors = self._fallback_extraction(text)
            valid_objects.extend(fallback_objects)
            errors.extend(fallback_errors)
        
        return valid_objects, errors
    def _analyze_content_structure(self, text: str) -> List[ContentBlock]:
        """
        Analyze text and identify different content types.

        Args:
            text: Input text to analyze

        Returns:
            List of ContentBlock objects
        """
        blocks = []
        position = 0

        # Identify code blocks first
        code_pattern = r'```(?:json|javascript|python)?\s*([\\s\\S]*?)\s*```'
        for match in re.finditer(code_pattern, text):
            # Add content before code block
            if match.start() > position:
                pre_content = text[position:match.start()]
                blocks.extend(self._analyze_plain_content(pre_content, position))

            # Add code block
            code_content = match.group(1)
            blocks.append(ContentBlock(
                content=code_content,
                content_type=ContentType.CODE_BLOCK,
                start_pos=match.start(),
                end_pos=match.end(),
                metadata={'language': self._detect_code_language(match.group(0))}
            ))

            position = match.end()

        # Add remaining content
        if position < len(text):
            remaining = text[position:]
            blocks.extend(self._analyze_plain_content(remaining, position))

        return blocks



    def _analyze_plain_content(self, text: str, start_pos: int) -> List[ContentBlock]:
        """Analyze plain text and identify content types."""
        blocks = []
        
        # Check for tables
        if self._is_table(text):
            blocks.append(ContentBlock(
                content=text,
                content_type=ContentType.TABLE,
                start_pos=start_pos,
                end_pos=start_pos + len(text)
            ))
        # Check for ASCII art
        elif self._is_ascii_art(text):
            blocks.append(ContentBlock(
                content=text,
                content_type=ContentType.ASCII_ART,
                start_pos=start_pos,
                end_pos=start_pos + len(text)
            ))
        else:
            blocks.append(ContentBlock(
                content=text,
                content_type=ContentType.PLAIN_TEXT,
                start_pos=start_pos,
                end_pos=start_pos + len(text)
            ))
        
        return blocks


    def _identify_json_candidates(self, blocks: List[ContentBlock]) -> List[str]:
        """Identify blocks that likely contain JSON."""
        candidates = []
        
        for block in blocks:
            # Code blocks are prime candidates
            if block.content_type == ContentType.CODE_BLOCK:
                candidates.append(block.content)
            
            # Check plain text for JSON indicators
            elif block.content_type == ContentType.PLAIN_TEXT:
                if self._has_json_indicators(block.content):
                    # Extract JSON-like structures from plain text
                    extracted = self._extract_json_from_text(block.content)
                    candidates.extend(extracted)
        
        return candidates


    def _has_json_indicators(self, text: str) -> bool:
        """Check if text contains indicators of JSON content."""
        return any(indicator in text for indicator in self.json_indicators)
    
    def _extract_json_from_text(self, text: str) -> List[str]:
        """Extract JSON-like structures from plain text."""
        candidates = []
        
        # Look for bracketed content
        bracket_pattern = r'\{[^{}]*\{[^{}]*\}[^{}]*\}'
        for match in re.finditer(bracket_pattern, text):
            candidates.append(match.group(0))
        
        # Look for complete JSON objects
        object_pattern = r'\{[^}]*"action"[^}]*\}'
        for match in re.finditer(object_pattern, text, re.IGNORECASE):
            candidates.append(match.group(0))
        
        return candidates


    def _parse_json_candidate(self, candidate: str) -> Optional[Dict]:
        """Parse a JSON candidate with intelligent error recovery."""
        try:
            # Try direct parsing first
            return json.loads(candidate)
        except json.JSONDecodeError:
            # Apply intelligent fixes
            fixed = self._intelligent_json_fix(candidate)
            try:
                return json.loads(fixed)
            except json.JSONDecodeError:
                return None


    def _intelligent_json_fix(self, text: str) -> str:
        """Apply intelligent fixes to malformed JSON."""
        # Remove common non-JSON artifacts
        text = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', text)
        
        # Fix quotes intelligently
        text = self._fix_quotes_intelligently(text)
        
        # Fix brackets
        text = self._fix_brackets_intelligently(text)
        
        # Remove trailing commas
        text = re.sub(r',\s*([}\]])', r'\1', text)
        
        return text
    def _fix_quotes_intelligently(self, text: str) -> str:
        """
        Fix quote usage based on context.

        This is more sophisticated than the regex approach.
        It analyzes each line and only fixes quotes in JSON-like
        contexts.
        """
        lines = text.split('\\n')
        fixed_lines = []

        for line in lines:
            # Skip lines that look like comments or non-JSON
            if line.strip().startswith('#') or '```' in line:
                fixed_lines.append(line)
                continue

            # Fix single quotes in JSON-like content
            if '{' in line and '}' in line:
                # Replace single quotes with double quotes for JSON keys/values
                line = re.sub(r"'([^']*)'", r'"\1"', line)

            fixed_lines.append(line)

        return '\\n'.join(fixed_lines)


    def _fix_brackets_intelligently(self, text: str) -> str:
        """Fix bracket matching intelligently using stack-based approach.
        
        This method tracks opening and closing brackets to ensure proper matching,
        rather than relying on simple counting.
        """
        stack = []
        fixed = []
        
        for char in text:
            if char in '{[':
                stack.append(char)
                fixed.append(char)
            elif char in '}]':
                if stack and ((char == '}' and stack[-1] == '{') or (char == ']' and stack[-1] == '[')):
                    stack.pop()
                    fixed.append(char)
                # Skip unmatched closing brackets
            else:
                fixed.append(char)
        
        # Add missing closing brackets
        while stack:
            closing = '}' if stack.pop() == '{' else ']'
            fixed.append(closing)
        
        return ''.join(fixed)


    def _validate_tool_call(self, obj: Any) -> bool:
        """Validate that an object is a proper tool call.
        
        Args:
            obj: Object to validate
            
        Returns:
            True if valid tool call, False otherwise
        """
        if not isinstance(obj, dict):
            return False
        
        # Check required fields
        if 'action' not in obj:
            return False
        
        if 'parameters' not in obj:
            return False
        
        if not isinstance(obj['parameters'], dict):
            return False
        
        # Optional reasoning field
        if 'reasoning' in obj and not isinstance(obj['reasoning'], str):
            return False
        
        return True


    def _fallback_extraction(self, text: str) -> Tuple[List[Dict], List[str]]:
        """Fallback extraction using pattern matching.
        
        This method is used when semantic parsing fails.
        It uses more aggressive pattern matching to find JSON-like structures.
        
        Args:
            text: Input text to parse
            
        Returns:
            Tuple of (found_objects, error_messages)
        """
        errors = []
        objects = []
        
        # Look for anything that looks like a tool call
        patterns = [
            r'\{\s*"action"\s*:\s*"[a-zA-Z_]+"',
            r'\{\s*\"action\"\s*:\s*\"[a-zA-Z_]+\"',
        ]
        
        for pattern in patterns:
            for match in re.finditer(pattern, text):
                try:
                    # Try to extract the complete object
                    start = match.start()
                    # Find the matching closing brace
                    brace_count = 0
                    end = start
                    for i, char in enumerate(text[start:], start):
                        if char == '{':
                            brace_count += 1
                        elif char == '}':
                            brace_count -= 1
                            if brace_count == 0:
                                end = i + 1
                                break
                    
                    candidate = text[start:end]
                    parsed = json.loads(candidate)
                    if self._validate_tool_call(parsed):
                        objects.append(parsed)
                except Exception as e:
                    errors.append(f"Fallback pattern failed: {str(e)}")
        
        return objects, errors


    # Helper methods for content type detection
    
    def _detect_code_language(self, code_block: str) -> str:
        """Detect the language of a code block.
        
        Args:
            code_block: The full code block including backticks
            
        Returns:
            Detected language string
        """
        if 'json' in code_block.lower():
            return 'json'
        elif 'python' in code_block.lower():
            return 'python'
        elif 'javascript' in code_block.lower():
            return 'javascript'
        else:
            return 'unknown'
    
    def _is_table(self, text: str) -> bool:
        """Check if text looks like a table.
        
        Args:
            text: Text to analyze
            
        Returns:
            True if text appears to be a table
        """
        lines = text.strip().split('\n')
        if len(lines) < 2:
            return False
        
        # Look for table-like patterns
        has_pipes = any('|' in line for line in lines)
        has_dashes = any('---' in line for line in lines)
        
        return has_pipes and has_dashes
    
    def _is_ascii_art(self, text: str) -> bool:
        """Check if text looks like ASCII art.
        
        Args:
            text: Text to analyze
            
        Returns:
            True if text appears to be ASCII art
        """
        # ASCII art typically has many non-alphanumeric characters
        special_chars = sum(1 for c in text if not c.isalnum() and not c.isspace())
        total_chars = len(text)
        
        return total_chars > 0 and (special_chars / total_chars) > 0.3
    def extract_json_semantically(text: str, max_attempts: int = 3) -> Tuple[List[Dict], List[str]]:
        """Extract JSON objects using semantic analysis.

        This is a
        convenience function that creates a SemanticJSONParser instance
        and extracts JSON
        objects from the given text.

        Args:
            text: Input text potentially
            containing JSON objects
            max_attempts: Maximum number of parsing attempts (default:
            3)

        Returns:
            Tuple of (valid_objects, error_messages)

        Example:
            >>> text = 'Here is the result: ```json{\"action\": \"read\",
            \"parameters\": {}}```'
            >>> objects, errors = extract_json_semantically(text)
            >>> print(objects[0]['action'])  # 'read'
        """
        parser = SemanticJSONParser(max_attempts=max_attempts)
        return parser.extract_json_objects(text)

# JSON Parser Factory - Centralized Parser Management

from typing import List, Tuple, Dict, Any
import logging
from .json_parser_v2 import JSONParserV2
from .semantic_json_parser import SemanticJSONParser

logger = logging.getLogger(__name__)

class JSONParserFactory:
    """Factory for creating and managing JSON parsers.
    
    This allows us to switch between different parsing strategies
    without breaking existing code.
    """
    
    # Parser types
    REGEX_PARSER = "regex"  # Original json_parser_v2
    SEMANTIC_PARSER = "semantic"  # New semantic parser
    
    # Default parser type (can be changed via environment or config)
    DEFAULT_PARSER = SEMANTIC_PARSER
    
    @classmethod
    def create_parser(cls, parser_type: str = None, **kwargs):
        """Create a JSON parser instance.
        
        Args:
            parser_type: Type of parser to create ('regex' or 'semantic')
            **kwargs: Additional arguments passed to parser constructor
            
        Returns:
            Parser instance with extract_json_objects method
        """
        if parser_type is None:
            parser_type = cls.DEFAULT_PARSER
        
        if parser_type == cls.REGEX_PARSER:
            return JSONParserV2(**kwargs)
        elif parser_type == cls.SEMANTIC_PARSER:
            return SemanticJSONParser(**kwargs)
        else:
            raise ValueError(f"Unknown parser type: {parser_type}")
    
    @classmethod
    def extract_json_with_fallback(cls, text: str, **kwargs) -> Tuple[List[Dict], List[str]]:
        """Extract JSON using semantic parser with regex fallback.
        
        This method tries the semantic parser first, then falls back
        to the regex parser if needed.
        
        Args:
            text: Input text to parse
            **kwargs: Arguments passed to parsers
            
        Returns:
            Tuple of (valid_objects, error_messages)
        """
        errors = []
        
        # Try semantic parser first
        try:
            semantic_parser = cls.create_parser(cls.SEMANTIC_PARSER, **kwargs)
            objects, semantic_errors = semantic_parser.extract_json_objects(text)
            
            if objects:
                return objects, semantic_errors
            else:
                errors.extend(semantic_errors)
        except Exception as e:
            errors.append(f"Semantic parser failed: {str(e)}")
        
        # Fallback to regex parser
        try:
            regex_parser = cls.create_parser(cls.REGEX_PARSER, **kwargs)
            objects, regex_errors = regex_parser.extract_json_objects(text)
            errors.extend(regex_errors)
            return objects, errors
        except Exception as e:
            errors.append(f"Regex parser failed: {str(e)}")
            return [], errors

# Convenience function for backward compatibility
def extract_json_with_retry(text: str, max_attempts: int = 3) -> Tuple[List[Dict], List[str]]:
    """Extract JSON objects using the default parser.
    
    This function maintains compatibility with the existing API
    while allowing us to switch parsers easily.
    
    Args:
        text: Input text potentially containing JSON objects
        max_attempts: Maximum number of parsing attempts
        
    Returns:
        Tuple of (valid_objects, error_messages)
    """
    factory = JSONParserFactory()
    return factory.extract_json_with_fallback(text, max_attempts=max_attempts)

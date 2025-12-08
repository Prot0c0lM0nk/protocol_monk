#!/usr/bin/env python3
"""
Configuration Exception Definitions for Protocol Monk

All configuration-related exceptions inherit from MonkBaseError.
"""

from exceptions.base import MonkBaseError


class ConfigFileError(MonkBaseError):
    """Raised when configuration files cannot be loaded or saved."""
    
    def __init__(self, message, file_path=None, operation=None):
        super().__init__(message)
        self.file_path = file_path
        self.operation = operation


class DirectorySelectionError(MonkBaseError):
    """Raised when directory selection fails or is invalid."""
    
    def __init__(self, message, directory_path=None):
        super().__init__(message)
        self.directory_path = directory_path


class ModelConfigError(MonkBaseError):
    """Raised when model configuration loading fails."""
    
    def __init__(self, message, config_file=None, original_error=None):
        super().__init__(message, original_error=original_error)
        self.config_file = config_file


class ValidationError(MonkBaseError):
    """Raised when configuration validation fails."""
    
    def __init__(self, message, field_name=None, invalid_value=None):
        super().__init__(message)
        self.field_name = field_name
        self.invalid_value = invalid_value

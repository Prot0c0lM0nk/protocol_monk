#!/usr/bin/env python3
"""
Enterprise Exception Hierarchy for MonkCode Agent

Provides structured error handling with clear categorization,
enabling proper error recovery, monitoring, and debugging in production.
"""

from typing import Optional, Dict, Any


class MonkBaseError(Exception):
    """
    Base exception for all MonkCode errors.
    Provides structured error data for observability and recovery.
    """
    
    def __init__(
        self, 
        message: str,
        error_code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        root_cause: Optional[Exception] = None
    ):
        super().__init__(message)
        self.message = message
        self.error_code = error_code or self.__class__.__name__
        self.details = details or {}
        self.root_cause = root_cause
        self.timestamp = self._get_timestamp()
    
    def _get_timestamp(self) -> float:
        """Get current timestamp for error tracking"""
        import time
        return time.time()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary for structured logging"""
        return {
            "error_type": self.__class__.__name__,
            "error_code": self.error_code,
            "message": self.message,
            "details": self.details,
            "timestamp": self.timestamp,
            "root_cause": str(self.root_cause) if self.root_cause else None
        }
    
    def __str__(self) -> str:
        """Human-readable error representation"""
        base = f"{self.__class__.__name__}: {self.message}"
        if self.error_code and self.error_code != self.__class__.__name__:
            base = f"[{self.error_code}] {base}"
        if self.details:
            base += f" | Details: {self.details}"
        return base


# =============================================================================
# PARSING ERRORS
# =============================================================================

class ParsingError(MonkBaseError):
    """Base class for parsing errors"""
    pass


class ParsingTimeoutError(ParsingError):
    """JSON parsing operation timed out"""

    def __init__(
        self,
        message: str,
        timeout_seconds: Optional[float] = None,
        **kwargs
    ):
        details = kwargs.pop('details', {})
        if timeout_seconds:
            details.update({"timeout_seconds": timeout_seconds})
        super().__init__(message, details=details, **kwargs)
        self.timeout_seconds = timeout_seconds


class SecurityValidationError(ParsingError):
    """Security validation failed during parsing"""

    def __init__(
        self,
        message: str,
        validation_type: Optional[str] = None,
        **kwargs
    ):
        details = kwargs.pop('details', {})
        if validation_type:
            details.update({"validation_type": validation_type})
        super().__init__(message, details=details, **kwargs)
        self.validation_type = validation_type


# =============================================================================
# MODEL & API ERRORS
# =============================================================================

class ModelAPIError(MonkBaseError):
    """Base class for model API related errors"""

    def __init__(
        self,
        message: str,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        status_code: Optional[int] = None,
        **kwargs
    ):
        details = kwargs.pop('details', {})
        details.update({
            "provider": provider,
            "model": model,
            "status_code": status_code
        })
        super().__init__(message, details=details, **kwargs)
        self.provider = provider
        self.model = model
        self.status_code = status_code


# Alias for backward compatibility
APIError = ModelAPIError


class EmptyResponseError(ModelAPIError):
    """Model returned empty response after retries"""
    
    def __init__(
        self,
        provider: str,
        model: str,
        retry_attempts: int = 0,
        **kwargs
    ):
        message = (
            f"Model {model} ({provider}) returned empty response "
            f"after {retry_attempts} retry attempts"
        )
        details = kwargs.pop('details', {})
        details.update({"retry_attempts": retry_attempts})
        super().__init__(message, provider=provider, model=model, details=details, **kwargs)


class ModelTimeoutError(ModelAPIError):
    """Model API request timed out"""
    
    def __init__(
        self,
        provider: str,
        model: str,
        timeout_seconds: float,
        **kwargs
    ):
        message = (
            f"Model {model} ({provider}) request timed out after {timeout_seconds}s"
        )
        details = kwargs.pop('details', {})
        details.update({"timeout_seconds": timeout_seconds})
        super().__init__(message, provider=provider, model=model, details=details, **kwargs)


class ModelRateLimitError(ModelAPIError):
    """Model API rate limit exceeded"""
    
    def __init__(
        self,
        provider: str,
        model: str,
        retry_after: Optional[int] = None,
        **kwargs
    ):
        message = f"Rate limit exceeded for {model} ({provider})"
        details = kwargs.pop('details', {})
        details.update({
            "retry_after": retry_after,
            "suggestion": "Implement exponential backoff or reduce request frequency"
        })
        super().__init__(message, provider=provider, model=model, details=details, **kwargs)


class ModelConfigurationError(ModelAPIError):
    """Model configuration is invalid or missing"""
    
    def __init__(
        self,
        provider: str,
        model: str,
        config_key: Optional[str] = None,
        **kwargs
    ):
        if config_key:
            message = f"Missing or invalid configuration for {model}: {config_key}"
        else:
            message = f"Invalid configuration for {model} ({provider})"
        
        details = kwargs.pop('details', {})
        details.update({"config_key": config_key})
        super().__init__(message, provider=provider, model=model, details=details, **kwargs)


# =============================================================================
# TOOL EXECUTION ERRORS
# =============================================================================

class ToolExecutionError(MonkBaseError):
    """Base class for tool execution errors"""
    
    def __init__(
        self,
        message: str,
        tool_name: Optional[str] = None,
        parameters: Optional[Dict[str, Any]] = None,
        **kwargs
    ):
        details = kwargs.pop('details', {})
        details.update({
            "tool_name": tool_name,
            "parameters": self._sanitize_parameters(parameters) if parameters else {}
        })
        super().__init__(message, details=details, **kwargs)
        self.tool_name = tool_name
        self.parameters = parameters
    
    def _sanitize_parameters(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Sanitize parameters for logging (remove sensitive data)"""
        sanitized = parameters.copy()
        sensitive_keys = ['password', 'api_key', 'token', 'secret', 'key']
        
        for key in list(sanitized.keys()):
            if any(sensitive in key.lower() for sensitive in sensitive_keys):
                sanitized[key] = '***REDACTED***'
        
        return sanitized


class ToolValidationError(ToolExecutionError):
    """Tool parameter validation failed"""
    
    def __init__(
        self,
        tool_name: str,
        validation_errors: list,
        parameters: Optional[Dict[str, Any]] = None,
        **kwargs
    ):
        message = f"Tool validation failed for {tool_name}: {', '.join(validation_errors)}"
        details = kwargs.pop('details', {})
        details.update({
            "validation_errors": validation_errors,
            "suggestion": "Check tool documentation for parameter requirements"
        })
        super().__init__(
            message, 
            tool_name=tool_name, 
            parameters=parameters, 
            details=details, 
            **kwargs
        )
        self.validation_errors = validation_errors


class ToolNotFoundError(ToolExecutionError):
    """Requested tool not found in registry"""
    
    def __init__(
        self,
        tool_name: str,
        available_tools: Optional[list] = None,
        **kwargs
    ):
        message = f"Tool not found: {tool_name}"
        details = kwargs.pop('details', {})
        details.update({
            "available_tools": available_tools or [],
            "suggestion": "Check tool registry or verify tool name spelling"
        })
        super().__init__(message, tool_name=tool_name, details=details, **kwargs)
        self.available_tools = available_tools


class ToolSecurityError(ToolExecutionError):
    """Tool execution blocked by security policy"""
    
    def __init__(
        self,
        tool_name: str,
        security_reason: str,
        parameters: Optional[Dict[str, Any]] = None,
        **kwargs
    ):
        message = f"Security violation in {tool_name}: {security_reason}"
        details = kwargs.pop('details', {})
        details.update({
            "security_reason": security_reason,
            "suggestion": "Review security policies or request permission"
        })
        super().__init__(
            message, 
            tool_name=tool_name, 
            parameters=parameters, 
            details=details, 
            **kwargs
        )
        self.security_reason = security_reason


class ToolResourceError(ToolExecutionError):
    """Tool exceeded resource limits"""
    
    def __init__(
        self,
        tool_name: str,
        resource_type: str,
        limit: Any,
        actual: Any,
        **kwargs
    ):
        message = f"Tool {tool_name} exceeded {resource_type} limit: {actual} > {limit}"
        details = kwargs.pop('details', {})
        details.update({
            "resource_type": resource_type,
            "limit": limit,
            "actual": actual
        })
        super().__init__(message, tool_name=tool_name, details=details, **kwargs)
        self.resource_type = resource_type
        self.limit = limit
        self.actual = actual
        self.actual = actual


class UserCancellationError(MonkBaseError):
    """User cancelled an operation, typically by rejecting a tool call"""
    
    def __init__(self, message: str = "Operation cancelled by user", **kwargs):
        super().__init__(message, **kwargs)


# =============================================================================
# CONTEXT & MEMORY ERRORS
# =============================================================================

class ContextError(MonkBaseError):
    """Base class for context management errors"""
    pass


class ContextOverflowError(ContextError):
    """Context token limit exceeded"""
    
    def __init__(
        self,
        current_tokens: int,
        max_tokens: int,
        **kwargs
    ):
        message = f"Context overflow: {current_tokens}/{max_tokens} tokens"
        details = kwargs.pop('details', {})
        details.update({
            "current_tokens": current_tokens,
            "max_tokens": max_tokens,
            "suggestion": "Implement conversation pruning or increase token limit"
        })
        super().__init__(message, details=details, **kwargs)
        self.current_tokens = current_tokens
        self.max_tokens = max_tokens


class ContextCorruptionError(ContextError):
    """Context data structure corrupted"""
    
    def __init__(
        self,
        corruption_type: str,
        recovery_attempted: bool = False,
        **kwargs
    ):
        message = f"Context corruption detected: {corruption_type}"
        details = kwargs.pop('details', {})
        details.update({
            "corruption_type": corruption_type,
            "recovery_attempted": recovery_attempted,
            "suggestion": "Enable context validation and recovery mechanisms"
        })
        super().__init__(message, details=details, **kwargs)
        self.corruption_type = corruption_type
        self.recovery_attempted = recovery_attempted


class MemoryError(MonkBaseError):
    """Base class for working memory errors"""
    pass


class MemoryLimitError(MemoryError):
    """Working memory size limit exceeded"""
    
    def __init__(
        self,
        current_items: int,
        max_items: int,
        **kwargs
    ):
        message = f"Memory limit exceeded: {current_items}/{max_items} items"
        details = kwargs.pop('details', {})
        details.update({
            "current_items": current_items,
            "max_items": max_items,
            "suggestion": "Implement LRU eviction or increase memory limit"
        })
        super().__init__(message, details=details, **kwargs)
        self.current_items = current_items
        self.max_items = max_items


# =============================================================================
# SECURITY & AUTHORIZATION ERRORS
# =============================================================================

class SecurityViolationError(MonkBaseError):
    """Security policy violation detected"""
    
    def __init__(
        self,
        violation_type: str,
        resource: Optional[str] = None,
        severity: str = "medium",
        **kwargs
    ):
        message = f"Security violation: {violation_type}"
        if resource:
            message += f" on {resource}"
            
        details = kwargs.pop('details', {})
        details.update({
            "violation_type": violation_type,
            "resource": resource,
            "severity": severity
        })
        super().__init__(message, details=details, **kwargs)
        self.violation_type = violation_type
        self.resource = resource
        self.severity = severity


class AuthenticationError(MonkBaseError):
    """Authentication failed"""
    
    def __init__(
        self,
        service: str,
        reason: str,
        **kwargs
    ):
        message = f"Authentication failed for {service}: {reason}"
        details = kwargs.pop('details', {})
        details.update({
            "service": service,
            "reason": reason,
            "suggestion": "Check credentials and authentication configuration"
        })
        super().__init__(message, details=details, **kwargs)
        self.service = service
        self.reason = reason


# =============================================================================
# CIRCUIT BREAKER & RESILIENCE ERRORS
# =============================================================================

class CircuitBreakerError(MonkBaseError):
    """Circuit breaker prevented operation execution"""

    def __init__(
        self,
        service: str = "unknown",
        state: str = "OPEN",
        failure_count: int = 0,
        message: Optional[str] = None,
        **kwargs
    ):
        if message is None:
            message = f"Circuit breaker {state} for {service}"
        details = kwargs.pop('details', {})
        details.update({
            "service": service,
            "state": state,
            "failure_count": failure_count,
            "suggestion": "Wait for circuit to close or check service health"
        })
        super().__init__(message, details=details, **kwargs)
        self.service = service
        self.state = state
        self.failure_count = failure_count


# Alias for backward compatibility
class CircuitBreakerOpenError(CircuitBreakerError):
    """Alias for CircuitBreakerError when circuit is open"""

    def __init__(self, message: str = "Circuit breaker is OPEN", **kwargs):
        super().__init__(message=message, state="OPEN", **kwargs)


class RetryExhaustedError(MonkBaseError):
    """All retry attempts exhausted"""
    
    def __init__(
        self,
        operation: str,
        max_retries: int,
        last_error: Optional[str] = None,
        **kwargs
    ):
        message = f"Retry exhausted for {operation} after {max_retries} attempts"
        if last_error:
            message += f". Last error: {last_error}"
            
        details = kwargs.pop('details', {})
        details.update({
            "operation": operation,
            "max_retries": max_retries,
            "last_error": last_error,
            "suggestion": "Investribute root cause or increase retry limit"
        })
        super().__init__(message, details=details, **kwargs)
        self.operation = operation
        self.max_retries = max_retries
        self.last_error = last_error


# =============================================================================
# CONFIGURATION & DEPLOYMENT ERRORS
# =============================================================================

class ConfigurationError(MonkBaseError):
    """Configuration is invalid or missing"""
    
    def __init__(
        self,
        config_key: str,
        expected_type: Optional[str] = None,
        actual_value: Any = None,
        **kwargs
    ):
        message = f"Invalid configuration for {config_key}"
        if expected_type and actual_value is not None:
            message += f". Expected {expected_type}, got {type(actual_value).__name__}"
            
        details = kwargs.pop('details', {})
        details.update({
            "config_key": config_key,
            "expected_type": expected_type,
            "actual_value": str(actual_value) if actual_value is not None else None,
            "suggestion": "Check environment variables and configuration files"
        })
        super().__init__(message, details=details, **kwargs)
        self.config_key = config_key
        self.expected_type = expected_type
        self.actual_value = actual_value


class EnvironmentError(MonkBaseError):
    """Environment setup or dependency error"""
    
    def __init__(
        self,
        dependency: str,
        issue: str,
        **kwargs
    ):
        message = f"Environment issue with {dependency}: {issue}"
        details = kwargs.pop('details', {})
        details.update({
            "dependency": dependency,
            "issue": issue,
            "suggestion": "Check installation and dependency versions"
        })
        super().__init__(message, details=details, **kwargs)
        self.dependency = dependency
        self.issue = issue


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def wrap_exception(
    func: callable,
    exception_class: type,
    error_message: Optional[str] = None,
    **error_kwargs
) -> callable:
    """
    Decorator to wrap exceptions with specific exception class.
    
    Usage:
        @wrap_exception(ModelAPIError, "API call failed")
        def call_api():
            # function that might raise various exceptions
            pass
    """
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except MonkBaseError:
            # Don't wrap our own exceptions
            raise
        except Exception as e:
            message = error_message or f"Operation failed: {str(e)}"
            raise exception_class(message, root_cause=e, **error_kwargs) from e
    return wrapper


def safe_execute(
    func: callable,
    default_return: Any = None,
    log_error: bool = True,
    **kwargs
) -> Any:
    """
    Safely execute a function and return default value on exception.
    
    Args:
        func: Function to execute safely
        default_return: Value to return on exception
        log_error: Whether to log the error
        **kwargs: Additional arguments for func
    
    Returns:
        Function result or default_return on exception
    """
    try:
        return func(**kwargs)
    except Exception as e:
        if log_error:
            # Import here to avoid circular imports
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Safe execute caught exception: {e}")
        return default_return


# Export commonly used exceptions for easy importing
__all__ = [
    # Base
    'MonkBaseError',

    # Parsing
    'ParsingError',
    'ParsingTimeoutError',
    'SecurityValidationError',

    # Model & API
    'ModelAPIError',
    'APIError',  # Alias
    'EmptyResponseError',
    'ModelTimeoutError',
    'ModelRateLimitError',
    'ModelConfigurationError',

    # Tool Execution
    'ToolExecutionError',
    'ToolValidationError',
    'ToolNotFoundError',
    'ToolSecurityError',
    'ToolResourceError',
    'UserCancellationError',

    # Context & Memory
    'ContextError',
    'ContextOverflowError',
    'ContextCorruptionError',
    'MemoryError',
    'MemoryLimitError',

    # Security
    'SecurityViolationError',
    'AuthenticationError',

    # Resilience
    'CircuitBreakerError',
    'CircuitBreakerOpenError',  # Alias
    'RetryExhaustedError',

    # Configuration
    'ConfigurationError',
    'EnvironmentError',

    # Utilities
    'wrap_exception',
    'safe_execute'
]
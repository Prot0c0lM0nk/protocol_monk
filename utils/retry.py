"""
Retry utility for handling transient errors in model interactions.
"""

from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from exceptions.model import ModelTimeoutError, ModelRateLimitError
import aiohttp
import asyncio


def retry_on_transient_errors(max_attempts=3):
    """
    Decorator to retry functions on transient errors.
    
    Retries on:
    - ModelTimeoutError: When model requests timeout
    - ModelRateLimitError: When rate limits are hit
    - aiohttp.ClientError: For HTTP client errors
    - asyncio.TimeoutError: For general timeouts
    
    Args:
        max_attempts: Maximum number of retry attempts (default: 3)
    
    Returns:
        Decorated function with exponential backoff retry logic
    """
    return retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(
            (ModelTimeoutError, ModelRateLimitError, aiohttp.ClientError, asyncio.TimeoutError)
        ),
        reraise=True
    )
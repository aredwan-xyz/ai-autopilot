"""Retry utilities with exponential backoff."""
from __future__ import annotations
import asyncio
import functools
from typing import Callable, Type
import structlog

logger = structlog.get_logger("retry")


def with_retry(
    retries: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: tuple[Type[Exception], ...] = (Exception,),
):
    """Decorator: retry async functions with exponential backoff."""
    def decorator(func: Callable):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            last_exc = None
            wait = delay
            for attempt in range(1, retries + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exc = e
                    if attempt < retries:
                        logger.warning(
                            "retry_attempt",
                            func=func.__name__,
                            attempt=attempt,
                            wait=wait,
                            error=str(e),
                        )
                        await asyncio.sleep(wait)
                        wait *= backoff
            raise last_exc
        return wrapper
    return decorator

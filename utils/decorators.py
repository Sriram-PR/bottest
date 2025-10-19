"""
Reusable decorators for the bot
"""

import asyncio
import logging
from functools import wraps
from typing import Callable, Optional, Type, Union

import aiohttp
from discord.ext import commands

from utils.constants import (
    DEFAULT_RETRY_ATTEMPTS,
    RETRY_BASE_DELAY,
    RETRY_MAX_DELAY,
)

logger = logging.getLogger("smogon_bot.decorators")


def retry_on_error(
    max_retries: int = DEFAULT_RETRY_ATTEMPTS,
    exceptions: Union[Type[Exception], tuple] = (
        aiohttp.ClientError,
        asyncio.TimeoutError,
    ),
    base_delay: float = RETRY_BASE_DELAY,
    max_delay: float = RETRY_MAX_DELAY,
):
    """
    Decorator to retry async functions on specific exceptions with exponential backoff

    Args:
        max_retries: Maximum number of retry attempts
        exceptions: Exception types to catch and retry
        base_delay: Base delay in seconds for exponential backoff
        max_delay: Maximum delay between retries

    Usage:
        @retry_on_error(max_retries=3)
        async def fetch_data():
            ...
    """

    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None

            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e

                    if attempt == max_retries - 1:
                        logger.error(
                            f"{func.__name__} failed after {max_retries} attempts: {e}"
                        )
                        raise

                    # Calculate delay with exponential backoff
                    delay = min(base_delay * (2**attempt), max_delay)

                    logger.warning(
                        f"{func.__name__} attempt {attempt + 1}/{max_retries} failed: {e}. "
                        f"Retrying in {delay:.1f}s..."
                    )

                    await asyncio.sleep(delay)

            # This should never be reached, but just in case
            if last_exception:
                raise last_exception

        return wrapper

    return decorator


def log_command_usage(func: Callable):
    """
    Decorator to log command usage

    Usage:
        @log_command_usage
        async def smogon(ctx, pokemon):
            ...
    """

    @wraps(func)
    async def wrapper(*args, **kwargs):
        # Get context from args
        ctx = args[1] if len(args) > 1 else kwargs.get("ctx")

        if ctx:
            logger.info(
                f"Command '{func.__name__}' used by {ctx.author} (ID: {ctx.author.id}) "
                f"in guild: {ctx.guild.name if ctx.guild else 'DM'}"
            )

        return await func(*args, **kwargs)

    return wrapper


def hybrid_defer(func: Callable):
    """
    Decorator to handle defer/typing logic for hybrid commands

    This eliminates code duplication by centralizing the defer pattern.
    For slash commands: shows "thinking..." status
    For prefix commands: shows typing indicator

    Usage:
        @hybrid_defer
        async def _process_smogon_command(self, ctx, pokemon, generation, tier):
            # Your command logic here
            ...
    """

    @wraps(func)
    async def wrapper(self, ctx: commands.Context, *args, **kwargs):
        # Check if this is a slash command or prefix command
        if ctx.interaction:
            # Slash command - defer the response
            await ctx.defer()
            # Execute the actual command logic
            return await func(self, ctx, *args, **kwargs)
        else:
            # Prefix command - show typing indicator
            async with ctx.typing():
                return await func(self, ctx, *args, **kwargs)

    return wrapper


class CircuitBreaker:
    """
    Circuit breaker pattern to prevent cascading failures

    Usage:
        breaker = CircuitBreaker(failure_threshold=5, recovery_timeout=60)

        @breaker
        async def risky_operation():
            ...
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60,
        expected_exception: Type[Exception] = Exception,
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception

        self.failure_count = 0
        self.last_failure_time: Optional[float] = None
        self.state = "closed"  # closed, open, half_open

    def __call__(self, func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            if self.state == "open":
                # Check if we should try recovery
                import time

                if time.time() - self.last_failure_time >= self.recovery_timeout:
                    logger.info(
                        f"Circuit breaker entering half-open state for {func.__name__}"
                    )
                    self.state = "half_open"
                else:
                    raise Exception(f"Circuit breaker is OPEN for {func.__name__}")

            try:
                result = await func(*args, **kwargs)

                # Success - reset failure count
                if self.state == "half_open":
                    logger.info(f"Circuit breaker closing for {func.__name__}")
                    self.state = "closed"
                    self.failure_count = 0

                return result

            except self.expected_exception:
                self.failure_count += 1

                import time

                self.last_failure_time = time.time()

                if self.failure_count >= self.failure_threshold:
                    logger.error(
                        f"Circuit breaker OPENING for {func.__name__} "
                        f"after {self.failure_count} failures"
                    )
                    self.state = "open"

                raise

        return wrapper

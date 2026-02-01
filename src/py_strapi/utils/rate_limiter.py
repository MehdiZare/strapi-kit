"""Rate limiting utilities using token bucket algorithm.

Provides both synchronous and asynchronous rate limiters to control
request rates when communicating with the Strapi API.
"""

import asyncio
import logging
import threading
import time

logger = logging.getLogger(__name__)


class TokenBucketRateLimiter:
    """Synchronous rate limiter using token bucket algorithm.

    The token bucket algorithm allows bursting up to the bucket capacity
    while maintaining the specified average rate over time.

    Example:
        >>> limiter = TokenBucketRateLimiter(rate=5.0)  # 5 requests per second
        >>> for _ in range(10):
        ...     limiter.acquire()
        ...     # make_request()
    """

    def __init__(
        self,
        rate: float,
        capacity: float | None = None,
    ) -> None:
        """Initialize the rate limiter.

        Args:
            rate: Maximum requests per second
            capacity: Bucket capacity (defaults to rate for 1 second burst)
        """
        if rate <= 0:
            raise ValueError("Rate must be positive")

        self._rate = rate
        self._capacity = capacity if capacity is not None else rate
        self._tokens = self._capacity
        self._last_update = time.monotonic()
        self._lock = threading.Lock()

        logger.debug(f"Rate limiter initialized: {rate}/s, capacity: {self._capacity}")

    def acquire(self, tokens: float = 1.0, blocking: bool = True) -> bool:
        """Acquire tokens from the bucket.

        Args:
            tokens: Number of tokens to acquire (default: 1)
            blocking: Whether to block until tokens are available (default: True)

        Returns:
            True if tokens were acquired, False if non-blocking and not available
        """
        with self._lock:
            while True:
                self._refill()

                if self._tokens >= tokens:
                    self._tokens -= tokens
                    return True

                if not blocking:
                    return False

                # Calculate wait time until enough tokens are available
                tokens_needed = tokens - self._tokens
                wait_time = tokens_needed / self._rate

                # Release lock while sleeping
                self._lock.release()
                try:
                    time.sleep(wait_time)
                finally:
                    self._lock.acquire()

    def _refill(self) -> None:
        """Refill tokens based on elapsed time."""
        now = time.monotonic()
        elapsed = now - self._last_update
        self._last_update = now

        # Add tokens based on elapsed time
        self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)

    @property
    def available_tokens(self) -> float:
        """Get current available tokens."""
        with self._lock:
            self._refill()
            return self._tokens


class AsyncTokenBucketRateLimiter:
    """Asynchronous rate limiter using token bucket algorithm.

    The token bucket algorithm allows bursting up to the bucket capacity
    while maintaining the specified average rate over time.

    Example:
        >>> limiter = AsyncTokenBucketRateLimiter(rate=5.0)  # 5 requests per second
        >>> for _ in range(10):
        ...     await limiter.acquire()
        ...     # await make_request()
    """

    def __init__(
        self,
        rate: float,
        capacity: float | None = None,
    ) -> None:
        """Initialize the rate limiter.

        Args:
            rate: Maximum requests per second
            capacity: Bucket capacity (defaults to rate for 1 second burst)
        """
        if rate <= 0:
            raise ValueError("Rate must be positive")

        self._rate = rate
        self._capacity = capacity if capacity is not None else rate
        self._tokens = self._capacity
        self._last_update = time.monotonic()
        self._lock = asyncio.Lock()

        logger.debug(f"Async rate limiter initialized: {rate}/s, capacity: {self._capacity}")

    async def acquire(self, tokens: float = 1.0, blocking: bool = True) -> bool:
        """Acquire tokens from the bucket.

        Args:
            tokens: Number of tokens to acquire (default: 1)
            blocking: Whether to block until tokens are available (default: True)

        Returns:
            True if tokens were acquired, False if non-blocking and not available
        """
        async with self._lock:
            while True:
                self._refill()

                if self._tokens >= tokens:
                    self._tokens -= tokens
                    return True

                if not blocking:
                    return False

                # Calculate wait time until enough tokens are available
                tokens_needed = tokens - self._tokens
                wait_time = tokens_needed / self._rate

                # Release lock while sleeping
                self._lock.release()
                try:
                    await asyncio.sleep(wait_time)
                finally:
                    await self._lock.acquire()

    def _refill(self) -> None:
        """Refill tokens based on elapsed time."""
        now = time.monotonic()
        elapsed = now - self._last_update
        self._last_update = now

        # Add tokens based on elapsed time
        self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)

    @property
    def available_tokens(self) -> float:
        """Get current available tokens (requires holding the lock)."""
        # Note: This is not thread-safe without holding the lock
        self._refill()
        return self._tokens


def create_rate_limiter(
    rate_per_second: float | None,
    async_mode: bool = False,
) -> TokenBucketRateLimiter | AsyncTokenBucketRateLimiter | None:
    """Factory function to create appropriate rate limiter.

    Args:
        rate_per_second: Rate limit (None to disable)
        async_mode: Whether to create async limiter

    Returns:
        Rate limiter instance or None if rate is None
    """
    if rate_per_second is None:
        return None

    if async_mode:
        return AsyncTokenBucketRateLimiter(rate=rate_per_second)
    return TokenBucketRateLimiter(rate=rate_per_second)

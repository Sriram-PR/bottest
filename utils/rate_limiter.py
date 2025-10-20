"""
Global rate limiting system for preventing user spam
"""

import logging
import time
from collections import defaultdict
from typing import Dict, List, Tuple

logger = logging.getLogger("smogon_bot.rate_limiter")


class UserRateLimiter:
    """
    Global rate limiter that tracks user requests across all channels and commands

    Features:
    - Per-user request tracking
    - Sliding window algorithm
    - Automatic cleanup of old requests
    - Violation tracking
    - Statistics for monitoring

    Example:
        limiter = UserRateLimiter(max_requests=10, window=60)

        if not limiter.is_allowed(user_id):
            time_left = limiter.get_time_until_reset(user_id)
            await ctx.send(f"Rate limited! Try again in {time_left:.1f}s")
            return
    """

    def __init__(self, max_requests: int = 15, window: int = 60):
        """
        Initialize rate limiter

        Args:
            max_requests: Maximum number of requests allowed in time window
            window: Time window in seconds
        """
        self.max_requests = max_requests
        self.window = window

        # Store timestamps of requests per user {user_id: [timestamp1, timestamp2, ...]}
        self.requests: Dict[int, List[float]] = defaultdict(list)

        # Track how many times each user was rate limited
        self.violations: Dict[int, int] = defaultdict(int)

        # Track total requests for stats
        self.total_requests = 0
        self.total_blocked = 0

        logger.info(
            f"Rate limiter initialized: {max_requests} requests per {window}s per user"
        )

    def is_allowed(self, user_id: int) -> bool:
        """
        Check if user is allowed to make a request

        Args:
            user_id: Discord user ID

        Returns:
            True if allowed, False if rate limited
        """
        now = time.time()
        self.total_requests += 1

        # Clean old requests outside the time window (sliding window)
        self.requests[user_id] = [
            req_time
            for req_time in self.requests[user_id]
            if now - req_time < self.window
        ]

        # Check if user exceeded limit
        if len(self.requests[user_id]) >= self.max_requests:
            self.violations[user_id] += 1
            self.total_blocked += 1

            # Log every 5th violation to avoid spam
            if self.violations[user_id] % 5 == 1:
                logger.warning(
                    f"User {user_id} rate limited "
                    f"({len(self.requests[user_id])} requests in {self.window}s) "
                    f"- Total violations: {self.violations[user_id]}"
                )

            return False

        # Allow request and record timestamp
        self.requests[user_id].append(now)
        return True

    def get_time_until_reset(self, user_id: int) -> float:
        """
        Get seconds until rate limit resets for user

        Args:
            user_id: Discord user ID

        Returns:
            Seconds until oldest request expires (0.0 if not rate limited)
        """
        if user_id not in self.requests or not self.requests[user_id]:
            return 0.0

        now = time.time()
        oldest_request = min(self.requests[user_id])
        time_remaining = self.window - (now - oldest_request)

        return max(0.0, time_remaining)

    def get_remaining_requests(self, user_id: int) -> int:
        """
        Get number of remaining requests for user in current window

        Args:
            user_id: Discord user ID

        Returns:
            Number of requests user can still make
        """
        now = time.time()

        # Clean old requests
        self.requests[user_id] = [
            req_time
            for req_time in self.requests[user_id]
            if now - req_time < self.window
        ]

        return max(0, self.max_requests - len(self.requests[user_id]))

    def get_user_info(self, user_id: int) -> Tuple[int, int, float]:
        """
        Get detailed info about user's rate limit status

        Args:
            user_id: Discord user ID

        Returns:
            Tuple of (requests_made, remaining_requests, time_until_reset)
        """
        remaining = self.get_remaining_requests(user_id)
        requests_made = self.max_requests - remaining
        time_left = self.get_time_until_reset(user_id)

        return requests_made, remaining, time_left

    def reset_user(self, user_id: int) -> bool:
        """
        Manually reset rate limit for a specific user

        Args:
            user_id: Discord user ID

        Returns:
            True if user was reset, False if user wasn't rate limited
        """
        had_data = user_id in self.requests or user_id in self.violations

        if user_id in self.requests:
            del self.requests[user_id]
        if user_id in self.violations:
            del self.violations[user_id]

        if had_data:
            logger.info(f"Rate limit manually reset for user {user_id}")

        return had_data

    def cleanup_expired(self):
        """
        Clean up expired data for all users (maintenance)
        Should be called periodically to prevent memory bloat
        """
        now = time.time()
        users_to_remove = []

        for user_id, timestamps in list(self.requests.items()):
            # Remove expired timestamps
            self.requests[user_id] = [t for t in timestamps if now - t < self.window]

            # If no active requests, remove user entirely
            if not self.requests[user_id]:
                users_to_remove.append(user_id)

        for user_id in users_to_remove:
            del self.requests[user_id]

        if users_to_remove:
            logger.debug(f"Cleaned up {len(users_to_remove)} inactive users")

    def get_stats(self) -> dict:
        """
        Get comprehensive rate limiter statistics

        Returns:
            Dictionary with statistics
        """
        now = time.time()

        # Count currently rate-limited users
        limited_users = 0
        for user_id, timestamps in self.requests.items():
            # Count active requests in current window
            active_requests = [t for t in timestamps if now - t < self.window]
            if len(active_requests) >= self.max_requests:
                limited_users += 1

        # Calculate block rate
        block_rate = (
            (self.total_blocked / self.total_requests * 100)
            if self.total_requests > 0
            else 0
        )

        return {
            "total_users_tracked": len(self.requests),
            "currently_limited": limited_users,
            "total_violations": sum(self.violations.values()),
            "max_requests": self.max_requests,
            "window": self.window,
            "total_requests": self.total_requests,
            "total_blocked": self.total_blocked,
            "block_rate": f"{block_rate:.1f}%",
        }

    def get_top_violators(self, limit: int = 5) -> List[Tuple[int, int]]:
        """
        Get users with most violations

        Args:
            limit: Number of top violators to return

        Returns:
            List of (user_id, violation_count) tuples
        """
        sorted_violations = sorted(
            self.violations.items(), key=lambda x: x[1], reverse=True
        )
        return sorted_violations[:limit]

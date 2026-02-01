#!/usr/bin/env python3
"""
Async Token Manager V2
======================
Background token estimation with caching and async recalculation.
No blocking operations in critical paths.
"""

from collections import OrderedDict
import asyncio
import logging
from collections import OrderedDict
from typing import List, Optional, Dict
from agent.context.message import Message
from utils.token_estimation import SmartTokenEstimator


class AsyncTokenManager:
    """
    Async token management with:
    - Background recalculation
    - Token caching
    - Non-blocking estimates
    """

    def __init__(
        self,
        max_tokens: int,
        tokenizer=None,
        model_family: str = "qwen"
    ):
        self.max_tokens = max_tokens
        self.total_tokens = 0
        self.logger = logging.getLogger(__name__)

        # Token cache for frequently estimated content (OrderedDict for LRU eviction)
        self._token_cache: OrderedDict[str, int] = OrderedDict()
        self._cache_hits = 0
        self._cache_misses = 0

        # Background recalculation
        self._recalc_needed = False
        self._background_task: asyncio.Task | None = None
        self._running = False

        # Initialize estimator
        try:
            self.estimator = SmartTokenEstimator(model_family=model_family)
            self.logger.info(
                f"AsyncTokenManager initialized with {model_family} model family"
            )
        except Exception as e:
            self.logger.warning(
                f"Failed to initialize estimator with {model_family}: {e}. "
                "Falling back to generic."
            )
            try:
                self.estimator = SmartTokenEstimator(model_family="generic")
            except Exception as fallback_error:
                self.logger.error(
                    f"Critical: All token estimation failed: {fallback_error}. "
                    "Using character-based fallback."
                )
                self.estimator = None

    async def start(self):
        """Start background token recalculation."""
        if self._running:
            return

        self._running = True
        self._background_task = asyncio.create_task(self._recalculation_loop())
        self.logger.info("AsyncTokenManager started")

    async def stop(self):
        """Stop background processing."""
        if not self._running:
            return

        self._running = False
        if self._background_task:
            self._background_task.cancel()
            try:
                await self._background_task
            except asyncio.CancelledError:
                pass
            self._background_task = None

        self.logger.info("AsyncTokenManager stopped")

    def estimate(self, text: str, use_cache: bool = True) -> int:
        """
        Estimate tokens for text.
        Uses cache if available to avoid expensive operations.
        """
        if not text:
            return 0

        # Use hash of full text as cache key to reduce collisions
        cache_key = f"{len(text)}:{hash(text)}"

        # Check cache with LRU behavior
        if use_cache and cache_key in self._token_cache:
            self._cache_hits += 1
            # Move to end to mark as recently used (LRU)
            self._token_cache.move_to_end(cache_key)
            return self._token_cache[cache_key]

        self._cache_misses += 1

        # Estimate
        if self.estimator is not None:
            try:
                tokens = self.estimator.estimate_tokens(text)
            except Exception as e:
                self.logger.warning(f"Token estimation failed: {e}")
                tokens = max(1, len(text) // 4)  # Fallback
        else:
            tokens = max(1, len(text) // 4)  # Fallback

        # Cache result with LRU eviction
        self._token_cache[cache_key] = tokens
        # Move to end (newest)
        self._token_cache.move_to_end(cache_key)

        # Evict oldest if over limit
        if len(self._token_cache) > 1000:
            self._token_cache.popitem(last=False)

        return tokens

    def add(self, tokens: int):
        """
        Add tokens to total.
        This is atomic and instant - no locks needed.
        """
        self.total_tokens += tokens
        self._recalc_needed = True

    def check_budget(self, new_tokens: int) -> bool:
        """
        Check if adding tokens would exceed budget.
        Non-blocking read of current state.
        """
        if self.max_tokens <= 0:
            return True  # Infinite budget

        pruning_threshold = int(self.max_tokens * 0.9)
        return (self.total_tokens + new_tokens) <= pruning_threshold

    async def request_recalculation(
        self,
        system_message: str,
        messages: List[Message]
    ):
        """
        Request background recalculation.
        Non-blocking - just sets a flag.
        """
        self._pending_system = system_message
        self._pending_messages = messages
        self._recalc_needed = True

    async def _recalculation_loop(self):
        """
        Background task that recalculates tokens periodically.
        Ensures accuracy without blocking main operations.
        """
        while self._running:
            try:
                # Wait for recalculation request or timeout
                await asyncio.sleep(0.5)  # Check every 500ms

                if self._recalc_needed and hasattr(self, '_pending_system'):
                    # Perform recalculation
                    running_total = 0

                    # System message
                    running_total += self.estimate(self._pending_system)

                    # Conversation
                    for msg in self._pending_messages:
                        if msg.content:
                            running_total += self.estimate(msg.content)

                    # Atomic update
                    old_total = self.total_tokens
                    self.total_tokens = running_total

                    self.logger.debug(
                        f"Token recalculation: {old_total} -> {self.total_tokens}"
                    )

                    self._recalc_needed = False

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in recalculation loop: {e}")

    def get_stats(self) -> Dict:
        """Get current statistics."""
        usage_percent = (
            (self.total_tokens / self.max_tokens) * 100
            if self.max_tokens > 0 else 0
        )

        return {
            "total_tokens": self.total_tokens,
            "max_tokens": self.max_tokens,
            "usage_percent": round(usage_percent, 2),
            "cache_hits": self._cache_hits,
            "cache_misses": self._cache_misses,
            "cache_size": len(self._token_cache),
            "recalc_needed": self._recalc_needed
        }

    def clear_cache(self):
        """Clear token cache."""
        self._token_cache.clear()
        self._cache_hits = 0
        self._cache_misses = 0
        self.logger.debug("Token cache cleared")
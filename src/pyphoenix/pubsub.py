"""Local PubSub implementation for PyPhoenix."""

import asyncio
from collections import defaultdict
from collections.abc import Callable
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class Subscription:
    """Represents a subscription to a topic."""

    def __init__(self, topic: str, callback: Callable, pubsub: "PubSub"):
        """
        Initialize a subscription.

        Args:
            topic: The topic being subscribed to
            callback: The callback function to invoke for messages
            pubsub: Reference to the PubSub instance
        """
        self.topic = topic
        self.callback = callback
        self.pubsub = pubsub
        self.active = True

    async def unsubscribe(self) -> None:
        """Unsubscribe from the topic."""
        if self.active:
            await self.pubsub.unsubscribe(self.topic, self.callback)
            self.active = False


class PubSub:
    """
    Local publish-subscribe system for inter-process communication.

    This is a simplified, single-node implementation that will later be extended
    for distributed operation.
    """

    def __init__(self):
        """Initialize the PubSub system."""
        self.subscriptions: dict[str, set[Callable]] = defaultdict(set)
        self.pattern_subscriptions: dict[str, set[Callable]] = defaultdict(set)
        self.lock = asyncio.Lock()

        logger.info("pubsub.initialized")

    async def subscribe(self, topic: str, callback: Callable) -> Subscription:
        """
        Subscribe to a topic.

        Args:
            topic: The topic to subscribe to (supports wildcards like "room:*")
            callback: The callback function to invoke for messages

        Returns:
            Subscription object that can be used to unsubscribe
        """
        async with self.lock:
            if "*" in topic:
                self.pattern_subscriptions[topic].add(callback)
                logger.debug(
                    "pubsub.pattern_subscribed",
                    topic=topic,
                    patterns=len(self.pattern_subscriptions),
                )
            else:
                self.subscriptions[topic].add(callback)
                logger.debug(
                    "pubsub.subscribed", topic=topic, subscribers=len(self.subscriptions[topic])
                )

        return Subscription(topic, callback, self)

    async def unsubscribe(self, topic: str, callback: Callable) -> None:
        """
        Unsubscribe from a topic.

        Args:
            topic: The topic to unsubscribe from
            callback: The callback function to remove
        """
        async with self.lock:
            if "*" in topic:
                self.pattern_subscriptions[topic].discard(callback)
                if not self.pattern_subscriptions[topic]:
                    del self.pattern_subscriptions[topic]
                logger.debug("pubsub.pattern_unsubscribed", topic=topic)
            else:
                self.subscriptions[topic].discard(callback)
                if not self.subscriptions[topic]:
                    del self.subscriptions[topic]
                logger.debug("pubsub.unsubscribed", topic=topic)

    async def publish(self, topic: str, message: Any) -> int:
        """
        Publish a message to all subscribers of a topic.

        Args:
            topic: The topic to publish to
            message: The message to send (can be any type)

        Returns:
            Number of subscribers that received the message
        """
        subscribers = set()

        async with self.lock:
            # Add direct topic subscribers
            if topic in self.subscriptions:
                subscribers.update(self.subscriptions[topic])

            # Add pattern subscribers that match
            for pattern in self.pattern_subscriptions:
                if self._matches_pattern(topic, pattern):
                    subscribers.update(self.pattern_subscriptions[pattern])

        # Notify all subscribers
        notification_count = 0
        for callback in subscribers:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(topic, message)
                else:
                    callback(topic, message)
                notification_count += 1
            except Exception as e:
                logger.error("pubsub.callback_error", topic=topic, error=str(e))

        logger.debug("pubsub.published", topic=topic, subscribers=notification_count)
        return notification_count

    async def direct_publish(self, node_id: str, topic: str, message: Any) -> None:
        """
        Publish directly to a specific node.

        For now, this is the same as regular publish since we only have one node.
        This method is a placeholder for future distributed functionality.

        Args:
            node_id: Target node identifier (ignored in local mode)
            topic: The topic to publish to
            message: The message to send
        """
        await self.publish(topic, message)

    def _matches_pattern(self, topic: str, pattern: str) -> bool:
        """
        Check if a topic matches a pattern.

        Currently supports simple wildcard matching with "*".

        Args:
            topic: The topic to check
            pattern: The pattern to match against

        Returns:
            True if the topic matches the pattern
        """
        if pattern == "*":
            return True

        if "*" not in pattern:
            return topic == pattern

        # Simple wildcard matching
        parts = pattern.split("*")
        if len(parts) != 2:
            # Only support one wildcard for now
            return False

        prefix, suffix = parts
        return topic.startswith(prefix) and topic.endswith(suffix)

    async def list_topics(self) -> list[str]:
        """
        List all active topics with subscribers.

        Returns:
            List of topic names
        """
        async with self.lock:
            return list(self.subscriptions.keys())

    async def subscriber_count(self, topic: str) -> int:
        """
        Get the number of subscribers for a topic.

        Args:
            topic: The topic to check

        Returns:
            Number of subscribers
        """
        async with self.lock:
            return len(self.subscriptions.get(topic, set()))

    async def shutdown(self) -> None:
        """Shutdown the PubSub system and clear all subscriptions."""
        async with self.lock:
            self.subscriptions.clear()
            self.pattern_subscriptions.clear()

        logger.info("pubsub.shutdown")


# Global PubSub instance for the local node
_local_pubsub: PubSub | None = None


def get_pubsub() -> PubSub:
    """Get or create the global PubSub instance."""
    global _local_pubsub
    if _local_pubsub is None:
        _local_pubsub = PubSub()
    return _local_pubsub

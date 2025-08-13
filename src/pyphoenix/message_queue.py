"""Message queue implementation with delivery guarantees for PyPhoenix."""

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import structlog

from .config import get_config
from .serializers import get_serializer_registry

logger = structlog.get_logger(__name__)


class MessageStatus(Enum):
    """Status of a message in the queue."""

    PENDING = "pending"
    PROCESSING = "processing"
    DELIVERED = "delivered"
    FAILED = "failed"
    EXPIRED = "expired"


@dataclass
class QueuedMessage:
    """A message in the queue with metadata."""

    id: str
    topic: str
    payload: Any
    created_at: float
    expires_at: float | None = None
    attempts: int = 0
    max_attempts: int = 3
    status: MessageStatus = MessageStatus.PENDING
    last_attempt_at: float | None = None
    error: str | None = None
    serialized_payload: bytes | None = field(default=None, repr=False)

    def is_expired(self) -> bool:
        """Check if the message has expired."""
        if self.expires_at is None:
            return False
        return time.time() > self.expires_at

    def can_retry(self) -> bool:
        """Check if the message can be retried."""
        return self.attempts < self.max_attempts and not self.is_expired()

    def mark_attempt(self, error: str | None = None) -> None:
        """Mark an attempt to deliver the message."""
        self.attempts += 1
        self.last_attempt_at = time.time()
        self.status = MessageStatus.PROCESSING
        if error:
            self.error = error
            if not self.can_retry():
                self.status = MessageStatus.FAILED

    def mark_delivered(self) -> None:
        """Mark the message as successfully delivered."""
        self.status = MessageStatus.DELIVERED

    def mark_failed(self, error: str) -> None:
        """Mark the message as failed."""
        self.status = MessageStatus.FAILED
        self.error = error


class MessageQueue:
    """
    Message queue with configurable delivery guarantees.

    Supports different delivery modes:
    - at_most_once: Fire and forget, no retries
    - at_least_once: Retry until delivered, may deliver duplicates
    - exactly_once: Deliver exactly once (requires deduplication)
    """

    def __init__(self, delivery_guarantee: str = "at_least_once"):
        self.delivery_guarantee = delivery_guarantee
        self.messages: dict[str, QueuedMessage] = {}
        self.topic_queues: dict[str, list[str]] = {}  # topic -> list of message IDs
        self.lock = asyncio.Lock()
        self.serializer_registry = get_serializer_registry()
        self.processing_task: asyncio.Task | None = None
        self.running = False

        # Deduplication for exactly_once delivery
        self.delivered_message_ids: set[str] = set()
        self.max_delivered_history = 10000

        logger.info("message_queue.initialized", delivery_guarantee=delivery_guarantee)

    async def start(self) -> None:
        """Start the message processing loop."""
        if self.running:
            return

        self.running = True
        self.processing_task = asyncio.create_task(self._processing_loop())
        logger.info("message_queue.started")

    async def stop(self) -> None:
        """Stop the message processing loop."""
        if not self.running:
            return

        self.running = False
        if self.processing_task:
            self.processing_task.cancel()
            try:
                await self.processing_task
            except asyncio.CancelledError:
                pass

        logger.info("message_queue.stopped")

    async def enqueue(
        self,
        topic: str,
        payload: Any,
        ttl: float | None = None,
        max_attempts: int | None = None,
    ) -> str:
        """
        Enqueue a message for delivery.

        Args:
            topic: The topic to publish to
            payload: The message payload
            ttl: Time to live in seconds (None for no expiry)
            max_attempts: Maximum delivery attempts (None for default)

        Returns:
            Message ID
        """
        config = get_config()
        message_id = str(uuid.uuid4())
        current_time = time.time()

        # Calculate expiry time
        expires_at = None
        if ttl is None:
            ttl = config.pubsub.message_ttl
        if ttl > 0:
            expires_at = current_time + ttl

        # Use default max attempts if not specified
        if max_attempts is None:
            max_attempts = 3 if self.delivery_guarantee != "at_most_once" else 1

        # Serialize payload
        serializer = self.serializer_registry.get_default()
        try:
            serialized_payload = serializer.serialize(payload)
        except Exception as e:
            logger.error("message_queue.serialization_error", error=str(e), payload=payload)
            raise

        # Create queued message
        message = QueuedMessage(
            id=message_id,
            topic=topic,
            payload=payload,
            created_at=current_time,
            expires_at=expires_at,
            max_attempts=max_attempts,
            serialized_payload=serialized_payload,
        )

        async with self.lock:
            self.messages[message_id] = message
            if topic not in self.topic_queues:
                self.topic_queues[topic] = []
            self.topic_queues[topic].append(message_id)

        logger.debug("message_queue.enqueued", message_id=message_id, topic=topic)
        return message_id

    async def get_pending_messages(self, topic: str | None = None) -> list[QueuedMessage]:
        """Get pending messages for processing."""
        async with self.lock:
            pending = []

            if topic:
                # Get messages for specific topic
                if topic in self.topic_queues:
                    for msg_id in self.topic_queues[topic]:
                        if msg_id in self.messages:
                            msg = self.messages[msg_id]
                            if msg.status == MessageStatus.PENDING and not msg.is_expired():
                                pending.append(msg)
            else:
                # Get all pending messages
                for message in self.messages.values():
                    if message.status == MessageStatus.PENDING and not message.is_expired():
                        pending.append(message)

            return sorted(pending, key=lambda m: m.created_at)

    async def mark_delivered(self, message_id: str) -> bool:
        """Mark a message as successfully delivered."""
        async with self.lock:
            if message_id not in self.messages:
                return False

            message = self.messages[message_id]
            message.mark_delivered()

            # For exactly_once delivery, track delivered messages
            if self.delivery_guarantee == "exactly_once":
                self.delivered_message_ids.add(message_id)
                # Limit history size
                if len(self.delivered_message_ids) > self.max_delivered_history:
                    # Remove oldest entries (simple implementation)
                    old_ids = list(self.delivered_message_ids)[:1000]
                    for old_id in old_ids:
                        self.delivered_message_ids.discard(old_id)

            logger.debug("message_queue.delivered", message_id=message_id)
            return True

    async def mark_failed(self, message_id: str, error: str) -> bool:
        """Mark a message delivery attempt as failed."""
        async with self.lock:
            if message_id not in self.messages:
                return False

            message = self.messages[message_id]
            message.mark_attempt(error)

            if message.status == MessageStatus.FAILED:
                logger.warning(
                    "message_queue.message_failed",
                    message_id=message_id,
                    attempts=message.attempts,
                    error=error,
                )

            return True

    async def is_duplicate(self, message_id: str) -> bool:
        """Check if a message has already been delivered (for exactly_once)."""
        if self.delivery_guarantee != "exactly_once":
            return False

        async with self.lock:
            return message_id in self.delivered_message_ids

    async def cleanup_expired(self) -> int:
        """Clean up expired and completed messages."""
        current_time = time.time()
        cleaned_count = 0

        async with self.lock:
            # Find expired and completed messages
            to_remove = []
            for msg_id, message in self.messages.items():
                should_remove = False

                if message.is_expired():
                    message.status = MessageStatus.EXPIRED
                    should_remove = True
                elif message.status in [
                    MessageStatus.DELIVERED,
                    MessageStatus.FAILED,
                    MessageStatus.EXPIRED,
                ]:
                    # Keep completed messages for a while for deduplication
                    age = current_time - message.created_at
                    if age > 3600:  # 1 hour
                        should_remove = True

                if should_remove:
                    to_remove.append(msg_id)

            # Remove messages
            for msg_id in to_remove:
                message = self.messages.pop(msg_id, None)
                if message:
                    # Remove from topic queues
                    if message.topic in self.topic_queues:
                        try:
                            self.topic_queues[message.topic].remove(msg_id)
                            if not self.topic_queues[message.topic]:
                                del self.topic_queues[message.topic]
                        except ValueError:
                            pass  # Already removed

                    cleaned_count += 1

        if cleaned_count > 0:
            logger.info("message_queue.cleanup", cleaned_count=cleaned_count)

        return cleaned_count

    async def get_stats(self) -> dict[str, Any]:
        """Get queue statistics."""
        async with self.lock:
            stats = {
                "total_messages": len(self.messages),
                "topics": len(self.topic_queues),
                "delivery_guarantee": self.delivery_guarantee,
                "status_counts": {},
            }

            # Count messages by status
            for message in self.messages.values():
                status = message.status.value
                stats["status_counts"][status] = stats["status_counts"].get(status, 0) + 1

            # Topic statistics
            stats["topic_stats"] = {}
            for topic, msg_ids in self.topic_queues.items():
                stats["topic_stats"][topic] = len(msg_ids)

            return stats

    async def _processing_loop(self) -> None:
        """Main processing loop for delivering messages."""
        logger.info("message_queue.processing_started")

        while self.running:
            try:
                # Get pending messages
                pending_messages = await self.get_pending_messages()

                if not pending_messages:
                    await asyncio.sleep(0.1)  # No messages, short sleep
                    continue

                # Process messages (in a real implementation, this would
                # interface with the PubSub system to deliver messages)
                for message in pending_messages:
                    try:
                        # Mark as processing
                        message.status = MessageStatus.PROCESSING

                        # For exactly_once, check for duplicates
                        if await self.is_duplicate(message.id):
                            await self.mark_delivered(message.id)
                            continue

                        # Simulate delivery (in real implementation, this would
                        # call the PubSub publish method)
                        await self._deliver_message(message)

                    except Exception as e:
                        await self.mark_failed(message.id, str(e))
                        logger.error(
                            "message_queue.delivery_error",
                            message_id=message.id,
                            error=str(e),
                        )

                # Clean up expired messages periodically
                if int(time.time()) % 60 == 0:  # Every minute
                    await self.cleanup_expired()

                await asyncio.sleep(0.1)  # Small delay between processing cycles

            except Exception as e:
                logger.error("message_queue.processing_error", error=str(e))
                await asyncio.sleep(1)  # Error recovery delay

    async def _deliver_message(self, message: QueuedMessage) -> None:
        """
        Deliver a message (placeholder for actual delivery logic).

        In a real implementation, this would interface with the PubSub
        system to deliver the message to subscribers.
        """
        # This is a placeholder - in the real implementation,
        # this would call the PubSub system
        logger.debug("message_queue.delivering", message_id=message.id, topic=message.topic)

        # Simulate delivery success/failure
        if message.attempts < 2:  # Simulate occasional failures
            await self.mark_delivered(message.id)
        else:
            raise Exception("Simulated delivery failure")

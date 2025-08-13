"""Presence tracking implementation for PyPhoenix."""

import asyncio
import time
from collections import defaultdict
from collections.abc import Callable
from typing import Any

import structlog

from .pubsub import get_pubsub
from .types import PresenceMeta, PresenceState

logger = structlog.get_logger(__name__)


class Presence:
    """
    Distributed presence tracking system.

    Tracks which processes/users are present on which topics across the system.
    This is a local implementation that will later be extended for distribution.
    """

    def __init__(self):
        """Initialize the Presence tracker."""
        self.presences: dict[str, dict[str, PresenceState]] = defaultdict(dict)
        self.callbacks: dict[str, list[Callable]] = {"join": [], "leave": []}
        self.pubsub = get_pubsub()
        self.lock = asyncio.Lock()

        logger.info("presence.initialized")

    async def track(self, pid: str, topic: str, meta: dict[str, Any]) -> None:
        """
        Track a process's presence on a topic.

        Args:
            pid: Process/user identifier
            topic: The topic to track presence on
            meta: Metadata about the presence (e.g., user info, online_at timestamp)
        """
        async with self.lock:
            presence_meta = PresenceMeta(
                online_at=meta.get("online_at", time.time()),
                user_id=meta.get("user_id"),
                metadata=meta.get("metadata"),
            )

            # Check if this is a new presence or update
            is_new = pid not in self.presences[topic]

            if is_new:
                # New presence
                self.presences[topic][pid] = PresenceState(metas=[presence_meta])
                logger.info("presence.joined", topic=topic, pid=pid, meta=meta)

                # Notify join callbacks
                await self._notify_callbacks("join", topic, pid, self.presences[topic][pid])

                # Publish presence_diff event
                await self._publish_presence_diff(
                    topic, {"joins": {pid: self.presences[topic][pid]}, "leaves": {}}
                )
            else:
                # Update existing presence
                self.presences[topic][pid].metas.append(presence_meta)
                logger.debug("presence.updated", topic=topic, pid=pid, meta=meta)

    async def untrack(self, pid: str, topic: str) -> None:
        """
        Stop tracking a process's presence.

        Args:
            pid: Process/user identifier
            topic: The topic to stop tracking on
        """
        async with self.lock:
            if topic not in self.presences or pid not in self.presences[topic]:
                return

            presence_state = self.presences[topic][pid]
            del self.presences[topic][pid]

            # Clean up empty topics
            if not self.presences[topic]:
                del self.presences[topic]

            logger.info("presence.left", topic=topic, pid=pid)

            # Notify leave callbacks
            await self._notify_callbacks("leave", topic, pid, presence_state)

            # Publish presence_diff event
            await self._publish_presence_diff(topic, {"joins": {}, "leaves": {pid: presence_state}})

    async def list(self, topic: str) -> dict[str, PresenceState]:
        """
        List all presences for a topic.

        Args:
            topic: The topic to list presences for

        Returns:
            Dictionary mapping process IDs to their presence states
        """
        async with self.lock:
            return dict(self.presences.get(topic, {}))

    async def get_presence(self, pid: str, topic: str) -> PresenceState | None:
        """
        Get presence state for a specific process on a topic.

        Args:
            pid: Process/user identifier
            topic: The topic to check

        Returns:
            PresenceState if present, None otherwise
        """
        async with self.lock:
            return self.presences.get(topic, {}).get(pid)

    def on_join(self, callback: Callable) -> None:
        """
        Register callback for when a presence joins.

        Args:
            callback: Function called with (topic, pid, presence_state)
        """
        self.callbacks["join"].append(callback)
        logger.debug("presence.join_callback_registered")

    def on_leave(self, callback: Callable) -> None:
        """
        Register callback for when a presence leaves.

        Args:
            callback: Function called with (topic, pid, presence_state)
        """
        self.callbacks["leave"].append(callback)
        logger.debug("presence.leave_callback_registered")

    async def _notify_callbacks(
        self, event_type: str, topic: str, pid: str, presence_state: PresenceState
    ) -> None:
        """
        Notify registered callbacks about presence events.

        Args:
            event_type: "join" or "leave"
            topic: The topic where the event occurred
            pid: The process identifier
            presence_state: The presence state
        """
        for callback in self.callbacks[event_type]:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(topic, pid, presence_state)
                else:
                    callback(topic, pid, presence_state)
            except Exception as e:
                logger.error(
                    "presence.callback_error",
                    event_type=event_type,
                    topic=topic,
                    pid=pid,
                    error=str(e),
                )

    async def _publish_presence_diff(self, topic: str, diff: dict[str, Any]) -> None:
        """
        Publish presence diff to subscribers.

        Args:
            topic: The topic to publish to
            diff: The presence diff with "joins" and "leaves"
        """
        try:
            # Convert PresenceState objects to dictionaries for JSON serialization
            serializable_diff = {}
            for key in ["joins", "leaves"]:
                serializable_diff[key] = {}
                for pid, state in diff[key].items():
                    serializable_diff[key][pid] = {
                        "metas": [
                            {
                                "online_at": meta.online_at,
                                "user_id": meta.user_id,
                                "metadata": meta.metadata,
                            }
                            for meta in state.metas
                        ]
                    }

            await self.pubsub.publish(
                f"presence:{topic}", {"event": "presence_diff", "payload": serializable_diff}
            )
        except Exception as e:
            logger.error("presence.publish_error", topic=topic, error=str(e))

    async def sync_presence_state(self, topic: str) -> dict[str, Any]:
        """
        Get the current presence state for synchronization.

        This method returns the full presence state in a format suitable
        for sending to new joiners or for synchronization between nodes.

        Args:
            topic: The topic to get state for

        Returns:
            Serializable presence state
        """
        presences = await self.list(topic)

        state = {}
        for pid, presence_state in presences.items():
            state[pid] = {
                "metas": [
                    {
                        "online_at": meta.online_at,
                        "user_id": meta.user_id,
                        "metadata": meta.metadata,
                    }
                    for meta in presence_state.metas
                ]
            }

        return state

    async def topic_count(self) -> int:
        """
        Get the number of topics with active presences.

        Returns:
            Number of topics
        """
        async with self.lock:
            return len(self.presences)

    async def total_presence_count(self) -> int:
        """
        Get the total number of presences across all topics.

        Returns:
            Total presence count
        """
        async with self.lock:
            total = 0
            for topic_presences in self.presences.values():
                total += len(topic_presences)
            return total

    async def presence_count_for_topic(self, topic: str) -> int:
        """
        Get the number of presences for a specific topic.

        Args:
            topic: The topic to count presences for

        Returns:
            Number of presences on the topic
        """
        async with self.lock:
            return len(self.presences.get(topic, {}))

    async def cleanup_stale_presences(self, max_age_seconds: float = 3600) -> int:
        """
        Clean up stale presences that haven't been updated recently.

        Args:
            max_age_seconds: Maximum age in seconds before considering a presence stale

        Returns:
            Number of stale presences cleaned up
        """
        current_time = time.time()
        cutoff_time = current_time - max_age_seconds
        cleaned_count = 0

        async with self.lock:
            topics_to_clean = []

            for topic, topic_presences in self.presences.items():
                pids_to_remove = []

                for pid, presence_state in topic_presences.items():
                    # Check if all metas are stale
                    all_stale = all(meta.online_at < cutoff_time for meta in presence_state.metas)

                    if all_stale:
                        pids_to_remove.append(pid)

                # Remove stale presences
                for pid in pids_to_remove:
                    del topic_presences[pid]
                    cleaned_count += 1
                    logger.info("presence.cleaned_stale", topic=topic, pid=pid)

                # Mark empty topics for removal
                if not topic_presences:
                    topics_to_clean.append(topic)

            # Remove empty topics
            for topic in topics_to_clean:
                del self.presences[topic]

        if cleaned_count > 0:
            logger.info("presence.cleanup_complete", cleaned_count=cleaned_count)

        return cleaned_count


# Global Presence instance
_global_presence: Presence | None = None


def get_presence() -> Presence:
    """Get or create the global Presence instance."""
    global _global_presence
    if _global_presence is None:
        _global_presence = Presence()
    return _global_presence

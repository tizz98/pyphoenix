"""Main Phoenix application class."""

import asyncio

import structlog

from .channel import Channel
from .presence import get_presence
from .pubsub import get_pubsub
from .socket import WebSocketTransport
from .types import Message

logger = structlog.get_logger(__name__)


class Phoenix:
    """
    Main Phoenix application class.

    This is the central coordination point for the PyPhoenix application,
    managing transports, channels, and providing the main API.
    """

    def __init__(self):
        """Initialize the Phoenix application."""
        self.channel_handlers: dict[str, type[Channel]] = {}
        self.channel_instances: dict[str, Channel] = {}  # topic -> channel instance
        self.transport: WebSocketTransport | None = None
        self.pubsub = get_pubsub()
        self.presence = get_presence()

        logger.info("phoenix.initialized")

    def channel(self, topic_pattern: str):
        """
        Decorator to register a channel handler for a topic pattern.

        Args:
            topic_pattern: Topic pattern to handle (e.g., "room:*")

        Returns:
            Decorator function
        """

        def decorator(channel_class: type[Channel]) -> type[Channel]:
            self.channel_handlers[topic_pattern] = channel_class
            logger.info(
                "phoenix.channel_registered", pattern=topic_pattern, handler=channel_class.__name__
            )
            return channel_class

        return decorator

    async def start(self, host: str = "localhost", port: int = 4000) -> None:
        """
        Start the Phoenix application.

        Args:
            host: Host to bind to
            port: Port to bind to
        """
        # Initialize and start WebSocket transport
        self.transport = WebSocketTransport(host, port)
        self.transport.set_phoenix_app(self)  # Connect transport to this app
        await self.transport.start()

        logger.info("phoenix.started", host=host, port=port)

    async def stop(self) -> None:
        """Stop the Phoenix application."""
        if self.transport:
            await self.transport.stop()

        logger.info("phoenix.stopped")

    async def route_message(self, socket, message: Message) -> None:
        """
        Route incoming message to appropriate channel.

        Args:
            socket: The socket that received the message
            message: The parsed message
        """
        topic = message.topic
        event = message.event

        logger.debug("phoenix.routing_message", topic=topic, event_name=event, socket_id=socket.id)

        # Find or create channel instance
        channel = await self.get_or_create_channel(topic, socket)

        if channel:
            # Dispatch event to channel
            await channel.handle_event(event, message.payload, message.ref, socket)
        else:
            # No matching channel pattern
            await socket.push(
                Message(
                    topic=topic,
                    event="phx_reply",
                    payload={"status": "error", "response": {"reason": "no matching channel"}},
                    ref=message.ref,
                )
            )
            logger.warning("phoenix.no_matching_channel", topic=topic, event_name=event)

    async def get_or_create_channel(self, topic: str, socket) -> Channel | None:
        """
        Get existing channel or create new one from registered handlers.

        Args:
            topic: The channel topic
            socket: The socket requesting the channel

        Returns:
            Channel instance or None if no pattern matches
        """
        # Check if we already have a channel for this topic
        if topic in self.channel_instances:
            existing = self.channel_instances[topic]
            # Ensure this socket has access to this channel
            if not hasattr(existing, "_sockets"):
                existing._sockets = set()
            existing._sockets.add(socket)
            return existing

        # Find matching pattern
        for pattern, handler_class in self.channel_handlers.items():
            if self.match_topic_pattern(pattern, topic):
                logger.info(
                    "phoenix.creating_channel",
                    topic=topic,
                    pattern=pattern,
                    handler=handler_class.__name__,
                )

                # Create new channel instance
                channel = handler_class(topic=topic, params={}, socket=socket)
                channel.phoenix_app = self  # Give channel reference to Phoenix app
                channel._sockets = {socket}  # Track sockets for this channel

                self.channel_instances[topic] = channel
                return channel

        return None

    def match_topic_pattern(self, pattern: str, topic: str) -> bool:
        """
        Match topic against pattern (support wildcards).

        Args:
            pattern: Pattern like "room:*" or "user:*"
            topic: Actual topic like "room:lobby" or "user:123"

        Returns:
            True if topic matches pattern
        """
        if pattern == topic:
            return True
        if pattern.endswith("*"):
            prefix = pattern[:-1]  # Remove *
            return topic.startswith(prefix)
        return False

    def run(self, host: str = "localhost", port: int = 4000, **kwargs) -> None:
        """
        Run the Phoenix application (blocking).

        Args:
            host: Host to bind to
            port: Port to bind to
            **kwargs: Additional arguments (for future use)
        """

        async def run_app():
            await self.start(host, port)
            try:
                # Keep running until interrupted
                while True:
                    await asyncio.sleep(1)
            except KeyboardInterrupt:
                logger.info("phoenix.interrupted")
            finally:
                await self.stop()

        try:
            asyncio.run(run_app())
        except KeyboardInterrupt:
            logger.info("phoenix.shutdown")


# Convenience function for creating Phoenix apps
def create_app() -> Phoenix:
    """Create a new Phoenix application instance."""
    return Phoenix()

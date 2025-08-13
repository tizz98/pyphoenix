"""Main Phoenix application class."""

import asyncio

import structlog

from .channel import Channel
from .presence import get_presence
from .pubsub import get_pubsub
from .socket import WebSocketTransport

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
        await self.transport.start()

        logger.info("phoenix.started", host=host, port=port)

    async def stop(self) -> None:
        """Stop the Phoenix application."""
        if self.transport:
            await self.transport.stop()

        logger.info("phoenix.stopped")

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

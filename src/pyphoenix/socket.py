"""Socket and WebSocket transport implementation for PyPhoenix."""

import asyncio
import json
import uuid
from typing import Any

import structlog
import websockets
from websockets.server import WebSocketServerProtocol

from .channel import Channel
from .pubsub import get_pubsub
from .types import ChannelState, Message

logger = structlog.get_logger(__name__)


class Socket:
    """
    Represents a client connection to the Phoenix server.

    Handles WebSocket communication, channel management, and message routing.
    """

    def __init__(self, websocket: WebSocketServerProtocol | None = None):
        """
        Initialize a socket connection.

        Args:
            websocket: The WebSocket connection (None for testing)
        """
        self.id = uuid.uuid4().hex
        self.websocket = websocket
        self.channels: dict[str, Channel] = {}
        self.ref_counter = 0
        self.transport = "websocket" if websocket else "test"
        self.pubsub = get_pubsub()
        self.closed = False

        logger.info("socket.connected", socket_id=self.id, transport=self.transport)

    async def push(self, message: Message) -> None:
        """
        Send a message through the socket.

        Args:
            message: The message to send
        """
        if self.closed:
            raise RuntimeError("Socket is closed")

        message_data = message.to_list()

        if self.websocket:
            try:
                await self.websocket.send(json.dumps(message_data))
                logger.debug(
                    "socket.message_sent",
                    socket_id=self.id,
                    topic=message.topic,
                    event_name=message.event,
                )
            except Exception as e:
                logger.error("socket.send_error", socket_id=self.id, error=str(e))
                await self.close()
        else:
            # For testing without WebSocket - just trigger local handling
            await self._handle_message(message_data)

    async def channel(self, topic: str, params: dict[str, Any] | None = None) -> Channel:
        """
        Get or create a channel for the given topic.

        Args:
            topic: The channel topic
            params: Optional parameters for the channel

        Returns:
            Channel instance
        """
        if topic not in self.channels:
            channel = Channel(topic, params, self)
            self.channels[topic] = channel
            logger.debug("socket.channel_created", socket_id=self.id, topic=topic)

        return self.channels[topic]

    async def handle_websocket_message(self, raw_message: str) -> None:
        """
        Handle incoming WebSocket message.

        Args:
            raw_message: Raw JSON message from WebSocket
        """
        try:
            message_data = json.loads(raw_message)
            await self._handle_message(message_data)
        except json.JSONDecodeError as e:
            logger.error("socket.invalid_json", socket_id=self.id, error=str(e))
        except Exception as e:
            logger.error("socket.message_error", socket_id=self.id, error=str(e))

    async def _handle_message(self, message_data: list) -> None:
        """
        Handle parsed message data.

        Args:
            message_data: Parsed message in Phoenix format [join_ref, ref, topic, event, payload]
        """
        try:
            message = Message.from_list(message_data)
            logger.debug(
                "socket.message_received",
                socket_id=self.id,
                topic=message.topic,
                event_name=message.event,
            )

            # Get or create channel for this topic
            channel = await self.channel(message.topic)

            # Handle the message based on event type
            if message.event == "phx_join":
                await self._handle_join(channel, message)
            elif message.event == "phx_leave":
                await self._handle_leave(channel, message)
            else:
                # Regular channel event
                await channel.trigger(message.event, message.payload, message.ref)

        except Exception as e:
            logger.error("socket.handle_error", socket_id=self.id, error=str(e))

    async def _handle_join(self, channel: Channel, message: Message) -> None:
        """
        Handle channel join request.

        Args:
            channel: The channel being joined
            message: The join message
        """
        try:
            # Set channel join reference
            channel.join_ref = message.ref
            channel.state = ChannelState.JOINED

            # Subscribe to channel topic in PubSub
            await self.pubsub.subscribe(
                channel.topic,
                lambda topic, msg: asyncio.create_task(
                    self._forward_pubsub_message(channel, topic, msg)
                ),
            )

            # Send successful join reply
            reply = Message(
                topic=message.topic,
                event="phx_reply",
                payload={"status": "ok", "response": {}},
                ref=message.ref,
                join_ref=message.ref,
            )
            await self.push(reply)

            logger.info("socket.channel_joined", socket_id=self.id, topic=channel.topic)

        except Exception as e:
            # Send error reply
            reply = Message(
                topic=message.topic,
                event="phx_reply",
                payload={"status": "error", "response": {"reason": str(e)}},
                ref=message.ref,
                join_ref=message.ref,
            )
            await self.push(reply)

            logger.error("socket.join_error", socket_id=self.id, topic=channel.topic, error=str(e))

    async def _handle_leave(self, channel: Channel, message: Message) -> None:
        """
        Handle channel leave request.

        Args:
            channel: The channel being left
            message: The leave message
        """
        try:
            channel.state = ChannelState.CLOSED

            # Send leave reply
            reply = Message(
                topic=message.topic,
                event="phx_reply",
                payload={"status": "ok", "response": {}},
                ref=message.ref,
                join_ref=channel.join_ref,
            )
            await self.push(reply)

            # Remove channel
            if channel.topic in self.channels:
                del self.channels[channel.topic]

            logger.info("socket.channel_left", socket_id=self.id, topic=channel.topic)

        except Exception as e:
            logger.error("socket.leave_error", socket_id=self.id, topic=channel.topic, error=str(e))

    async def _forward_pubsub_message(self, channel: Channel, topic: str, message: Any) -> None:
        """
        Forward PubSub messages to the channel.

        Args:
            channel: The target channel
            topic: The message topic
            message: The message data
        """
        try:
            if isinstance(message, Message):
                await self.push(message)
            else:
                # Convert generic message to Phoenix message format
                phoenix_msg = Message(
                    topic=topic,
                    event="broadcast",
                    payload=message if isinstance(message, dict) else {"data": message},
                    join_ref=channel.join_ref,
                )
                await self.push(phoenix_msg)
        except Exception as e:
            logger.error("socket.forward_error", socket_id=self.id, topic=topic, error=str(e))

    async def close(self) -> None:
        """Close the socket connection."""
        if self.closed:
            return

        self.closed = True

        # Close all channels
        for channel in list(self.channels.values()):
            try:
                await channel.leave()
            except Exception as e:
                logger.error(
                    "socket.channel_close_error",
                    socket_id=self.id,
                    topic=channel.topic,
                    error=str(e),
                )

        self.channels.clear()

        # Close WebSocket if present
        if self.websocket and not self.websocket.closed:
            try:
                await self.websocket.close()
            except Exception as e:
                logger.error("socket.websocket_close_error", socket_id=self.id, error=str(e))

        logger.info("socket.closed", socket_id=self.id)

    def __str__(self) -> str:
        return f"Socket(id={self.id}, transport={self.transport})"

    def __repr__(self) -> str:
        return (
            f"Socket(id={self.id!r}, transport={self.transport!r}, channels={len(self.channels)})"
        )


class WebSocketTransport:
    """WebSocket transport for handling client connections."""

    def __init__(self, host: str = "localhost", port: int = 4000):
        """
        Initialize WebSocket transport.

        Args:
            host: Host to bind to
            port: Port to bind to
        """
        self.host = host
        self.port = port
        self.sockets: set[Socket] = set()
        self.server = None

        logger.info("websocket_transport.initialized", host=host, port=port)

    async def start(self) -> None:
        """Start the WebSocket server."""
        self.server = await websockets.serve(self.handle_connection, self.host, self.port)
        logger.info("websocket_transport.started", host=self.host, port=self.port)

    async def stop(self) -> None:
        """Stop the WebSocket server."""
        if self.server:
            self.server.close()
            await self.server.wait_closed()

        # Close all sockets
        for socket in list(self.sockets):
            await socket.close()

        logger.info("websocket_transport.stopped")

    async def handle_connection(self, websocket: WebSocketServerProtocol, path: str) -> None:
        """
        Handle new WebSocket connection.

        Args:
            websocket: The WebSocket connection
            path: The connection path
        """
        socket = Socket(websocket)
        self.sockets.add(socket)

        try:
            async for message in websocket:
                await socket.handle_websocket_message(message)
        except websockets.exceptions.ConnectionClosed:
            logger.debug("websocket_transport.connection_closed", socket_id=socket.id)
        except Exception as e:
            logger.error("websocket_transport.connection_error", socket_id=socket.id, error=str(e))
        finally:
            await socket.close()
            self.sockets.discard(socket)

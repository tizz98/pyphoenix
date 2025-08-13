"""Client-side Socket implementation for PyPhoenix."""

import asyncio
import json
import uuid
from collections.abc import Callable
from enum import Enum
from typing import Any

import structlog
from websockets.asyncio.client import ClientConnection, connect

from .exceptions import ConnectionError
from .exceptions import TimeoutError as PyPhoenixTimeoutError
from .types import ChannelState, Message

logger = structlog.get_logger(__name__)


class ConnectionState(Enum):
    """Client connection states."""

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    CLOSING = "closing"
    CLOSED = "closed"


class ClientChannel:
    """Client-side channel implementation."""

    def __init__(self, topic: str, socket: "ClientSocket", params: dict[str, Any] | None = None):
        """
        Initialize a client channel.

        Args:
            topic: The channel topic
            socket: The client socket
            params: Optional join parameters
        """
        self.topic = topic
        self.socket = socket
        self.params = params or {}
        self.state = ChannelState.CLOSED
        self.join_ref: str | None = None
        self.bindings: dict[str, list[Callable]] = {}
        self.join_future: asyncio.Future | None = None
        self.timeout = 10.0

        logger.debug("client_channel.created", topic=topic)

    async def join(self, timeout: float | None = None) -> dict[str, Any]:
        """
        Join the channel.

        Args:
            timeout: Optional join timeout

        Returns:
            Join response from server
        """
        if self.state == ChannelState.JOINED:
            return {"status": "already_joined"}

        if self.state == ChannelState.JOINING and self.join_future:
            return await self.join_future

        self.state = ChannelState.JOINING
        self.join_ref = str(uuid.uuid4())
        timeout = timeout or self.timeout

        # Create join future
        self.join_future = asyncio.Future()

        # Send join message
        message = Message(
            topic=self.topic,
            event="phx_join",
            payload=self.params,
            ref=self.join_ref,
            join_ref=self.join_ref,
        )

        try:
            await self.socket.push(message)

            # Wait for join response
            response = await asyncio.wait_for(self.join_future, timeout=timeout)
            self.state = ChannelState.JOINED

            logger.info("client_channel.joined", topic=self.topic)
            return response

        except TimeoutError as e:
            self.state = ChannelState.ERRORED
            logger.error("client_channel.join_timeout", topic=self.topic)
            raise PyPhoenixTimeoutError(f"Join timeout after {timeout}s") from e

        except Exception as e:
            self.state = ChannelState.ERRORED
            logger.error("client_channel.join_error", topic=self.topic, error=str(e))
            raise

    async def leave(self) -> None:
        """Leave the channel."""
        if self.state in [ChannelState.CLOSED, ChannelState.LEAVING]:
            return

        self.state = ChannelState.LEAVING

        message = Message(
            topic=self.topic,
            event="phx_leave",
            payload={},
            ref=str(uuid.uuid4()),
            join_ref=self.join_ref,
        )

        try:
            await self.socket.push(message)
            self.state = ChannelState.CLOSED
            logger.info("client_channel.left", topic=self.topic)
        except Exception as e:
            logger.error("client_channel.leave_error", topic=self.topic, error=str(e))
            self.state = ChannelState.CLOSED

    async def push(self, event: str, payload: dict[str, Any]) -> None:
        """
        Push a message to the channel.

        Args:
            event: The event name
            payload: The message payload
        """
        if self.state != ChannelState.JOINED:
            raise ConnectionError("Channel not joined")

        message = Message(
            topic=self.topic,
            event=event,
            payload=payload,
            ref=str(uuid.uuid4()),
            join_ref=self.join_ref,
        )

        await self.socket.push(message)
        logger.debug("client_channel.pushed", topic=self.topic, event_name=event)

    def on(self, event: str, callback: Callable | None = None):
        """
        Register an event handler.

        Can be used as a decorator:
            @channel.on("event_name")
            def handler(payload, ref):
                pass

        Or as a regular method:
            channel.on("event_name", handler)

        Args:
            event: The event name
            callback: The callback function (optional for decorator usage)
        """

        def decorator(func: Callable) -> Callable:
            if event not in self.bindings:
                self.bindings[event] = []
            self.bindings[event].append(func)
            return func

        if callback is None:
            # Used as decorator: @channel.on("event")
            return decorator
        else:
            # Used as method: channel.on("event", callback)
            decorator(callback)
            return callback

    def off(self, event: str, callback: Callable | None = None) -> None:
        """
        Remove event handler(s).

        Args:
            event: The event name
            callback: Specific callback to remove, or None to remove all
        """
        if event not in self.bindings:
            return

        if callback is None:
            self.bindings[event] = []
        else:
            self.bindings[event] = [cb for cb in self.bindings[event] if cb != callback]

    async def trigger(self, event: str, payload: dict[str, Any], ref: str | None = None) -> None:
        """
        Trigger event handlers.

        Args:
            event: The event name
            payload: The event payload
            ref: Optional message reference
        """
        if event not in self.bindings:
            return

        for callback in self.bindings[event]:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(payload, ref)
                else:
                    callback(payload, ref)
            except Exception as e:
                logger.error(
                    "client_channel.callback_error",
                    topic=self.topic,
                    event_name=event,
                    error=str(e),
                )

    def _handle_reply(self, payload: dict[str, Any], ref: str | None) -> None:
        """Handle reply messages."""
        if ref == self.join_ref and self.join_future and not self.join_future.done():
            if payload.get("status") == "ok":
                self.join_future.set_result(payload.get("response", {}))
            else:
                error = payload.get("response", {}).get("reason", "Unknown error")
                self.join_future.set_exception(Exception(f"Join failed: {error}"))


class ClientSocket:
    """Client-side Phoenix socket implementation."""

    def __init__(self, url: str, params: dict[str, Any] | None = None):
        """
        Initialize a client socket.

        Args:
            url: WebSocket URL to connect to
            params: Optional connection parameters
        """
        self.url = url
        self.params = params or {}
        self.state = ConnectionState.DISCONNECTED
        self.websocket: ClientConnection | None = None
        self.channels: dict[str, ClientChannel] = {}
        self.ref_counter = 0
        self.heartbeat_interval = 30.0
        self.reconnect_interval = 5.0
        self.max_reconnect_attempts = 10
        self.reconnect_attempts = 0

        # Connection management
        self.connect_future: asyncio.Future | None = None
        self.heartbeat_task: asyncio.Task | None = None
        self.receive_task: asyncio.Task | None = None
        self.reconnect_task: asyncio.Task | None = None

        # Event handlers
        self.connect_handlers: list[Callable] = []
        self.disconnect_handlers: list[Callable] = []
        self.error_handlers: list[Callable] = []

        logger.info("client_socket.created", url=url)

    async def connect(self, timeout: float = 10.0) -> None:
        """
        Connect to the Phoenix server.

        Args:
            timeout: Connection timeout in seconds
        """
        if self.state == ConnectionState.CONNECTED:
            return

        if self.state == ConnectionState.CONNECTING and self.connect_future:
            await self.connect_future
            return

        self.state = ConnectionState.CONNECTING
        self.connect_future = asyncio.Future()

        try:
            # Connect WebSocket
            self.websocket = await asyncio.wait_for(
                connect(self.url, additional_headers=self._build_headers()),
                timeout=timeout,
            )

            self.state = ConnectionState.CONNECTED
            self.reconnect_attempts = 0

            # Start background tasks
            self.receive_task = asyncio.create_task(self._receive_loop())
            self.heartbeat_task = asyncio.create_task(self._heartbeat_loop())

            self.connect_future.set_result(None)

            # Notify connect handlers
            for handler in self.connect_handlers:
                try:
                    if asyncio.iscoroutinefunction(handler):
                        await handler()
                    else:
                        handler()
                except Exception as e:
                    logger.error("client_socket.connect_handler_error", error=str(e))

            logger.info("client_socket.connected", url=self.url)

        except Exception as e:
            self.state = ConnectionState.DISCONNECTED
            self.connect_future.set_exception(e)
            logger.error("client_socket.connect_error", url=self.url, error=str(e))
            raise

    async def disconnect(self) -> None:
        """Disconnect from the Phoenix server."""
        if self.state in [ConnectionState.DISCONNECTED, ConnectionState.CLOSING]:
            return

        self.state = ConnectionState.CLOSING

        # Cancel background tasks
        if self.heartbeat_task:
            self.heartbeat_task.cancel()
        if self.receive_task:
            self.receive_task.cancel()
        if self.reconnect_task:
            self.reconnect_task.cancel()

        # Leave all channels
        for channel in list(self.channels.values()):
            try:
                await channel.leave()
            except Exception as e:
                logger.error("client_socket.channel_leave_error", topic=channel.topic, error=str(e))

        # Close WebSocket
        if self.websocket:
            try:
                await self.websocket.close()
            except Exception as e:
                logger.error("client_socket.websocket_close_error", error=str(e))

        self.state = ConnectionState.DISCONNECTED

        # Notify disconnect handlers
        for handler in self.disconnect_handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler()
                else:
                    handler()
            except Exception as e:
                logger.error("client_socket.disconnect_handler_error", error=str(e))

        logger.info("client_socket.disconnected")

    def channel(self, topic: str, params: dict[str, Any] | None = None) -> ClientChannel:
        """
        Get or create a channel.

        Args:
            topic: The channel topic
            params: Optional join parameters

        Returns:
            ClientChannel instance
        """
        if topic not in self.channels:
            self.channels[topic] = ClientChannel(topic, self, params)

        return self.channels[topic]

    async def push(self, message: Message) -> None:
        """
        Push a message to the server.

        Args:
            message: The message to send
        """
        if self.state != ConnectionState.CONNECTED or not self.websocket:
            raise ConnectionError("Socket not connected")

        message_data = json.dumps(message.to_list())
        await self.websocket.send(message_data)
        logger.debug("client_socket.message_sent", topic=message.topic, event_name=message.event)

    def on_connect(self, handler: Callable) -> None:
        """Register a connect event handler."""
        self.connect_handlers.append(handler)

    def on_disconnect(self, handler: Callable) -> None:
        """Register a disconnect event handler."""
        self.disconnect_handlers.append(handler)

    def on_error(self, handler: Callable) -> None:
        """Register an error event handler."""
        self.error_handlers.append(handler)

    async def _receive_loop(self) -> None:
        """Main message receiving loop."""
        logger.info("client_socket.receive_loop_started")

        try:
            if not self.websocket:
                return

            async for raw_message in self.websocket:
                try:
                    message_data = json.loads(raw_message)
                    message = Message.from_list(message_data)

                    logger.debug(
                        "client_socket.message_received",
                        topic=message.topic,
                        event_name=message.event,
                    )

                    # Route message to appropriate channel
                    if message.topic in self.channels:
                        channel = self.channels[message.topic]

                        if message.event == "phx_reply":
                            channel._handle_reply(message.payload, message.ref)
                        else:
                            await channel.trigger(message.event, message.payload, message.ref)

                except json.JSONDecodeError as e:
                    logger.error("client_socket.invalid_json", error=str(e))
                except Exception as e:
                    logger.error("client_socket.message_processing_error", error=str(e))

        except Exception as e:
            if "Connection closed" in str(e) or "ConnectionClosed" in str(type(e).__name__):
                logger.info("client_socket.connection_closed")
                await self._handle_disconnect()
            else:
                logger.error("client_socket.receive_loop_error", error=str(e))
                await self._handle_error(e)

    async def _heartbeat_loop(self) -> None:
        """Send periodic heartbeat messages."""
        logger.info("client_socket.heartbeat_loop_started")

        while self.state == ConnectionState.CONNECTED:
            try:
                await asyncio.sleep(self.heartbeat_interval)

                if self.state == ConnectionState.CONNECTED:
                    heartbeat = Message(
                        topic="phoenix",
                        event="heartbeat",
                        payload={},
                        ref=str(self.ref_counter),
                    )
                    self.ref_counter += 1

                    await self.push(heartbeat)
                    logger.debug("client_socket.heartbeat_sent")

            except Exception as e:
                logger.error("client_socket.heartbeat_error", error=str(e))
                await self._handle_error(e)
                break

    async def _handle_disconnect(self) -> None:
        """Handle unexpected disconnection."""
        if self.state == ConnectionState.CLOSING:
            return

        self.state = ConnectionState.DISCONNECTED
        logger.warning("client_socket.disconnected_unexpectedly")

        # Schedule reconnection
        if self.reconnect_attempts < self.max_reconnect_attempts:
            self.reconnect_task = asyncio.create_task(self._reconnect())

    async def _handle_error(self, error: Exception) -> None:
        """Handle connection errors."""
        logger.error("client_socket.error", error=str(error))

        # Notify error handlers
        for handler in self.error_handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(error)
                else:
                    handler(error)
            except Exception as e:
                logger.error("client_socket.error_handler_error", error=str(e))

    async def _reconnect(self) -> None:
        """Attempt to reconnect to the server."""
        self.state = ConnectionState.RECONNECTING
        self.reconnect_attempts += 1

        logger.info(
            "client_socket.reconnecting",
            attempt=self.reconnect_attempts,
            max_attempts=self.max_reconnect_attempts,
        )

        await asyncio.sleep(self.reconnect_interval)

        try:
            await self.connect()

            # Rejoin all channels
            for channel in self.channels.values():
                if channel.state == ChannelState.JOINED:
                    try:
                        await channel.join()
                    except Exception as e:
                        logger.error(
                            "client_socket.rejoin_error",
                            topic=channel.topic,
                            error=str(e),
                        )

        except Exception as e:
            logger.error("client_socket.reconnect_error", error=str(e))
            if self.reconnect_attempts < self.max_reconnect_attempts:
                self.reconnect_task = asyncio.create_task(self._reconnect())
            else:
                logger.error("client_socket.max_reconnect_attempts_reached")

    def _build_headers(self) -> dict[str, str]:
        """Build HTTP headers for WebSocket connection."""
        headers = {"User-Agent": "PyPhoenix-Client/0.1.0"}

        # Add authentication headers if provided
        if "token" in self.params:
            headers["Authorization"] = f"Bearer {self.params['token']}"

        return headers

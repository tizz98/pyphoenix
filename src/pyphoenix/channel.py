"""
Channel implementation for PyPhoenix.

This module provides the core Channel class which implements Phoenix-style
real-time communication channels. Channels support joining, leaving, pushing
messages, broadcasting to all participants, and middleware processing.

Key features:
    - Phoenix wire format compatibility
    - Middleware support for cross-cutting concerns
    - Automatic rejoining and error handling
    - Event-based message routing
    - State management with proper lifecycle hooks

Example:
    Basic channel usage::

        from pyphoenix import Channel

        class RoomChannel(Channel):
            async def on_join(self, payload, socket):
                return {"status": "ok", "response": {"message": "Welcome!"}}

            async def on_message(self, payload, socket):
                await self.broadcast("new_message", payload)

    With middleware::

        class AuthenticatedRoomChannel(Channel):
            def __init__(self, topic, params=None, socket=None):
                super().__init__(topic, params, socket)
                self.use_middleware(LoggingMiddleware())
                self.use_middleware(AuthMiddleware(authenticate_user))
"""

import asyncio
import uuid
from collections.abc import Callable
from typing import Any

import structlog

from .exceptions import ChannelError, JoinError
from .exceptions import TimeoutError as PyPhoenixTimeoutError
from .middleware import MiddlewareStack
from .types import ChannelState, JoinResponse, Message, PushResponse

logger = structlog.get_logger(__name__)


class Channel:
    """
    A Channel represents a conversation on a specific topic between multiple participants.

    Channels maintain their own state and handle joining, leaving, pushing messages,
    and broadcasting to all participants. They support middleware for cross-cutting
    concerns like authentication, logging, and rate limiting.

    The channel lifecycle follows Phoenix conventions:
        1. CLOSED -> JOINING (when join() is called)
        2. JOINING -> JOINED (when join succeeds)
        3. JOINED -> LEAVING (when leave() is called)
        4. LEAVING -> CLOSED (when leave completes)
        5. Any state -> ERRORED (when errors occur)

    Attributes:
        topic (str): The channel topic (e.g., "room:lobby", "user:123")
        params (dict): Parameters passed during channel creation
        socket: Associated socket connection
        state (ChannelState): Current channel state
        join_ref (str, optional): Reference ID for the join operation
        timeout (float): Timeout for operations in seconds (default: 10.0)
        middleware (MiddlewareStack): Stack of middleware functions

    Example:
        Create a basic room channel::

            class RoomChannel(Channel):
                async def on_join(self, payload, socket):
                    user_id = payload.get("user_id")
                    logger.info(f"User {user_id} joined {self.topic}")
                    return {"status": "ok"}

                async def on_message(self, payload, socket):
                    message = payload.get("text", "")
                    await self.broadcast("new_message", {
                        "text": message,
                        "timestamp": time.time()
                    })
    """

    def __init__(self, topic: str, params: dict[str, Any] | None = None, socket=None):
        """
        Initialize a channel.

        Args:
            topic: The channel topic (e.g., "room:lobby")
            params: Optional parameters for joining
            socket: Associated socket connection
        """
        self.topic = topic
        self.params = params or {}
        self.socket = socket
        self.state = ChannelState.CLOSED
        self.join_ref: str | None = None
        self.ref_counter = 0
        self.bindings: dict[str, list[Callable]] = {}
        self.join_push: asyncio.Future | None = None
        self.push_buffer: list[tuple[str, dict[str, Any]]] = []
        self.rejoin_timer: asyncio.Task | None = None
        self.timeout = 10.0  # Default timeout in seconds
        self.middleware = MiddlewareStack()

        # Internal event handlers
        self.on("phx_reply", self._handle_reply)
        self.on("phx_error", self._handle_error)
        self.on("phx_close", self._handle_close)

        logger.info("channel.created", topic=topic, params=params)

    def use_middleware(self, middleware) -> None:
        """
        Add middleware to the channel's middleware stack.

        Middleware is executed in the order it's added, with each middleware
        having the opportunity to process or modify requests before they reach
        the final handler.

        Args:
            middleware: A middleware instance that implements the required interface
                       (e.g., LoggingMiddleware, AuthMiddleware, RateLimitMiddleware)

        Example:
            Add authentication and logging middleware::

                channel.use_middleware(LoggingMiddleware())
                channel.use_middleware(AuthMiddleware(authenticate_user))
                channel.use_middleware(RateLimitMiddleware(max_messages=10))
        """
        self.middleware.add(middleware)

    def remove_middleware(self, middleware) -> None:
        """Remove middleware from the channel's middleware stack."""
        self.middleware.remove(middleware)

    async def join(self, params: dict[str, Any] | None = None) -> JoinResponse:
        """
        Join the channel and start receiving messages.

        This method initiates the channel join process. If middleware is configured,
        it will be executed before the final join handler. The method handles
        authentication, validation, and any other middleware processing.

        Args:
            params: Optional parameters to send with join request.
                   These are merged with the channel's initial params.

        Returns:
            JoinResponse: An object containing the join status and response data.
            - status: "ok" if join succeeded, "error" if it failed
            - response: Dict with additional data (success response or error details)

        Raises:
            JoinError: If the join operation fails
            PyPhoenixTimeoutError: If the join times out

        Example:
            Basic join::

                response = await channel.join({"user_id": "123"})
                if response.status == "ok":
                    print("Successfully joined channel!")

            Join with authentication::

                response = await channel.join({
                    "token": "auth_token",
                    "user_id": "123"
                })
        """
        if self.state == ChannelState.JOINED:
            return JoinResponse("ok", {"status": "already_joined"})

        if self.state == ChannelState.JOINING:
            # Wait for existing join to complete
            if self.join_push:
                try:
                    await self.join_push
                    return JoinResponse("ok", {"status": "joined"})
                except Exception as e:
                    return JoinResponse("error", {"reason": str(e)})

        self.state = ChannelState.JOINING
        self.join_ref = self._make_ref()

        join_params = {**self.params}
        if params:
            join_params.update(params)

        logger.info("channel.joining", topic=self.topic, join_ref=self.join_ref)

        try:
            # Process join through middleware
            if hasattr(self, "on_join"):
                final_handler = self.on_join
            else:
                final_handler = self._default_join_handler

            result = await self.middleware.process_join(join_params, self.socket, final_handler)

            if self.socket is None:
                # No socket - join immediately for local testing
                self.state = ChannelState.JOINED

                # Send any buffered messages
                await self._flush_push_buffer()

                logger.info("channel.joined_local", topic=self.topic, join_ref=self.join_ref)
                return JoinResponse("ok", result or {"status": "joined_local"})
            else:
                # Create join push future
                self.join_push = asyncio.Future()

                # Send join message
                await self._push("phx_join", join_params, self.join_ref)

                # Wait for reply or timeout
                try:
                    response = await asyncio.wait_for(self.join_push, timeout=self.timeout)
                    self.state = ChannelState.JOINED

                    # Send any buffered messages
                    await self._flush_push_buffer()

                    logger.info("channel.joined", topic=self.topic, join_ref=self.join_ref)
                    return JoinResponse("ok", response)

                except TimeoutError as e:
                    self.state = ChannelState.ERRORED
                    error_msg = f"Join timeout after {self.timeout}s"
                    logger.error("channel.join_timeout", topic=self.topic, join_ref=self.join_ref)
                    raise PyPhoenixTimeoutError(error_msg) from e

        except PyPhoenixTimeoutError:
            raise
        except Exception as e:
            self.state = ChannelState.ERRORED
            logger.error("channel.join_error", topic=self.topic, error=str(e))
            raise JoinError(f"Failed to join channel: {e}", self.topic) from e

    async def _default_join_handler(self, payload: dict[str, Any], socket: Any) -> dict[str, Any]:
        """Default join handler when no custom handler is provided."""
        return {"status": "ok", "response": {"joined": self.topic}}

    async def leave(self) -> None:
        """Leave the channel gracefully."""
        if self.state in [ChannelState.CLOSED, ChannelState.LEAVING]:
            return

        logger.info("channel.leaving", topic=self.topic)
        self.state = ChannelState.LEAVING

        # Cancel rejoin timer if active
        if self.rejoin_timer:
            self.rejoin_timer.cancel()
            self.rejoin_timer = None

        try:
            # Process leave through middleware
            if hasattr(self, "on_leave"):
                final_handler = self.on_leave
            else:
                final_handler = self._default_leave_handler

            await self.middleware.process_leave("manual", self.socket, final_handler)

            await self._push("phx_leave", {})
        except Exception as e:
            logger.error("channel.leave_error", topic=self.topic, error=str(e))
            raise ChannelError(f"Failed to leave channel: {e}", self.topic) from e
        finally:
            self.state = ChannelState.CLOSED
            logger.info("channel.left", topic=self.topic)

    async def _default_leave_handler(self, reason: str, socket: Any) -> None:
        """Default leave handler when no custom handler is provided."""
        logger.info("channel.default_leave", topic=self.topic, reason=reason)

    async def push(self, event: str, payload: dict[str, Any]) -> PushResponse:
        """
        Push a message to the channel.

        Args:
            event: The event name
            payload: The message payload

        Returns:
            PushResponse with status and response data
        """
        if self.state != ChannelState.JOINED:
            # Buffer the message if not joined yet
            if self.state == ChannelState.JOINING:
                self.push_buffer.append((event, payload))
                return PushResponse("ok", {"status": "buffered"})
            else:
                return PushResponse("error", {"reason": "not_joined"})

        return await self._push(event, payload)

    async def broadcast(self, event: str, payload: dict[str, Any]) -> None:
        """
        Broadcast a message to all channel participants.

        Args:
            event: The event name
            payload: The message payload
        """
        # For now, this is the same as push since we don't have
        # multiple participants yet
        await self.push(event, payload)

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
            event: The event name to listen for
            callback: The callback function to invoke (optional for decorator usage)
        """

        def decorator(func: Callable) -> Callable:
            if event not in self.bindings:
                self.bindings[event] = []
            self.bindings[event].append(func)
            logger.debug("channel.event_bound", topic=self.topic, event_name=event)
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
            # Remove all callbacks for this event
            self.bindings[event] = []
        else:
            # Remove specific callback
            self.bindings[event] = [cb for cb in self.bindings[event] if cb != callback]

        logger.debug("channel.event_unbound", topic=self.topic, event_name=event)

    async def trigger(self, event: str, payload: dict[str, Any], ref: str | None = None) -> None:
        """
        Trigger event handlers for an event.

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
                    "channel.callback_error", topic=self.topic, event_name=event, error=str(e)
                )

    def _make_ref(self) -> str:
        """Generate a unique reference string."""
        self.ref_counter += 1
        return f"{self.ref_counter}_{uuid.uuid4().hex[:8]}"

    async def _push(
        self, event: str, payload: dict[str, Any], ref: str | None = None
    ) -> PushResponse:
        """
        Internal push method.

        Args:
            event: The event name
            payload: The message payload
            ref: Optional message reference

        Returns:
            PushResponse with status and response data
        """
        if not ref:
            ref = self._make_ref()

        message = Message(
            topic=self.topic, event=event, payload=payload, ref=ref, join_ref=self.join_ref
        )

        logger.debug("channel.push", topic=self.topic, event_name=event, ref=ref)

        if self.socket:
            try:
                await self.socket.push(message)
                return PushResponse("ok", {"status": "sent"}, ref)
            except Exception as e:
                logger.error("channel.push_error", topic=self.topic, event_name=event, error=str(e))
                return PushResponse("error", {"reason": str(e)}, ref)
        else:
            # No socket connection - simulate local handling
            await self.trigger(event, payload, ref)
            return PushResponse("ok", {"status": "local"}, ref)

    async def _flush_push_buffer(self) -> None:
        """Send any buffered messages."""
        if not self.push_buffer:
            return

        buffer = self.push_buffer[:]
        self.push_buffer.clear()

        for event, payload in buffer:
            try:
                await self._push(event, payload)
            except Exception as e:
                logger.error(
                    "channel.buffer_flush_error", topic=self.topic, event_name=event, error=str(e)
                )

    async def _handle_reply(self, payload: dict[str, Any], ref: str | None) -> None:
        """Handle phx_reply messages."""
        if ref == self.join_ref and self.join_push and not self.join_push.done():
            status = payload.get("status")
            response = payload.get("response", {})

            if status == "ok":
                self.join_push.set_result(response)
            else:
                self.join_push.set_exception(Exception(f"Join failed: {response}"))

    async def _handle_error(self, payload: dict[str, Any], ref: str | None) -> None:
        """Handle phx_error messages."""
        logger.error("channel.error", topic=self.topic, payload=payload)

        if self.state == ChannelState.JOINED:
            # Attempt rejoin after error
            await self._schedule_rejoin()

    async def _handle_close(self, payload: dict[str, Any], ref: str | None) -> None:
        """Handle phx_close messages."""
        logger.info("channel.closed", topic=self.topic, payload=payload)
        self.state = ChannelState.CLOSED

    async def _schedule_rejoin(self) -> None:
        """Schedule a rejoin attempt."""
        if self.rejoin_timer:
            self.rejoin_timer.cancel()

        async def rejoin_task():
            await asyncio.sleep(5.0)  # Wait 5 seconds before rejoining
            if self.state == ChannelState.CLOSED:
                logger.info("channel.rejoining", topic=self.topic)
                await self.join()

        self.rejoin_timer = asyncio.create_task(rejoin_task())

    def __str__(self) -> str:
        return f"Channel(topic={self.topic}, state={self.state.value})"

    def __repr__(self) -> str:
        return (
            f"Channel(topic={self.topic!r}, state={self.state.value!r}, join_ref={self.join_ref!r})"
        )

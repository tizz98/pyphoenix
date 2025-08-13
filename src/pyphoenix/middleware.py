"""Middleware system for PyPhoenix channels and messages."""

import asyncio
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class Middleware(ABC):
    """Base class for middleware components."""

    @abstractmethod
    async def process_join(
        self,
        payload: dict[str, Any],
        socket: Any,
        next_handler: Callable[..., Any],
    ) -> dict[str, Any]:
        """Process channel join requests."""
        pass

    @abstractmethod
    async def process_message(
        self,
        event: str,
        payload: dict[str, Any],
        socket: Any,
        next_handler: Callable[..., Any],
    ) -> Any:
        """Process incoming messages."""
        pass

    @abstractmethod
    async def process_leave(
        self,
        reason: str,
        socket: Any,
        next_handler: Callable[..., Any],
    ) -> None:
        """Process channel leave events."""
        pass


class LoggingMiddleware(Middleware):
    """Middleware that logs all channel activities."""

    def __init__(self, log_level: str = "info"):
        self.log_level = log_level

    async def process_join(
        self,
        payload: dict[str, Any],
        socket: Any,
        next_handler: Callable[..., Any],
    ) -> dict[str, Any]:
        """Log join attempts and results."""
        logger.info(
            "middleware.join_start",
            socket_id=socket.id if socket else "test",
            payload=payload,
        )

        try:
            result = await next_handler(payload, socket)
            logger.info(
                "middleware.join_success",
                socket_id=socket.id if socket else "test",
                result=result,
            )
            return result
        except Exception as e:
            logger.error(
                "middleware.join_error",
                socket_id=socket.id if socket else "test",
                error=str(e),
            )
            raise

    async def process_message(
        self,
        event: str,
        payload: dict[str, Any],
        socket: Any,
        next_handler: Callable[..., Any],
    ) -> Any:
        """Log message processing."""
        logger.debug(
            "middleware.message_start",
            event_name=event,
            socket_id=socket.id if socket else "test",
            payload=payload,
        )

        try:
            result = await next_handler(event, payload, socket)
            logger.debug(
                "middleware.message_success",
                event_name=event,
                socket_id=socket.id if socket else "test",
            )
            return result
        except Exception as e:
            logger.error(
                "middleware.message_error",
                event_name=event,
                socket_id=socket.id if socket else "test",
                error=str(e),
            )
            raise

    async def process_leave(
        self,
        reason: str,
        socket: Any,
        next_handler: Callable[..., Any],
    ) -> None:
        """Log leave events."""
        logger.info(
            "middleware.leave_start",
            reason=reason,
            socket_id=socket.id if socket else "test",
        )

        try:
            await next_handler(reason, socket)
            logger.info(
                "middleware.leave_success",
                reason=reason,
                socket_id=socket.id if socket else "test",
            )
        except Exception as e:
            logger.error(
                "middleware.leave_error",
                reason=reason,
                socket_id=socket.id if socket else "test",
                error=str(e),
            )
            raise


class AuthMiddleware(Middleware):
    """Middleware that handles authentication and authorization."""

    def __init__(self, auth_handler: Callable[[dict[str, Any]], Any] | None = None):
        self.auth_handler = auth_handler

    async def process_join(
        self,
        payload: dict[str, Any],
        socket: Any,
        next_handler: Callable[..., Any],
    ) -> dict[str, Any]:
        """Authenticate join requests."""
        if self.auth_handler:
            user = await self._authenticate(payload)
            if socket:
                socket.user = user
            payload["authenticated_user"] = user

        return await next_handler(payload, socket)

    async def process_message(
        self,
        event: str,
        payload: dict[str, Any],
        socket: Any,
        next_handler: Callable[..., Any],
    ) -> Any:
        """Check authorization for message events."""
        # For now, just pass through
        # Future: implement fine-grained permissions
        return await next_handler(event, payload, socket)

    async def process_leave(
        self,
        reason: str,
        socket: Any,
        next_handler: Callable[..., Any],
    ) -> None:
        """Handle leave cleanup."""
        return await next_handler(reason, socket)

    async def _authenticate(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        """Authenticate user from payload."""
        if not self.auth_handler:
            return None

        if asyncio.iscoroutinefunction(self.auth_handler):
            return await self.auth_handler(payload)
        else:
            return self.auth_handler(payload)


class RateLimitMiddleware(Middleware):
    """Middleware that implements rate limiting."""

    def __init__(self, max_messages_per_second: int = 10):
        self.max_messages_per_second = max_messages_per_second
        self.message_counts: dict[str, list[float]] = {}

    async def process_join(
        self,
        payload: dict[str, Any],
        socket: Any,
        next_handler: Callable[..., Any],
    ) -> dict[str, Any]:
        """No rate limiting on joins."""
        return await next_handler(payload, socket)

    async def process_message(
        self,
        event: str,
        payload: dict[str, Any],
        socket: Any,
        next_handler: Callable[..., Any],
    ) -> Any:
        """Apply rate limiting to messages."""
        socket_id = socket.id if socket else "test"
        current_time = asyncio.get_event_loop().time()

        # Initialize or clean up old timestamps
        if socket_id not in self.message_counts:
            self.message_counts[socket_id] = []

        # Remove timestamps older than 1 second
        self.message_counts[socket_id] = [
            ts for ts in self.message_counts[socket_id] if current_time - ts < 1.0
        ]

        # Check rate limit
        if len(self.message_counts[socket_id]) >= self.max_messages_per_second:
            logger.warning(
                "middleware.rate_limit_exceeded",
                socket_id=socket_id,
                event_name=event,
                limit=self.max_messages_per_second,
            )
            raise Exception(f"Rate limit exceeded: {self.max_messages_per_second} messages/second")

        # Record this message
        self.message_counts[socket_id].append(current_time)

        return await next_handler(event, payload, socket)

    async def process_leave(
        self,
        reason: str,
        socket: Any,
        next_handler: Callable[..., Any],
    ) -> None:
        """Clean up rate limiting data on leave."""
        socket_id = socket.id if socket else "test"
        if socket_id in self.message_counts:
            del self.message_counts[socket_id]

        return await next_handler(reason, socket)


class MiddlewareStack:
    """Manages and executes middleware in order."""

    def __init__(self, middleware: list[Middleware] | None = None):
        self.middleware = middleware or []

    def add(self, middleware: Middleware) -> None:
        """Add middleware to the stack."""
        self.middleware.append(middleware)

    def remove(self, middleware: Middleware) -> None:
        """Remove middleware from the stack."""
        if middleware in self.middleware:
            self.middleware.remove(middleware)

    async def process_join(
        self,
        payload: dict[str, Any],
        socket: Any,
        final_handler: Callable[..., Any],
    ) -> dict[str, Any]:
        """Process join through all middleware."""
        if not self.middleware:
            return await final_handler(payload, socket)

        async def create_handler(index: int):
            if index >= len(self.middleware):
                return final_handler

            middleware = self.middleware[index]

            async def handler(p: dict[str, Any], s: Any) -> dict[str, Any]:
                next_handler = await create_handler(index + 1)
                return await middleware.process_join(p, s, next_handler)

            return handler

        handler = await create_handler(0)
        return await handler(payload, socket)

    async def process_message(
        self,
        event: str,
        payload: dict[str, Any],
        socket: Any,
        final_handler: Callable[..., Any],
    ) -> Any:
        """Process message through all middleware."""
        if not self.middleware:
            return await final_handler(event, payload, socket)

        async def create_handler(index: int):
            if index >= len(self.middleware):
                return final_handler

            middleware = self.middleware[index]

            async def handler(e: str, p: dict[str, Any], s: Any) -> Any:
                next_handler = await create_handler(index + 1)
                return await middleware.process_message(e, p, s, next_handler)

            return handler

        handler = await create_handler(0)
        return await handler(event, payload, socket)

    async def process_leave(
        self,
        reason: str,
        socket: Any,
        final_handler: Callable[..., Any],
    ) -> None:
        """Process leave through all middleware."""
        if not self.middleware:
            return await final_handler(reason, socket)

        async def create_handler(index: int):
            if index >= len(self.middleware):
                return final_handler

            middleware = self.middleware[index]

            async def handler(r: str, s: Any) -> None:
                next_handler = await create_handler(index + 1)
                return await middleware.process_leave(r, s, next_handler)

            return handler

        handler = await create_handler(0)
        return await handler(reason, socket)

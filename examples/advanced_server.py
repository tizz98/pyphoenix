#!/usr/bin/env python3
"""
Advanced PyPhoenix server example demonstrating Phase 1+ features.

This example showcases:
- Configuration system
- Middleware stack
- Metrics collection
- Enhanced error handling
- Client-server interaction
- Presence tracking with cleanup
"""

import asyncio
import logging

import structlog

from pyphoenix import (
    AuthMiddleware,
    Channel,
    ClientSocket,
    LoggingMiddleware,
    Phoenix,
    PhoenixConfig,
    RateLimitMiddleware,
    get_phoenix_metrics,
    get_presence,
    set_config,
)

# Configure structured logging
structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.dev.set_exc_info,
        structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S", utc=False),
        structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=False,
)

logger = structlog.get_logger(__name__)

# Create enhanced configuration
config = PhoenixConfig(
    host="localhost",
    port=4001,
    debug=True,
)

# Customize component configurations
config.channel.default_timeout = 15.0
config.security.rate_limit_enabled = True
config.security.max_messages_per_second = 5
config.logging.log_channel_events = True

# Set global configuration
set_config(config)

# Create the Phoenix application
app = Phoenix()


# Custom authentication handler
async def authenticate_user(payload: dict) -> dict | None:
    """Simple authentication based on token."""
    token = payload.get("token")
    if token == "valid_token":
        return {"user_id": "authenticated_user", "username": "Test User"}
    elif token == "admin_token":
        return {"user_id": "admin", "username": "Admin User", "role": "admin"}
    return None


@app.channel("room:*")
class AdvancedRoomChannel(Channel):
    """
    Advanced room channel with middleware, metrics, and enhanced features.
    """

    def __init__(self, topic: str, params: dict | None = None, socket=None):
        super().__init__(topic, params, socket)

        # Add middleware
        self.use_middleware(LoggingMiddleware())
        self.use_middleware(AuthMiddleware(authenticate_user))
        self.use_middleware(RateLimitMiddleware(max_messages_per_second=3))

    async def on_join(self, payload: dict, socket) -> dict:
        """Handle channel joins with authentication and presence."""
        # Get metrics instance
        metrics = await get_phoenix_metrics()
        await metrics.record_channel_join(self.topic, success=True)

        user = payload.get("authenticated_user")
        if not user:
            logger.error("room.join_no_auth", topic=self.topic)
            await metrics.record_channel_join(self.topic, success=False)
            raise Exception("Authentication required")

        user_id = user["user_id"]
        username = user["username"]

        logger.info(
            "room.authenticated_join",
            topic=self.topic,
            user_id=user_id,
            username=username,
        )

        # Track presence with enhanced metadata
        presence = get_presence()
        await presence.track(
            pid=user_id,
            topic=self.topic,
            meta={
                "user_id": user_id,
                "username": username,
                "joined_at": asyncio.get_event_loop().time(),
                "socket_id": socket.id if socket else "test",
                "role": user.get("role", "user"),
                "metadata": {"last_seen": asyncio.get_event_loop().time()},
            },
        )

        # Send enhanced presence state to the new joiner
        presence_state = await presence.sync_presence_state(self.topic)
        await self.push("presence_state", {"presences": presence_state})

        # Send welcome message with room info
        room_info = await self._get_room_info()
        await self.push("room_info", room_info)

        # Record successful join
        await metrics.record_presence_track(self.topic)

        return {
            "status": "ok",
            "response": {
                "joined": self.topic,
                "user": {"id": user_id, "username": username},
                "room_info": room_info,
            },
        }

    async def on_message(self, payload: dict, socket) -> None:
        """Handle messages with rate limiting and metrics."""
        start_time = asyncio.get_event_loop().time()

        try:
            # Get authenticated user from middleware
            user = payload.get("authenticated_user")
            if not user:
                logger.warning("room.message_no_auth", topic=self.topic)
                return

            user_id = user["user_id"]
            username = user["username"]
            message_text = payload.get("text", "")

            logger.info(
                "room.message_received",
                topic=self.topic,
                user_id=user_id,
                username=username,
                message_length=len(message_text),
            )

            # Process message based on type
            message_type = payload.get("type", "text")

            if message_type == "command" and message_text.startswith("/"):
                await self._handle_command(message_text, user, socket)
            else:
                # Regular message broadcast
                broadcast_payload = {
                    "user": {"id": user_id, "username": username},
                    "text": message_text,
                    "timestamp": asyncio.get_event_loop().time(),
                    "type": message_type,
                }

                await self.broadcast("new_message", broadcast_payload)

            # Record metrics
            metrics = await get_phoenix_metrics()
            await metrics.record_message_received(self.topic, "message")

        except Exception as e:
            logger.error("room.message_error", topic=self.topic, error=str(e))
            # Record error metric
            metrics = await get_phoenix_metrics()
            await metrics.record_error("message_processing", "channel")

        finally:
            # Record processing time
            duration = asyncio.get_event_loop().time() - start_time
            metrics = await get_phoenix_metrics()
            await metrics.record_message_processing_time(self.topic, "message", duration)

    async def on_leave(self, reason: str, socket) -> None:
        """Handle channel leaves with cleanup."""
        logger.info("room.leave", topic=self.topic, reason=reason)

        # In a real implementation, we'd need to track user_id -> socket mapping
        # For now, this is a placeholder for presence cleanup
        # await presence.untrack(user_id, self.topic)

        # Record metrics
        metrics = await get_phoenix_metrics()
        await metrics.record_channel_leave(self.topic)

    async def _handle_command(self, command: str, user: dict, socket) -> None:
        """Handle chat commands."""
        parts = command.split()
        cmd = parts[0].lower()

        if cmd == "/help":
            help_text = """
Available commands:
/help - Show this help message
/users - List online users
/stats - Show room statistics
/ping - Test connectivity
"""
            await self.push("system_message", {"text": help_text.strip(), "type": "help"})

        elif cmd == "/users":
            presence = get_presence()
            presences = await presence.list(self.topic)
            user_list = []

            for pid, presence_state in presences.items():
                if presence_state.metas:
                    meta = presence_state.metas[0]  # Get first meta
                    user_list.append(
                        {
                            "id": pid,
                            "username": meta.user_id,
                            "role": meta.metadata.get("role", "user") if meta.metadata else "user",
                            "joined_at": meta.online_at,
                        }
                    )

            await self.push("user_list", {"users": user_list, "count": len(user_list)})

        elif cmd == "/stats":
            stats = await self._get_room_stats()
            await self.push("room_stats", stats)

        elif cmd == "/ping":
            await self.push("pong", {"timestamp": asyncio.get_event_loop().time()})

        else:
            await self.push("system_message", {"text": f"Unknown command: {cmd}", "type": "error"})

    async def _get_room_info(self) -> dict:
        """Get room information."""
        presence = get_presence()
        user_count = await presence.presence_count_for_topic(self.topic)

        return {
            "topic": self.topic,
            "user_count": user_count,
            "created_at": asyncio.get_event_loop().time(),
            "features": ["presence", "commands", "rate_limiting", "metrics"],
        }

    async def _get_room_stats(self) -> dict:
        """Get detailed room statistics."""
        presence = get_presence()
        metrics_registry = await get_phoenix_metrics()
        all_metrics = await metrics_registry.registry.get_all_metrics()

        return {
            "topic": self.topic,
            "active_users": await presence.presence_count_for_topic(self.topic),
            "total_topics": await presence.topic_count(),
            "metrics": {
                "connections": all_metrics["gauges"].get("pyphoenix_active_connections", 0),
                "channels": all_metrics["gauges"].get("pyphoenix_active_channels", 0),
                "messages_sent": all_metrics["counters"].get("pyphoenix_messages_sent_total", 0),
                "messages_received": all_metrics["counters"].get("pyphoenix_messages_received_total", 0),
            },
        }


@app.channel("private:*")
class PrivateChannel(Channel):
    """Private channel for direct messages and notifications."""

    def __init__(self, topic: str, params: dict | None = None, socket=None):
        super().__init__(topic, params, socket)
        self.use_middleware(LoggingMiddleware())
        self.use_middleware(AuthMiddleware(authenticate_user))

    async def on_join(self, payload: dict, socket) -> dict:
        """Handle private channel joins with authorization."""
        user = payload.get("authenticated_user")
        if not user:
            raise Exception("Authentication required for private channels")

        # Extract target user from topic (private:user123)
        target_user = self.topic.split(":")[-1]
        current_user = user["user_id"]

        # Only allow users to join their own private channel or admins
        if current_user != target_user and user.get("role") != "admin":
            raise Exception("Not authorized to join this private channel")

        logger.info(
            "private.joined",
            topic=self.topic,
            user_id=current_user,
            target_user=target_user,
        )

        return {"status": "ok", "response": {"joined": self.topic, "user": user}}

    async def on_direct_message(self, payload: dict, socket) -> None:
        """Handle direct messages."""
        user = payload.get("authenticated_user")
        if not user:
            return

        message_payload = {
            "from": user,
            "text": payload.get("text", ""),
            "timestamp": asyncio.get_event_loop().time(),
        }

        await self.broadcast("direct_message", message_payload)

        # Record metrics
        metrics = await get_phoenix_metrics()
        await metrics.record_message_received(self.topic, "direct_message")


async def demonstrate_client_interaction():
    """Demonstrate client-server interaction."""
    logger.info("demo.starting_client_interaction")

    try:
        # Create client socket
        client = ClientSocket("ws://localhost:4001/socket", {"token": "valid_token"})

        # Set up event handlers
        @client.on_connect
        async def on_connect():
            logger.info("client.connected")

        @client.on_disconnect
        async def on_disconnect():
            logger.info("client.disconnected")

        # Connect to server
        await client.connect()

        # Join a room
        room_channel = client.channel("room:demo", {"token": "valid_token"})

        @room_channel.on("presence_state")
        async def on_presence_state(payload, ref):
            logger.info("client.presence_state_received", count=len(payload.get("presences", {})))

        @room_channel.on("new_message")
        async def on_new_message(payload, ref):
            user = payload.get("user", {})
            text = payload.get("text", "")
            logger.info("client.message_received", username=user.get("username"), text=text)

        @room_channel.on("system_message")
        async def on_system_message(payload, ref):
            logger.info("client.system_message", text=payload.get("text"))

        # Join the channel
        join_response = await room_channel.join()
        logger.info("client.channel_joined", response=join_response)

        # Send some messages
        await room_channel.push("message", {"text": "Hello from client!", "type": "text"})
        await asyncio.sleep(1)

        await room_channel.push("message", {"text": "/help", "type": "command"})
        await asyncio.sleep(1)

        await room_channel.push("message", {"text": "/users", "type": "command"})
        await asyncio.sleep(1)

        await room_channel.push("message", {"text": "/stats", "type": "command"})
        await asyncio.sleep(2)

        # Leave and disconnect
        await room_channel.leave()
        await client.disconnect()

        logger.info("demo.client_interaction_complete")

    except Exception as e:
        logger.error("demo.client_error", error=str(e))


async def run_advanced_server():
    """Run the advanced server demonstration."""
    logger.info("server.starting_advanced", config=config.to_dict())

    try:
        # Start metrics collection
        await get_phoenix_metrics()
        logger.info("server.metrics_initialized")

        # Set up presence cleanup
        presence = get_presence()

        async def cleanup_stale_presences():
            """Periodic cleanup of stale presences."""
            while True:
                try:
                    await asyncio.sleep(60)  # Run every minute
                    cleaned = await presence.cleanup_stale_presences(max_age_seconds=300)  # 5 minutes
                    if cleaned > 0:
                        logger.info("server.presence_cleanup", cleaned_count=cleaned)
                except Exception as e:
                    logger.error("server.cleanup_error", error=str(e))

        # Start background tasks
        cleanup_task = asyncio.create_task(cleanup_stale_presences())

        # Run client demonstration
        client_task = asyncio.create_task(demonstrate_client_interaction())

        # In a real server, this would start the WebSocket transport
        # await app.start("localhost", 4001)

        # For demo, just wait for client interaction to complete
        await client_task

        # Show final metrics
        all_metrics = await (await get_phoenix_metrics()).registry.get_all_metrics()
        logger.info("server.final_metrics", metrics=all_metrics)

        # Cleanup
        cleanup_task.cancel()

        logger.info("server.demo_complete")

    except KeyboardInterrupt:
        logger.info("server.interrupted")
    except Exception as e:
        logger.error("server.error", error=str(e))
        raise


if __name__ == "__main__":
    print("PyPhoenix Advanced Server Example")
    print("=================================")
    print("Demonstrating Phase 1+ features:")
    print("- Configuration system")
    print("- Middleware stack (logging, auth, rate limiting)")
    print("- Metrics collection")
    print("- Enhanced presence tracking")
    print("- Client-server interaction")
    print("- Command handling")
    print("- Background tasks")
    print()

    asyncio.run(run_advanced_server())

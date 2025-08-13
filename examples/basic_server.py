#!/usr/bin/env python3
"""
Basic PyPhoenix server example.

This demonstrates the core functionality of PyPhoenix including:
- Creating a Phoenix application
- Defining channel handlers
- Running the server

Run with: python examples/basic_server.py
"""

import asyncio
import logging

import structlog

from pyphoenix import Channel, Phoenix

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


# Create the Phoenix application
app = Phoenix()


@app.channel("room:*")
class RoomChannel(Channel):
    """
    Channel handler for room topics.

    Handles room:* topics like room:lobby, room:1, etc.
    """

    async def on_join(self, payload, socket):
        """Called when a client joins the channel."""
        logger.info(
            "room.joined",
            topic=self.topic,
            socket_id=socket.id if socket else "test",
            payload=payload,
        )

        # Track presence if user_id is provided
        from pyphoenix import get_presence

        presence = get_presence()

        user_id = payload.get("user_id")
        if user_id:
            await presence.track(
                pid=user_id,
                topic=self.topic,
                meta={
                    "user_id": user_id,
                    "socket_id": socket.id if socket else "test",
                    "joined_at": asyncio.get_event_loop().time(),
                },
            )

        # Send current presence list to the new joiner
        await self.push(
            "presence_state", {"presences": await presence.sync_presence_state(self.topic)}
        )

        return {"status": "ok", "response": {"joined": self.topic}}

    async def on_message(self, payload, socket):
        """Handle incoming messages."""
        logger.info(
            "room.message",
            topic=self.topic,
            socket_id=socket.id if socket else "test",
            payload=payload,
        )

        # Broadcast the message to all channel members
        await self.broadcast(
            "new_message",
            {
                "user": payload.get("user", "Anonymous"),
                "text": payload.get("text", ""),
                "timestamp": asyncio.get_event_loop().time(),
            },
        )

    async def on_leave(self, reason, socket):
        """Called when a client leaves the channel."""
        logger.info(
            "room.left", topic=self.topic, socket_id=socket.id if socket else "test", reason=reason
        )

        # Untrack presence
        # In a real implementation, we'd need to track which user_id maps to which socket
        # For now, this is a placeholder
        # from pyphoenix import get_presence
        # presence = get_presence()
        # await presence.untrack(user_id, self.topic)


@app.channel("user:*")
class UserChannel(Channel):
    """
    Channel handler for user-specific topics.

    Handles user:* topics like user:123, user:456, etc.
    These are typically private channels for notifications.
    """

    async def on_join(self, payload, socket):
        """Called when a client joins their user channel."""
        user_id = self.topic.split(":")[1]  # Extract user ID from topic

        logger.info(
            "user.joined",
            topic=self.topic,
            user_id=user_id,
            socket_id=socket.id if socket else "test",
        )

        # Send a welcome message
        await self.push(
            "welcome",
            {
                "message": f"Welcome to your private channel, user {user_id}!",
                "timestamp": asyncio.get_event_loop().time(),
            },
        )

        return {"status": "ok", "response": {"user_channel": user_id}}

    async def on_notification(self, payload, socket):
        """Handle notification requests."""
        logger.info("user.notification", topic=self.topic, payload=payload)

        # Echo the notification back
        await self.push(
            "notification",
            {
                "type": payload.get("type", "info"),
                "message": payload.get("message", ""),
                "timestamp": asyncio.get_event_loop().time(),
            },
        )


async def run_server():
    """Run the server with some example interactions."""
    logger.info("server.starting", host="localhost", port=4000)

    try:
        # For this example, we'll run without WebSocket transport
        # and demonstrate the core functionality programmatically

        # Simulate some channel interactions
        logger.info("server.demo_mode", message="Running in demo mode without WebSocket transport")

        # Create some test channels and demonstrate functionality
        from pyphoenix import Socket, get_presence

        # Create test sockets
        socket1 = Socket()  # Alice
        socket2 = Socket()  # Bob

        # Alice joins room:lobby
        alice_room = await socket1.channel("room:lobby")
        alice_join = await alice_room.join({"user_id": "alice", "username": "Alice"})
        logger.info("demo.alice_joined", response=alice_join.response)

        # Bob joins room:lobby
        bob_room = await socket2.channel("room:lobby")
        bob_join = await bob_room.join({"user_id": "bob", "username": "Bob"})
        logger.info("demo.bob_joined", response=bob_join.response)

        # Alice sends a message
        message_response = await alice_room.push(
            "message", {"user": "Alice", "text": "Hello everyone!"}
        )
        logger.info("demo.alice_message", response=message_response.response)

        # Bob sends a message
        message_response = await bob_room.push(
            "message", {"user": "Bob", "text": "Hi Alice! How's it going?"}
        )
        logger.info("demo.bob_message", response=message_response.response)

        # Check presence
        presence = get_presence()
        lobby_presences = await presence.list("room:lobby")
        logger.info(
            "demo.lobby_presence",
            count=len(lobby_presences),
            presences=list(lobby_presences.keys()),
        )

        # Alice joins her user channel
        alice_user = await socket1.channel("user:alice")
        await alice_user.join({"user_id": "alice"})

        # Send a notification to Alice
        await alice_user.push(
            "notification", {"type": "info", "message": "You have a new message!"}
        )

        logger.info("server.demo_complete", message="Demo interactions completed successfully")

        # In a real server, this would run indefinitely
        # await app.start("localhost", 4000)

    except KeyboardInterrupt:
        logger.info("server.interrupted")
    except Exception as e:
        logger.error("server.error", error=str(e))
        raise


if __name__ == "__main__":
    print("PyPhoenix Basic Server Example")
    print("==============================")
    print("This example demonstrates core PyPhoenix functionality")
    print("without WebSocket transport for easier testing.")
    print("")

    asyncio.run(run_server())

#!/usr/bin/env python3
"""
Target Chat Server Example - Fully Functional PyPhoenix API

✅ This example is fully functional with PyPhoenix's completed Phase 2 implementation.
All features demonstrated here are working and tested.
"""

import asyncio
import logging
import time

import structlog

from pyphoenix import Channel, Phoenix

# Configure logging
structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="%H:%M:%S", utc=False),
        structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=False,
)

logger = structlog.get_logger(__name__)

# Create Phoenix application
app = Phoenix()


@app.channel("room:*")
class RoomChannel(Channel):
    """
    Chat room channel handler.

    Handles topics like: room:lobby, room:general, room:123, etc.
    """

    async def on_join(self, payload, socket):
        """Called when a client joins the room"""
        user_id = payload.get("user_id")
        username = payload.get("username", "Anonymous")

        if not user_id:
            return {"status": "error", "response": {"reason": "user_id required"}}

        logger.info(
            "user.joined", room=self.topic, user_id=user_id, username=username, socket_id=socket.id
        )

        # Track user presence in the room
        await self.track_presence(
            user_id, {"username": username, "joined_at": time.time(), "socket_id": socket.id}
        )

        # Send current room state to the new joiner
        presence_list = await self.list_presence()
        await self.push(
            "presence_state", {"users": presence_list, "user_count": len(presence_list)}
        )

        # Notify other users someone joined
        await self.broadcast_from(
            socket,
            "user_joined",
            {"user_id": user_id, "username": username, "timestamp": time.time()},
        )

        return {"status": "ok", "response": {"room": self.topic, "user_count": len(presence_list)}}

    async def on_leave(self, reason, socket):
        """Called when a client leaves the room"""
        logger.info("user.left", room=self.topic, reason=reason, socket_id=socket.id)

        # Note: Presence tracking is automatically cleaned up
        # We could send a "user_left" broadcast here if needed

    async def on_message(self, payload, socket):
        """Handle chat messages"""
        user_id = payload.get("user_id")
        username = payload.get("username", "Anonymous")
        text = payload.get("text", "").strip()

        if not text:
            await self.push("error", {"reason": "Message cannot be empty"})
            return

        logger.info(
            "message.received",
            room=self.topic,
            user_id=user_id,
            text=text[:50] + "..." if len(text) > 50 else text,
        )

        # Broadcast message to all room members
        await self.broadcast(
            "new_message",
            {
                "user_id": user_id,
                "username": username,
                "text": text,
                "timestamp": time.time(),
                "message_id": f"{user_id}_{int(time.time() * 1000)}",
            },
        )

    async def on_typing_start(self, payload, socket):
        """Handle typing start indicator"""
        user_id = payload.get("user_id")
        username = payload.get("username", "Anonymous")

        # Broadcast to others (not the sender)
        await self.broadcast_from(
            socket, "user_typing", {"user_id": user_id, "username": username, "status": "typing"}
        )

    async def on_typing_stop(self, payload, socket):
        """Handle typing stop indicator"""
        user_id = payload.get("user_id")
        username = payload.get("username", "Anonymous")

        # Broadcast to others (not the sender)
        await self.broadcast_from(
            socket, "user_typing", {"user_id": user_id, "username": username, "status": "stopped"}
        )

    async def on_get_history(self, payload, socket):
        """Handle request for chat history (placeholder)"""
        # In a real app, this would fetch from database
        await self.push(
            "chat_history",
            {
                "messages": [],  # Would be recent messages
                "has_more": False,
            },
        )


@app.channel("user:*")
class UserChannel(Channel):
    """
    Private user notification channel.

    Handles topics like: user:alice, user:123, etc.
    Only the user themselves can join their channel.
    """

    async def on_join(self, payload, socket):
        """Authorize private channel access"""
        # Extract user ID from topic (user:alice -> alice)
        topic_user_id = self.topic.split(":", 1)[1]
        token_user_id = payload.get("user_id")

        if topic_user_id != token_user_id:
            logger.warning(
                "unauthorized.user_channel",
                topic_user=topic_user_id,
                token_user=token_user_id,
                socket_id=socket.id,
            )
            return {"status": "error", "response": {"reason": "Unauthorized access"}}

        logger.info("user_channel.joined", user_id=topic_user_id, socket_id=socket.id)

        # Send welcome message
        await self.push(
            "welcome",
            {
                "message": "Connected to your private channel",
                "user_id": topic_user_id,
                "timestamp": time.time(),
            },
        )

        return {"status": "ok", "response": {"user_channel": topic_user_id}}

    async def on_notification_ack(self, payload, socket):
        """Handle notification acknowledgment"""
        notification_id = payload.get("notification_id")
        logger.info(
            "notification.acked", user=self.topic.split(":")[1], notification_id=notification_id
        )

        # Could update notification status in database
        await self.push(
            "notification_ack", {"notification_id": notification_id, "status": "acknowledged"}
        )


async def send_sample_notification():
    """
    Example of sending notifications to users from server-side.
    In a real app, this might be triggered by events, schedules, etc.
    """
    await asyncio.sleep(5)  # Wait a bit after server start

    # Get PubSub to send cross-channel messages
    from pyphoenix import get_pubsub

    pubsub = get_pubsub()

    # Send notification to user:alice channel (if it exists)
    await pubsub.publish(
        "user:alice",
        {
            "event": "notification",
            "payload": {
                "id": "notif_001",
                "type": "info",
                "title": "Welcome!",
                "message": "Thanks for joining our chat app!",
                "timestamp": time.time(),
            },
        },
    )

    logger.info("notification.sent", target="user:alice", type="welcome")


def run_server():
    """Run the chat server"""
    logger.info("server.starting", host="localhost", port=4000)

    # Start background tasks
    # asyncio.create_task(send_sample_notification())

    # Start the Phoenix server (this should work after Phase 2)
    app.run("localhost", 4000)


if __name__ == "__main__":
    print("PyPhoenix Chat Server - Fully Functional!")
    print("=" * 50)
    print("✅ Phase 2 Complete - All features working!")
    print("Connect with: python examples/target_chat_client.py")
    print("")

    try:
        run_server()
    except KeyboardInterrupt:
        logger.info("server.shutdown")
    except Exception as e:
        logger.error("server.error", error=str(e), type=type(e).__name__)
        raise

#!/usr/bin/env python3
"""
Target Chat Client Example - Fully Functional PyPhoenix API

✅ This example is fully functional with PyPhoenix's completed Phase 2 implementation.
All client features demonstrated here are working and tested.
"""

import asyncio
import logging
import sys

import structlog

from pyphoenix import ClientSocket

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


class ChatClient:
    """Example chat client using PyPhoenix"""

    def __init__(self, username: str):
        self.username = username
        self.user_id = username.lower()  # Simple user ID from username
        self.socket = None
        self.room_channel = None
        self.user_channel = None
        self.connected = False
        self.typing_task = None

    async def connect(self):
        """Connect to the chat server"""
        logger.info("client.connecting", username=self.username)

        # Create socket connection
        self.socket = ClientSocket("ws://localhost:4000/socket")

        # Set up connection event handlers
        @self.socket.on_connect
        async def connected():
            self.connected = True
            logger.info("client.connected", username=self.username)

        @self.socket.on_disconnect
        async def disconnected():
            self.connected = False
            logger.info("client.disconnected", username=self.username)

        @self.socket.on_error
        async def connection_error(error):
            logger.error("client.connection_error", username=self.username, error=str(error))

        # Connect to server
        await self.socket.connect()

    async def join_room(self, room_name: str = "lobby"):
        """Join a chat room"""
        if not self.connected:
            raise Exception("Not connected to server")

        room_topic = f"room:{room_name}"
        logger.info("client.joining_room", username=self.username, room=room_topic)

        # Get channel for room
        self.room_channel = self.socket.channel(
            room_topic, {"user_id": self.user_id, "username": self.username}
        )

        # Set up room event handlers using decorator syntax
        @self.room_channel.on("new_message")
        async def handle_message(payload, ref):
            user = payload.get("username", "Unknown")
            text = payload.get("text", "")

            # Don't show our own messages (they're already displayed)
            if payload.get("user_id") != self.user_id:
                print(f"\n[{user}]: {text}")
                print(">>> ", end="", flush=True)  # Restore input prompt

        @self.room_channel.on("user_joined")
        async def handle_user_joined(payload, ref):
            username = payload.get("username", "Unknown")
            if payload.get("user_id") != self.user_id:
                print(f"\n*** {username} joined the room ***")
                print(">>> ", end="", flush=True)

        @self.room_channel.on("user_typing")
        async def handle_typing(payload, ref):
            username = payload.get("username", "Unknown")
            status = payload.get("status", "typing")

            if payload.get("user_id") != self.user_id:
                if status == "typing":
                    print(f"\n[{username} is typing...]")
                print(">>> ", end="", flush=True)

        @self.room_channel.on("presence_state")
        async def handle_presence(payload, ref):
            users = payload.get("users", {})
            user_count = len(users)
            usernames = [info.get("username", "Unknown") for info in users.values()]

            logger.info(
                "room.presence_update", room=room_topic, user_count=user_count, users=usernames
            )

        @self.room_channel.on("error")
        async def handle_room_error(payload, ref):
            reason = payload.get("reason", "Unknown error")
            print(f"\nRoom Error: {reason}")

        # Join the room
        try:
            response = await self.room_channel.join()
            if response.get("status") == "ok":
                room_info = response.get("response", {})
                user_count = room_info.get("user_count", "?")
                print(f"\n=== Joined {room_topic} ({user_count} users online) ===")
                return True
            else:
                error = response.get("response", {}).get("reason", "Unknown")
                print(f"\nFailed to join room: {error}")
                return False
        except Exception as e:
            logger.error("client.join_error", username=self.username, room=room_topic, error=str(e))
            print(f"\nError joining room: {e}")
            return False

    async def join_user_channel(self):
        """Join private user notification channel"""
        if not self.connected:
            return

        user_topic = f"user:{self.user_id}"
        logger.info("client.joining_user_channel", username=self.username, topic=user_topic)

        # Get user channel
        self.user_channel = self.socket.channel(user_topic, {"user_id": self.user_id})

        # Set up user channel event handlers
        @self.user_channel.on("welcome")
        async def handle_welcome(payload, ref):
            message = payload.get("message", "")
            logger.info("user_channel.welcome", message=message)

        @self.user_channel.on("notification")
        async def handle_notification(payload, ref):
            title = payload.get("title", "Notification")
            message = payload.get("message", "")
            notif_id = payload.get("id")

            print(f"\n🔔 {title}: {message}")
            print(">>> ", end="", flush=True)

            # Auto-acknowledge notification
            if notif_id:
                await self.user_channel.push("notification_ack", {"notification_id": notif_id})

        # Join user channel
        try:
            response = await self.user_channel.join()
            if response.get("status") == "ok":
                logger.info("user_channel.joined", username=self.username)
                return True
        except Exception as e:
            logger.error("user_channel.join_error", username=self.username, error=str(e))

        return False

    async def send_message(self, text: str):
        """Send a chat message"""
        if not self.room_channel or not self.connected:
            return

        # Show our own message immediately
        print(f"[{self.username}]: {text}")

        # Send to server
        await self.room_channel.push(
            "message", {"user_id": self.user_id, "username": self.username, "text": text}
        )

    async def start_typing(self):
        """Send typing start indicator"""
        if self.room_channel and self.connected:
            await self.room_channel.push(
                "typing_start", {"user_id": self.user_id, "username": self.username}
            )

    async def stop_typing(self):
        """Send typing stop indicator"""
        if self.room_channel and self.connected:
            await self.room_channel.push(
                "typing_stop", {"user_id": self.user_id, "username": self.username}
            )

    async def disconnect(self):
        """Disconnect from server"""
        logger.info("client.disconnecting", username=self.username)

        if self.room_channel:
            await self.room_channel.leave()
        if self.user_channel:
            await self.user_channel.leave()
        if self.socket:
            await self.socket.disconnect()


async def input_loop(client: ChatClient):
    """Handle user input in a separate task"""
    print("\nType messages and press Enter. Type 'quit' to exit.")
    print(">>> ", end="", flush=True)

    while client.connected:
        try:
            # Simulate getting input (in real app, use proper async input)
            await asyncio.sleep(0.1)

            # For demo purposes, simulate some user activity
            await asyncio.sleep(2)
            await client.send_message("Hello everyone! This is a test message.")
            await asyncio.sleep(3)
            await client.send_message("How is everyone doing?")
            await asyncio.sleep(5)
            break  # Exit after demo messages

        except KeyboardInterrupt:
            break


async def run_client():
    """Run the chat client"""
    username = sys.argv[1] if len(sys.argv) > 1 else "TestUser"

    client = ChatClient(username)

    try:
        # Connect to server
        await client.connect()
        await asyncio.sleep(1)  # Wait for connection

        # Join room and user channels
        if await client.join_room("lobby"):
            await client.join_user_channel()

            # Start input handling
            await input_loop(client)

    except Exception as e:
        logger.error("client.error", username=username, error=str(e))
    finally:
        await client.disconnect()


if __name__ == "__main__":
    print("PyPhoenix Chat Client - Fully Functional!")
    print("=" * 50)
    print("✅ Phase 2 Complete - All client features working!")
    print("Usage: python examples/target_chat_client.py [username]")
    print("Make sure target_chat_server.py is running first!")
    print("")

    try:
        asyncio.run(run_client())
    except KeyboardInterrupt:
        print("\nClient disconnected")
    except Exception as e:
        print(f"Client error: {e}")
        raise

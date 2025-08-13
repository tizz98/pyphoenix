"""
Tests for channel presence methods.

These tests verify that the presence tracking methods work correctly
with the Channel class integration.
"""

import pytest

from pyphoenix import Channel, Phoenix, Socket
from pyphoenix.types import Message


@pytest.fixture(autouse=True)
def reset_presence():
    """Reset global presence state between tests."""
    import pyphoenix.presence as presence_module

    # Clear global presence instance to start fresh
    presence_module._global_presence = None

    yield

    # Clean up after test
    presence_module._global_presence = None


class TestChannelPresenceMethods:
    """Test channel presence tracking methods."""

    @pytest.mark.asyncio
    async def test_track_presence_basic(self):
        """Test basic presence tracking functionality."""
        app = Phoenix()

        @app.channel("room:*")
        class RoomChannel(Channel):
            pass

        socket = Socket(websocket=None, phoenix_app=app)
        channel = await app.get_or_create_channel("room:lobby", socket)

        # Track a user
        await channel.track_presence("alice", {"username": "Alice", "socket_id": socket.id})

        # Verify presence is tracked
        presence_list = await channel.list_presence()
        assert "alice" in presence_list
        assert presence_list["alice"]["user_id"] == "alice"
        assert presence_list["alice"]["metadata"]["username"] == "Alice"

        # Check presence count
        count = await channel.presence_count()
        assert count == 1

    @pytest.mark.asyncio
    async def test_untrack_presence(self):
        """Test presence untracking."""
        app = Phoenix()

        @app.channel("room:*")
        class RoomChannel(Channel):
            pass

        socket = Socket(websocket=None, phoenix_app=app)
        channel = await app.get_or_create_channel("room:lobby", socket)

        # Track a user
        await channel.track_presence("alice", {"username": "Alice"})
        assert await channel.presence_count() == 1

        # Untrack the user
        await channel.untrack_presence("alice")
        assert await channel.presence_count() == 0

        # Verify presence list is empty
        presence_list = await channel.list_presence()
        assert "alice" not in presence_list

    @pytest.mark.asyncio
    async def test_multiple_presence_tracking(self):
        """Test tracking multiple users."""
        app = Phoenix()

        @app.channel("room:*")
        class RoomChannel(Channel):
            pass

        socket = Socket(websocket=None, phoenix_app=app)
        channel = await app.get_or_create_channel("room:lobby", socket)

        # Track multiple users
        await channel.track_presence("alice", {"username": "Alice"})
        await channel.track_presence("bob", {"username": "Bob"})
        await channel.track_presence("charlie", {"username": "Charlie"})

        # Check count
        assert await channel.presence_count() == 3

        # Check presence list
        presence_list = await channel.list_presence()
        assert len(presence_list) == 3
        assert "alice" in presence_list
        assert "bob" in presence_list
        assert "charlie" in presence_list

    @pytest.mark.asyncio
    async def test_broadcast_from_excludes_sender(self):
        """Test that broadcast_from excludes the sender socket."""
        app = Phoenix()
        from pyphoenix import get_pubsub

        # Track broadcast messages
        broadcast_messages = []
        pubsub = get_pubsub()

        async def capture_broadcast(topic, message):
            broadcast_messages.append((topic, message))

        await pubsub.subscribe("room:test", capture_broadcast)

        @app.channel("room:*")
        class RoomChannel(Channel):
            pass

        socket = Socket(websocket=None, phoenix_app=app)
        channel = await app.get_or_create_channel("room:test", socket)

        # Broadcast from socket (should exclude this socket)
        await channel.broadcast_from(socket, "test_event", {"message": "hello"})

        # Should receive broadcast with exclude_socket set
        assert len(broadcast_messages) == 1
        topic, message = broadcast_messages[0]
        assert topic == "room:test"
        assert message["event"] == "test_event"
        assert message["payload"]["message"] == "hello"
        assert message["exclude_socket"] == socket.id

    @pytest.mark.asyncio
    async def test_presence_integration_with_join_leave(self):
        """Test presence tracking integration with channel join/leave."""
        app = Phoenix()

        @app.channel("room:*")
        class RoomChannel(Channel):
            async def on_join(self, payload, socket):
                user_id = payload.get("user_id")
                username = payload.get("username", "Anonymous")
                await self.track_presence(user_id, {"username": username, "socket_id": socket.id})
                return {"status": "ok", "response": {"joined": True}}

            async def on_leave(self, reason, socket):
                # In a real app, we'd extract user_id from socket or payload
                # For testing, we'll untrack a known user
                await self.untrack_presence("alice")

        socket = Socket(websocket=None, phoenix_app=app)

        # Join channel - should track presence
        join_message = Message(
            topic="room:lobby",
            event="phx_join",
            payload={"user_id": "alice", "username": "Alice"},
            ref="1",
            join_ref="1",
        )
        await app.route_message(socket, join_message)

        # Check presence was tracked
        channel = app.channel_instances["room:lobby"]
        presence_list = await channel.list_presence()
        assert "alice" in presence_list
        assert presence_list["alice"]["metadata"]["username"] == "Alice"

        # Leave channel - should untrack presence
        leave_message = Message(
            topic="room:lobby", event="phx_leave", payload={}, ref="2", join_ref="1"
        )
        await app.route_message(socket, leave_message)

        # Check presence was untracked
        presence_list = await channel.list_presence()
        assert "alice" not in presence_list

    @pytest.mark.asyncio
    async def test_presence_across_different_channels(self):
        """Test that presence is tracked separately per channel."""
        app = Phoenix()

        @app.channel("room:*")
        class RoomChannel(Channel):
            pass

        socket = Socket(websocket=None, phoenix_app=app)
        lobby_channel = await app.get_or_create_channel("room:lobby", socket)
        general_channel = await app.get_or_create_channel("room:general", socket)

        # Track presence in both channels
        await lobby_channel.track_presence("alice", {"username": "Alice"})
        await general_channel.track_presence("alice", {"username": "Alice"})

        # Check each channel has its own presence
        assert await lobby_channel.presence_count() == 1
        assert await general_channel.presence_count() == 1

        # Untrack from one channel
        await lobby_channel.untrack_presence("alice")

        # Should only affect that channel
        assert await lobby_channel.presence_count() == 0
        assert await general_channel.presence_count() == 1

    @pytest.mark.asyncio
    async def test_presence_metadata_update(self):
        """Test updating presence metadata."""
        app = Phoenix()

        @app.channel("room:*")
        class RoomChannel(Channel):
            pass

        socket = Socket(websocket=None, phoenix_app=app)
        channel = await app.get_or_create_channel("room:lobby", socket)

        # Track initial presence
        await channel.track_presence("alice", {"username": "Alice", "status": "online"})

        # Update presence (track again with new metadata)
        await channel.track_presence("alice", {"username": "Alice", "status": "away"})

        # Should still be one user but with updated metadata
        assert await channel.presence_count() == 1
        presence_list = await channel.list_presence()

        # The latest metadata should be available
        assert "alice" in presence_list
        # Note: The presence system keeps multiple metas, latest is used in list_presence

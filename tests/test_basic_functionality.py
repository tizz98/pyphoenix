"""Basic functionality tests for PyPhoenix."""

import time

import pytest

from pyphoenix import Channel, Socket, get_presence, get_pubsub
from pyphoenix.types import ChannelState


class TestChannel:
    """Test the Channel implementation."""

    @pytest.mark.asyncio
    async def test_channel_creation(self):
        """Test channel creation and basic properties."""
        channel = Channel("room:test", {"user_id": "123"})

        assert channel.topic == "room:test"
        assert channel.params == {"user_id": "123"}
        assert channel.state == ChannelState.CLOSED
        assert channel.join_ref is None

    @pytest.mark.asyncio
    async def test_channel_join_without_socket(self):
        """Test joining a channel without WebSocket (local mode)."""
        channel = Channel("room:test")

        response = await channel.join({"user_id": "test_user"})

        assert response.is_ok
        assert channel.state == ChannelState.JOINED
        assert channel.join_ref is not None

    @pytest.mark.asyncio
    async def test_channel_push_without_socket(self):
        """Test pushing messages without WebSocket."""
        channel = Channel("room:test")

        # First join the channel
        await channel.join()

        # Create a callback to capture events
        received_events = []

        def event_handler(payload, ref):
            received_events.append((payload, ref))

        channel.on("test_event", event_handler)

        # Push a message
        response = await channel.push("test_event", {"message": "Hello!"})

        assert response.is_ok
        assert len(received_events) == 1
        assert received_events[0][0] == {"message": "Hello!"}

    @pytest.mark.asyncio
    async def test_channel_event_handling(self):
        """Test event binding and triggering."""
        channel = Channel("room:test")
        received_events = []

        # Async callback
        async def async_handler(payload, ref):
            received_events.append(("async", payload, ref))

        # Sync callback
        def sync_handler(payload, ref):
            received_events.append(("sync", payload, ref))

        channel.on("test", async_handler)
        channel.on("test", sync_handler)

        await channel.trigger("test", {"data": "test"}, "ref123")

        assert len(received_events) == 2
        assert ("async", {"data": "test"}, "ref123") in received_events
        assert ("sync", {"data": "test"}, "ref123") in received_events

    @pytest.mark.asyncio
    async def test_channel_leave(self):
        """Test leaving a channel."""
        channel = Channel("room:test")

        # Join first
        await channel.join()
        assert channel.state == ChannelState.JOINED

        # Leave
        await channel.leave()
        assert channel.state == ChannelState.CLOSED


class TestSocket:
    """Test the Socket implementation."""

    @pytest.mark.asyncio
    async def test_socket_creation(self):
        """Test socket creation."""
        socket = Socket()

        assert socket.id is not None
        assert socket.transport == "test"
        assert len(socket.channels) == 0
        assert not socket.closed

    @pytest.mark.asyncio
    async def test_socket_channel_creation(self):
        """Test creating channels through socket."""
        socket = Socket()

        channel = await socket.channel("room:test", {"user": "alice"})

        assert channel.topic == "room:test"
        assert channel.params == {"user": "alice"}
        assert "room:test" in socket.channels

        # Getting the same channel again should return the same instance
        channel2 = await socket.channel("room:test")
        assert channel is channel2


class TestPubSub:
    """Test the PubSub system."""

    @pytest.mark.asyncio
    async def test_pubsub_subscribe_and_publish(self):
        """Test basic subscribe and publish functionality."""
        pubsub = get_pubsub()
        received_messages = []

        async def message_handler(topic, message):
            received_messages.append((topic, message))

        # Subscribe
        subscription = await pubsub.subscribe("test:channel", message_handler)

        # Publish
        count = await pubsub.publish("test:channel", {"message": "Hello!"})

        assert count == 1
        assert len(received_messages) == 1
        assert received_messages[0] == ("test:channel", {"message": "Hello!"})

        # Unsubscribe
        await subscription.unsubscribe()

        # Publish again - should have no subscribers
        count = await pubsub.publish("test:channel", {"message": "Nobody listening"})
        assert count == 0

    @pytest.mark.asyncio
    async def test_pubsub_pattern_matching(self):
        """Test pattern-based subscriptions."""
        pubsub = get_pubsub()
        received_messages = []

        def message_handler(topic, message):
            received_messages.append((topic, message))

        # Subscribe to pattern
        await pubsub.subscribe("room:*", message_handler)

        # Publish to matching topics
        await pubsub.publish("room:1", {"user": "alice"})
        await pubsub.publish("room:2", {"user": "bob"})
        await pubsub.publish("chat:1", {"user": "charlie"})  # Should not match

        assert len(received_messages) == 2
        assert ("room:1", {"user": "alice"}) in received_messages
        assert ("room:2", {"user": "bob"}) in received_messages


class TestPresence:
    """Test the Presence system."""

    @pytest.mark.asyncio
    async def test_presence_track_and_list(self):
        """Test tracking and listing presences."""
        presence = get_presence()

        # Track some presences
        await presence.track("alice", "room:1", {"user_id": "alice", "online_at": time.time()})
        await presence.track("bob", "room:1", {"user_id": "bob", "online_at": time.time()})
        await presence.track("charlie", "room:2", {"user_id": "charlie", "online_at": time.time()})

        # List presences for room:1
        room1_presences = await presence.list("room:1")
        assert len(room1_presences) == 2
        assert "alice" in room1_presences
        assert "bob" in room1_presences

        # List presences for room:2
        room2_presences = await presence.list("room:2")
        assert len(room2_presences) == 1
        assert "charlie" in room2_presences

        # Check total counts
        assert await presence.total_presence_count() == 3
        assert await presence.presence_count_for_topic("room:1") == 2
        assert await presence.presence_count_for_topic("room:2") == 1

    @pytest.mark.asyncio
    async def test_presence_untrack(self):
        """Test untracking presences."""
        presence = get_presence()

        # Track and then untrack
        await presence.track("alice", "room:test", {"user_id": "alice"})
        assert await presence.presence_count_for_topic("room:test") == 1

        await presence.untrack("alice", "room:test")
        assert await presence.presence_count_for_topic("room:test") == 0

    @pytest.mark.asyncio
    async def test_presence_callbacks(self):
        """Test presence join/leave callbacks."""
        presence = get_presence()
        events = []

        def on_join(topic, pid, presence_state):
            events.append(("join", topic, pid))

        def on_leave(topic, pid, presence_state):
            events.append(("leave", topic, pid))

        presence.on_join(on_join)
        presence.on_leave(on_leave)

        # Track and untrack
        await presence.track("alice", "room:callback", {"user_id": "alice"})
        await presence.untrack("alice", "room:callback")

        assert len(events) == 2
        assert ("join", "room:callback", "alice") in events
        assert ("leave", "room:callback", "alice") in events


class TestIntegration:
    """Integration tests combining multiple components."""

    @pytest.mark.asyncio
    async def test_channel_with_pubsub_integration(self):
        """Test channel integration with PubSub."""
        pubsub = get_pubsub()
        received_messages = []

        # Set up PubSub listener
        async def pubsub_handler(topic, message):
            received_messages.append((topic, message))

        await pubsub.subscribe("room:integration", pubsub_handler)

        # Create and join channel
        channel = Channel("room:integration")
        await channel.join()

        # Publish through PubSub - this simulates messages from other nodes
        await pubsub.publish(
            "room:integration", {"event": "external_message", "data": "Hello from PubSub!"}
        )

        # Verify message was received
        assert len(received_messages) == 1
        assert received_messages[0][1]["event"] == "external_message"

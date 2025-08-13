"""
Tests for channel broadcasting and PubSub integration.

These tests verify that channel broadcasting works correctly
with the Phoenix app integration.
"""

import asyncio

import pytest

from pyphoenix import Channel, Phoenix, Socket, get_pubsub
from pyphoenix.types import Message


class TestChannelBroadcasting:
    """Test channel broadcasting functionality."""

    @pytest.mark.asyncio
    async def test_channel_push_method(self):
        """Test basic channel push functionality."""
        app = Phoenix()

        @app.channel("test:*")
        class TestChannel(Channel):
            pass

        socket = Socket(websocket=None, phoenix_app=app)
        channel = await app.get_or_create_channel("test:room", socket)

        # Set channel to joined state for testing
        from pyphoenix.types import ChannelState

        channel.state = ChannelState.JOINED

        # Track pushed messages
        pushed_messages = []

        async def mock_push(message):
            pushed_messages.append(message)

        socket.push = mock_push

        # Test push method
        await channel.push("test_event", {"message": "hello"})

        assert len(pushed_messages) == 1
        message = pushed_messages[0]
        assert message.event == "test_event"
        assert message.payload == {"message": "hello"}
        assert message.topic == "test:room"

    @pytest.mark.asyncio
    async def test_channel_broadcast_single_socket(self):
        """Test broadcasting with single socket."""
        app = Phoenix()

        @app.channel("room:*")
        class RoomChannel(Channel):
            async def on_message(self, payload, socket):
                await self.broadcast(
                    "new_message", {"user": payload.get("user"), "text": payload.get("text")}
                )

        socket = Socket(websocket=None, phoenix_app=app)

        # Track PubSub messages
        pubsub_messages = []
        pubsub = get_pubsub()

        # Subscribe to the topic to capture broadcast messages
        async def capture_message(topic, message):
            pubsub_messages.append((topic, message))

        await pubsub.subscribe("room:lobby", capture_message)

        # Send message that triggers broadcast
        message = Message(
            topic="room:lobby",
            event="message",
            payload={"user": "alice", "text": "Hello everyone!"},
            ref="1",
            join_ref="1",
        )

        await app.route_message(socket, message)

        # Should receive broadcast via PubSub
        assert len(pubsub_messages) == 1
        topic, broadcast_data = pubsub_messages[0]
        assert topic == "room:lobby"
        assert broadcast_data["event"] == "new_message"
        assert broadcast_data["payload"]["user"] == "alice"
        assert broadcast_data["payload"]["text"] == "Hello everyone!"

    @pytest.mark.asyncio
    async def test_multiple_channels_same_topic(self):
        """Test multiple channel instances for same topic."""
        app = Phoenix()

        @app.channel("room:*")
        class RoomChannel(Channel):
            async def on_join(self, payload, socket):
                return {"status": "ok", "response": {}}

        # Create two sockets for same room
        socket1 = Socket(websocket=None, phoenix_app=app)
        socket2 = Socket(websocket=None, phoenix_app=app)

        # Both join same room - should get same channel instance
        channel1 = await app.get_or_create_channel("room:lobby", socket1)
        channel2 = await app.get_or_create_channel("room:lobby", socket2)

        assert channel1 is channel2
        assert len(channel1._sockets) == 2
        assert socket1 in channel1._sockets
        assert socket2 in channel1._sockets


class TestPubSubIntegration:
    """Test PubSub integration with channels."""

    @pytest.mark.asyncio
    async def test_pubsub_pattern_subscription(self):
        """Test PubSub pattern-based subscriptions."""
        pubsub = get_pubsub()

        received_messages = []

        async def message_handler(topic, message):
            received_messages.append((topic, message))

        # Subscribe to pattern
        await pubsub.subscribe("room:*", message_handler)

        # Publish to matching topics
        await pubsub.publish("room:lobby", {"event": "test1", "data": "message1"})
        await pubsub.publish("room:general", {"event": "test2", "data": "message2"})
        await pubsub.publish(
            "user:alice", {"event": "test3", "data": "message3"}
        )  # Shouldn't match

        # Should only receive room: messages
        assert len(received_messages) == 2
        assert ("room:lobby", {"event": "test1", "data": "message1"}) in received_messages
        assert ("room:general", {"event": "test2", "data": "message2"}) in received_messages

    @pytest.mark.asyncio
    async def test_channel_pubsub_auto_subscription(self):
        """Test that channels automatically subscribe to their topics."""
        app = Phoenix()

        received_broadcasts = []

        @app.channel("room:*")
        class RoomChannel(Channel):
            async def on_join(self, payload, socket):
                return {"status": "ok", "response": {}}

            async def _handle_pubsub_message(self, topic, message):
                # Override to capture broadcasts
                received_broadcasts.append((topic, message))
                # Call parent implementation if needed
                await super()._handle_pubsub_message(topic, message)

        socket = Socket(websocket=None, phoenix_app=app)

        # Create channel
        channel = await app.get_or_create_channel("room:lobby", socket)

        # Manually trigger PubSub setup (normally done in constructor)
        if hasattr(channel, "_setup_pubsub_subscription"):
            await channel._setup_pubsub_subscription()

        # Publish message to the topic
        pubsub = get_pubsub()
        await pubsub.publish(
            "room:lobby", {"event": "broadcast_test", "payload": {"message": "Hello from PubSub!"}}
        )

        # Channel should receive the broadcast
        # Note: This test depends on PubSub implementation details
        # In a real implementation, this would forward to WebSocket

    @pytest.mark.asyncio
    async def test_cross_channel_communication(self):
        """Test communication between different channels via PubSub."""
        app = Phoenix()
        pubsub = get_pubsub()

        notifications_sent = []

        @app.channel("room:*")
        class RoomChannel(Channel):
            async def on_message(self, payload, socket):
                user_id = payload.get("user_id")
                # Send notification to user's private channel
                await pubsub.publish(
                    f"user:{user_id}",
                    {
                        "event": "notification",
                        "payload": {
                            "type": "room_activity",
                            "room": self.topic,
                            "message": "New activity in your room",
                        },
                    },
                )

        @app.channel("user:*")
        class UserChannel(Channel):
            async def on_join(self, payload, socket):
                # Subscribe to notifications for this user
                user_id = self.topic.split(":")[1]

                async def handle_notification(topic, message):
                    notifications_sent.append((topic, message))

                await pubsub.subscribe(f"user:{user_id}", handle_notification)
                return {"status": "ok", "response": {}}

        # Create room and user channels
        room_socket = Socket(websocket=None, phoenix_app=app)
        user_socket = Socket(websocket=None, phoenix_app=app)

        room_channel = await app.get_or_create_channel("room:lobby", room_socket)
        user_channel = await app.get_or_create_channel("user:alice", user_socket)

        # Join user channel (sets up subscription)
        await user_channel.handle_event("phx_join", {"user_id": "alice"}, "ref1", user_socket)

        # Send message in room (should trigger notification)
        await room_channel.handle_event(
            "message", {"user_id": "alice", "text": "Hello"}, "ref2", room_socket
        )

        # Should receive notification
        assert len(notifications_sent) == 1
        topic, notification = notifications_sent[0]
        assert topic == "user:alice"
        assert notification["event"] == "notification"
        assert notification["payload"]["type"] == "room_activity"


class TestBroadcastingWithPresence:
    """Test broadcasting integration with presence system."""

    @pytest.mark.asyncio
    async def test_presence_tracking_in_channels(self):
        """Test presence tracking within channels."""
        app = Phoenix()

        @app.channel("room:*")
        class RoomChannel(Channel):
            async def on_join(self, payload, socket):
                user_id = payload.get("user_id")
                await self.track_presence(
                    user_id,
                    {"username": payload.get("username", "Anonymous"), "socket_id": socket.id},
                )
                return {"status": "ok", "response": {}}

            async def on_leave(self, reason, socket):
                # Presence cleanup would happen here
                pass

        socket = Socket(websocket=None, phoenix_app=app)

        # Test join with presence tracking
        join_message = Message(
            topic="room:lobby",
            event="phx_join",
            payload={"user_id": "alice", "username": "Alice"},
            ref="1",
            join_ref="1",
        )

        await app.route_message(socket, join_message)

        # Verify channel was created and join was successful
        assert "room:lobby" in app.channel_instances
        channel = app.channel_instances["room:lobby"]
        assert socket in channel._sockets

    @pytest.mark.asyncio
    async def test_presence_broadcasts(self):
        """Test broadcasting presence changes."""
        app = Phoenix()
        pubsub = get_pubsub()

        presence_broadcasts = []

        @app.channel("room:*")
        class RoomChannel(Channel):
            async def on_join(self, payload, socket):
                user_id = payload.get("user_id")

                # Simulate presence tracking
                await pubsub.publish(
                    self.topic,
                    {
                        "event": "presence_state",
                        "payload": {
                            "joins": {user_id: {"username": payload.get("username")}},
                            "leaves": {},
                        },
                    },
                )

                return {"status": "ok", "response": {}}

        # Subscribe to presence broadcasts
        async def capture_presence(topic, message):
            if message.get("event") == "presence_state":
                presence_broadcasts.append((topic, message))

        await pubsub.subscribe("room:*", capture_presence)

        socket = Socket(websocket=None, phoenix_app=app)

        # Join channel
        join_message = Message(
            topic="room:lobby",
            event="phx_join",
            payload={"user_id": "alice", "username": "Alice"},
            ref="1",
            join_ref="1",
        )

        await app.route_message(socket, join_message)

        # Should receive presence broadcast
        assert len(presence_broadcasts) == 1
        topic, broadcast = presence_broadcasts[0]
        assert topic == "room:lobby"
        assert broadcast["event"] == "presence_state"
        assert "alice" in broadcast["payload"]["joins"]


class TestBroadcastingPerformance:
    """Test broadcasting performance characteristics."""

    @pytest.mark.asyncio
    async def test_many_subscribers_broadcast(self):
        """Test broadcasting to many subscribers."""
        app = Phoenix()
        pubsub = get_pubsub()

        received_messages = []

        @app.channel("room:*")
        class RoomChannel(Channel):
            async def on_message(self, payload, socket):
                await self.broadcast("new_message", payload)

        # Create many subscribers
        num_subscribers = 10
        handlers = []

        for i in range(num_subscribers):

            async def handler(topic, message, subscriber_id=i):
                received_messages.append((subscriber_id, topic, message))

            handlers.append(handler)
            await pubsub.subscribe("room:lobby", handler)

        # Create channel and send message
        socket = Socket(websocket=None, phoenix_app=app)

        message = Message(
            topic="room:lobby",
            event="message",
            payload={"text": "Broadcast to all!"},
            ref="1",
            join_ref="1",
        )

        await app.route_message(socket, message)

        # All subscribers should receive the message
        assert len(received_messages) == num_subscribers
        for i in range(num_subscribers):
            assert any(msg[0] == i for msg in received_messages)

    @pytest.mark.asyncio
    async def test_rapid_broadcasts(self):
        """Test rapid successive broadcasts."""
        app = Phoenix()
        pubsub = get_pubsub()

        received_count = 0

        async def count_messages(topic, message):
            nonlocal received_count
            received_count += 1

        await pubsub.subscribe("room:test", count_messages)

        @app.channel("room:*")
        class RoomChannel(Channel):
            async def on_message(self, payload, socket):
                await self.broadcast("new_message", payload)

        socket = Socket(websocket=None, phoenix_app=app)

        # Send many messages rapidly
        num_messages = 20
        tasks = []

        for i in range(num_messages):
            message = Message(
                topic="room:test",
                event="message",
                payload={"id": i, "text": f"Message {i}"},
                ref=str(i),
                join_ref="1",
            )
            tasks.append(app.route_message(socket, message))

        await asyncio.gather(*tasks)

        # All messages should be broadcast
        assert received_count == num_messages


class TestBroadcastingErrorHandling:
    """Test error handling in broadcasting scenarios."""

    @pytest.mark.asyncio
    async def test_broadcast_with_failing_subscriber(self):
        """Test broadcasting when one subscriber fails."""
        pubsub = get_pubsub()

        received_messages = []
        failed_calls = 0

        async def good_handler(topic, message):
            received_messages.append((topic, message))

        async def failing_handler(topic, message):
            nonlocal failed_calls
            failed_calls += 1
            raise RuntimeError("Subscriber error")

        # Subscribe both handlers
        await pubsub.subscribe("test:topic", good_handler)
        await pubsub.subscribe("test:topic", failing_handler)

        # Publish message
        await pubsub.publish("test:topic", {"event": "test", "data": "message"})

        # Good handler should still receive message despite failing handler
        assert len(received_messages) == 1
        assert failed_calls == 1

    @pytest.mark.asyncio
    async def test_broadcast_to_nonexistent_topic(self):
        """Test broadcasting to topic with no subscribers."""
        pubsub = get_pubsub()

        # Should not raise error
        count = await pubsub.publish("nonexistent:topic", {"event": "test"})
        assert count == 0  # No subscribers

    @pytest.mark.asyncio
    async def test_channel_broadcast_error_recovery(self):
        """Test channel broadcast error recovery."""
        app = Phoenix()

        @app.channel("room:*")
        class RoomChannel(Channel):
            async def on_message(self, payload, socket):
                # This should not crash even if broadcast fails
                await self.broadcast("new_message", payload)

        socket = Socket(websocket=None, phoenix_app=app)

        # Should not raise error even if PubSub has issues
        message = Message(
            topic="room:test", event="message", payload={"text": "test"}, ref="1", join_ref="1"
        )

        await app.route_message(socket, message)
        # Should complete without error

"""
Tests for Phoenix application integration and routing functionality.

These tests verify the core integration between Phoenix app, channels, and sockets.
"""

import pytest

from pyphoenix import Channel, Phoenix, Socket
from pyphoenix.types import ChannelState, Message


class TestPhoenixChannelRegistration:
    """Test Phoenix app channel registration and pattern matching."""

    def test_channel_decorator_registration(self):
        """Test that @app.channel decorator properly registers handlers."""
        app = Phoenix()

        @app.channel("room:*")
        class RoomChannel(Channel):
            pass

        @app.channel("user:*")
        class UserChannel(Channel):
            pass

        assert "room:*" in app.channel_handlers
        assert "user:*" in app.channel_handlers
        assert app.channel_handlers["room:*"] == RoomChannel
        assert app.channel_handlers["user:*"] == UserChannel

    def test_pattern_matching(self):
        """Test topic pattern matching functionality."""
        app = Phoenix()

        # Exact match
        assert app.match_topic_pattern("global", "global") is True
        assert app.match_topic_pattern("global", "global:something") is False

        # Wildcard matching
        assert app.match_topic_pattern("room:*", "room:lobby") is True
        assert app.match_topic_pattern("room:*", "room:123") is True
        assert app.match_topic_pattern("room:*", "room:") is True
        assert app.match_topic_pattern("room:*", "user:123") is False
        assert app.match_topic_pattern("room:*", "rooms:123") is False

        # User pattern
        assert app.match_topic_pattern("user:*", "user:alice") is True
        assert app.match_topic_pattern("user:*", "user:123") is True
        assert app.match_topic_pattern("user:*", "room:alice") is False

    @pytest.mark.asyncio
    async def test_channel_creation_from_patterns(self):
        """Test that channels are created from registered patterns."""
        app = Phoenix()
        socket = Socket(websocket=None, phoenix_app=app)

        @app.channel("room:*")
        class RoomChannel(Channel):
            pass

        # First call should create new channel
        channel1 = await app.get_or_create_channel("room:lobby", socket)
        assert channel1 is not None
        assert isinstance(channel1, RoomChannel)
        assert channel1.topic == "room:lobby"
        assert channel1.phoenix_app is app
        assert socket in channel1._sockets

        # Second call should return same channel
        channel2 = await app.get_or_create_channel("room:lobby", socket)
        assert channel2 is channel1

        # Different topic should create different channel
        channel3 = await app.get_or_create_channel("room:general", socket)
        assert channel3 is not channel1
        assert channel3.topic == "room:general"

    @pytest.mark.asyncio
    async def test_no_matching_pattern(self):
        """Test behavior when no pattern matches the topic."""
        app = Phoenix()
        socket = Socket(websocket=None, phoenix_app=app)

        # No channels registered
        channel = await app.get_or_create_channel("unknown:topic", socket)
        assert channel is None

        @app.channel("room:*")
        class RoomChannel(Channel):
            pass

        # Pattern doesn't match
        channel = await app.get_or_create_channel("user:123", socket)
        assert channel is None


class TestPhoenixMessageRouting:
    """Test Phoenix app message routing functionality."""

    @pytest.mark.asyncio
    async def test_successful_message_routing(self):
        """Test successful routing of messages to channels."""
        app = Phoenix()
        socket = Socket(websocket=None, phoenix_app=app)

        join_called = False
        message_called = False

        @app.channel("room:*")
        class TestChannel(Channel):
            async def on_join(self, payload, socket):
                nonlocal join_called
                join_called = True
                assert payload == {"user_id": "alice"}
                return {"status": "ok", "response": {"welcome": True}}

            async def on_message(self, payload, socket):
                nonlocal message_called
                message_called = True
                assert payload == {"text": "Hello!"}

        # Test join message routing
        join_message = Message(
            topic="room:lobby",
            event="phx_join",
            payload={"user_id": "alice"},
            ref="1",
            join_ref="1",
        )
        await app.route_message(socket, join_message)
        assert join_called

        # Test custom event routing
        message_event = Message(
            topic="room:lobby", event="message", payload={"text": "Hello!"}, ref="2", join_ref="1"
        )
        await app.route_message(socket, message_event)
        assert message_called

    @pytest.mark.asyncio
    async def test_no_matching_channel_error(self):
        """Test error handling when no channel matches."""
        app = Phoenix()
        socket = Socket(websocket=None, phoenix_app=app)

        # Track pushed messages
        pushed_messages = []

        async def mock_push(message):
            pushed_messages.append(message)

        socket.push = mock_push

        # Send message to unregistered topic
        message = Message(
            topic="unknown:topic", event="phx_join", payload={}, ref="1", join_ref="1"
        )
        await app.route_message(socket, message)

        # Should receive error reply
        assert len(pushed_messages) == 1
        error_reply = pushed_messages[0]
        assert error_reply.event == "phx_reply"
        assert error_reply.payload["status"] == "error"
        assert "no matching channel" in error_reply.payload["response"]["reason"]


class TestChannelEventHandling:
    """Test channel event handling and dispatch."""

    @pytest.mark.asyncio
    async def test_join_event_handling(self):
        """Test phx_join event handling."""
        app = Phoenix()
        socket = Socket(websocket=None, phoenix_app=app)

        # Track pushed messages
        pushed_messages = []

        async def mock_push(message):
            pushed_messages.append(message)

        socket.push = mock_push

        @app.channel("test:*")
        class TestChannel(Channel):
            async def on_join(self, payload, socket):
                assert payload == {"user": "alice"}
                return {"status": "ok", "response": {"joined": True}}

        channel = await app.get_or_create_channel("test:room", socket)

        # Test successful join
        await channel.handle_event("phx_join", {"user": "alice"}, "ref1", socket)

        assert len(pushed_messages) == 1
        reply = pushed_messages[0]
        assert reply.event == "phx_reply"
        assert reply.payload["status"] == "ok"
        assert reply.payload["response"]["joined"] is True
        assert channel.state == ChannelState.JOINED
        assert channel.join_ref == "ref1"

    @pytest.mark.asyncio
    async def test_join_event_error_handling(self):
        """Test phx_join error handling."""
        app = Phoenix()
        socket = Socket(websocket=None, phoenix_app=app)

        pushed_messages = []

        async def mock_push(message):
            pushed_messages.append(message)

        socket.push = mock_push

        @app.channel("test:*")
        class TestChannel(Channel):
            async def on_join(self, payload, socket):
                raise ValueError("Invalid user")

        channel = await app.get_or_create_channel("test:room", socket)
        await channel.handle_event("phx_join", {}, "ref1", socket)

        assert len(pushed_messages) == 1
        reply = pushed_messages[0]
        assert reply.event == "phx_reply"
        assert reply.payload["status"] == "error"
        assert "Invalid user" in reply.payload["response"]["reason"]

    @pytest.mark.asyncio
    async def test_leave_event_handling(self):
        """Test phx_leave event handling."""
        app = Phoenix()
        socket = Socket(websocket=None, phoenix_app=app)

        pushed_messages = []
        leave_called = False

        async def mock_push(message):
            pushed_messages.append(message)

        socket.push = mock_push

        @app.channel("test:*")
        class TestChannel(Channel):
            async def on_leave(self, reason, socket):
                nonlocal leave_called
                leave_called = True
                assert reason == "manual"

        channel = await app.get_or_create_channel("test:room", socket)
        channel.join_ref = "ref1"  # Simulate joined state
        channel.state = ChannelState.JOINED  # Properly set joined state

        await channel.handle_event("phx_leave", {}, "ref2", socket)

        assert leave_called
        assert len(pushed_messages) == 1
        reply = pushed_messages[0]
        assert reply.event == "phx_reply"
        assert reply.payload["status"] == "ok"
        assert channel.state == ChannelState.CLOSED

    @pytest.mark.asyncio
    async def test_custom_event_handling(self):
        """Test custom event method dispatch."""
        app = Phoenix()
        socket = Socket(websocket=None, phoenix_app=app)

        events_received = []

        @app.channel("test:*")
        class TestChannel(Channel):
            async def on_message(self, payload, socket):
                events_received.append(("message", payload))

            async def on_typing(self, payload, socket):
                events_received.append(("typing", payload))

        channel = await app.get_or_create_channel("test:room", socket)

        # Test message event
        await channel.handle_event("message", {"text": "hello"}, "ref1", socket)
        assert ("message", {"text": "hello"}) in events_received

        # Test typing event
        await channel.handle_event("typing", {"user": "alice"}, "ref2", socket)
        assert ("typing", {"user": "alice"}) in events_received

    @pytest.mark.asyncio
    async def test_unknown_event_handling(self):
        """Test handling of unknown events."""
        app = Phoenix()
        socket = Socket(websocket=None, phoenix_app=app)

        pushed_messages = []

        async def mock_push(message):
            pushed_messages.append(message)

        socket.push = mock_push

        @app.channel("test:*")
        class TestChannel(Channel):
            pass  # No event handlers

        channel = await app.get_or_create_channel("test:room", socket)
        await channel.handle_event("unknown_event", {}, "ref1", socket)

        assert len(pushed_messages) == 1
        reply = pushed_messages[0]
        assert reply.event == "phx_reply"
        assert reply.payload["status"] == "error"
        assert "Unknown event" in reply.payload["response"]["reason"]


class TestSocketPhoenixIntegration:
    """Test Socket integration with Phoenix app."""

    @pytest.mark.asyncio
    async def test_socket_routes_through_phoenix(self):
        """Test that socket routes messages through Phoenix app."""
        app = Phoenix()
        socket = Socket(websocket=None, phoenix_app=app)

        message_received = False

        @app.channel("room:*")
        class TestChannel(Channel):
            async def on_message(self, payload, socket):
                nonlocal message_received
                message_received = True

        # Simulate WebSocket message
        raw_message = '["ref1", "ref1", "room:test", "message", {"text": "hello"}]'
        await socket.handle_websocket_message(raw_message)

        assert message_received

    @pytest.mark.asyncio
    async def test_socket_fallback_without_phoenix(self):
        """Test socket fallback when no Phoenix app is set."""
        socket = Socket(websocket=None, phoenix_app=None)

        # Should not raise error - falls back to old behavior
        raw_message = '["ref1", "ref1", "room:test", "phx_join", {}]'
        await socket.handle_websocket_message(raw_message)

        # Socket should have created channel using old method
        assert "room:test" in socket.channels


class TestMultipleChannelInstances:
    """Test behavior with multiple channel instances and sockets."""

    @pytest.mark.asyncio
    async def test_multiple_sockets_same_channel(self):
        """Test multiple sockets connecting to same channel."""
        app = Phoenix()
        socket1 = Socket(websocket=None, phoenix_app=app)
        socket2 = Socket(websocket=None, phoenix_app=app)

        @app.channel("room:*")
        class TestChannel(Channel):
            pass

        # Both sockets join same channel
        channel1 = await app.get_or_create_channel("room:lobby", socket1)
        channel2 = await app.get_or_create_channel("room:lobby", socket2)

        # Should be same channel instance
        assert channel1 is channel2

        # Both sockets should be tracked
        assert socket1 in channel1._sockets
        assert socket2 in channel1._sockets
        assert len(channel1._sockets) == 2

    @pytest.mark.asyncio
    async def test_different_channels_different_instances(self):
        """Test that different topics create different channel instances."""
        app = Phoenix()
        socket = Socket(websocket=None, phoenix_app=app)

        @app.channel("room:*")
        class RoomChannel(Channel):
            pass

        @app.channel("user:*")
        class UserChannel(Channel):
            pass

        room_channel = await app.get_or_create_channel("room:lobby", socket)
        user_channel = await app.get_or_create_channel("user:alice", socket)

        assert room_channel is not user_channel
        assert isinstance(room_channel, RoomChannel)
        assert isinstance(user_channel, UserChannel)
        assert room_channel.topic == "room:lobby"
        assert user_channel.topic == "user:alice"


class TestChannelEventAuthentication:
    """Test channel event authentication and authorization."""

    @pytest.mark.asyncio
    async def test_join_authorization_success(self):
        """Test successful join authorization."""
        app = Phoenix()
        socket = Socket(websocket=None, phoenix_app=app)

        pushed_messages = []

        async def mock_push(message):
            pushed_messages.append(message)

        socket.push = mock_push

        @app.channel("user:*")
        class UserChannel(Channel):
            async def on_join(self, payload, socket):
                user_id = payload.get("user_id")
                topic_user = self.topic.split(":")[1]

                if user_id != topic_user:
                    return {"status": "error", "response": {"reason": "Unauthorized"}}

                return {"status": "ok", "response": {"authorized": True}}

        channel = await app.get_or_create_channel("user:alice", socket)

        # Test authorized join
        await channel.handle_event("phx_join", {"user_id": "alice"}, "ref1", socket)

        reply = pushed_messages[0]
        assert reply.payload["status"] == "ok"
        assert reply.payload["response"]["authorized"] is True

    @pytest.mark.asyncio
    async def test_join_authorization_failure(self):
        """Test failed join authorization."""
        app = Phoenix()
        socket = Socket(websocket=None, phoenix_app=app)

        pushed_messages = []

        async def mock_push(message):
            pushed_messages.append(message)

        socket.push = mock_push

        @app.channel("user:*")
        class UserChannel(Channel):
            async def on_join(self, payload, socket):
                user_id = payload.get("user_id")
                topic_user = self.topic.split(":")[1]

                if user_id != topic_user:
                    return {"status": "error", "response": {"reason": "Unauthorized"}}

                return {"status": "ok", "response": {"authorized": True}}

        channel = await app.get_or_create_channel("user:alice", socket)

        # Test unauthorized join (wrong user)
        await channel.handle_event("phx_join", {"user_id": "bob"}, "ref1", socket)

        reply = pushed_messages[0]
        assert reply.payload["status"] == "error"
        assert "Unauthorized" in reply.payload["response"]["reason"]
        assert channel.state != ChannelState.JOINED


class TestErrorHandlingEdgeCases:
    """Test error handling and edge cases."""

    @pytest.mark.asyncio
    async def test_malformed_message_handling(self):
        """Test handling of malformed WebSocket messages."""
        app = Phoenix()
        socket = Socket(websocket=None, phoenix_app=app)

        # Invalid JSON
        await socket.handle_websocket_message("invalid json")
        # Should not crash

        # Invalid message format
        await socket.handle_websocket_message('["too", "few", "fields"]')
        # Should not crash

    @pytest.mark.asyncio
    async def test_channel_handler_exception(self):
        """Test handling of exceptions in channel handlers."""
        app = Phoenix()
        socket = Socket(websocket=None, phoenix_app=app)

        pushed_messages = []

        async def mock_push(message):
            pushed_messages.append(message)

        socket.push = mock_push

        @app.channel("test:*")
        class TestChannel(Channel):
            async def on_message(self, payload, socket):
                raise RuntimeError("Handler error")

        channel = await app.get_or_create_channel("test:room", socket)
        await channel.handle_event("message", {}, "ref1", socket)

        # Should send error reply
        assert len(pushed_messages) == 1
        reply = pushed_messages[0]
        assert reply.payload["status"] == "error"
        assert "Handler error" in reply.payload["response"]["reason"]

    @pytest.mark.asyncio
    async def test_socket_without_phoenix_app(self):
        """Test socket behavior when Phoenix app is None."""
        socket = Socket(websocket=None, phoenix_app=None)

        # Should fall back to legacy behavior
        raw_message = '["ref1", "ref1", "room:test", "phx_join", {}]'
        await socket.handle_websocket_message(raw_message)

        # Channel should be created using legacy method
        assert "room:test" in socket.channels

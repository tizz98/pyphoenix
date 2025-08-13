"""
WebSocket integration tests for PyPhoenix.

These tests verify end-to-end WebSocket functionality including
Phoenix app, transport, and client integration.
"""

import asyncio
import json

import pytest

from pyphoenix import Channel, ClientSocket, Phoenix
from pyphoenix.socket import WebSocketTransport


class TestWebSocketTransportIntegration:
    """Test WebSocket transport integration with Phoenix app."""

    @pytest.mark.asyncio
    async def test_transport_phoenix_connection(self):
        """Test connecting WebSocket transport to Phoenix app."""
        app = Phoenix()
        transport = WebSocketTransport("localhost", 0)  # Use port 0 for testing

        # Before connection
        assert transport.phoenix_app is None

        # Connect transport to app
        transport.set_phoenix_app(app)
        assert transport.phoenix_app is app

    @pytest.mark.asyncio
    async def test_transport_socket_creation_with_phoenix(self):
        """Test that transport creates sockets with Phoenix app reference."""
        app = Phoenix()
        transport = WebSocketTransport("localhost", 0)
        transport.set_phoenix_app(app)

        # Mock websocket connection for testing
        class MockWebSocket:
            def __init__(self):
                self.closed = False

            async def close(self):
                self.closed = True

            def __aiter__(self):
                return self

            async def __anext__(self):
                # Return no messages (end iteration immediately)
                raise StopAsyncIteration

        mock_websocket = MockWebSocket()

        # Test socket creation through transport
        await transport.handle_connection(mock_websocket)

        # Socket is created and cleaned up immediately due to no messages
        # So we test that the socket was created with phoenix app reference
        # by checking it doesn't crash and transport.phoenix_app is set
        assert transport.phoenix_app is app

    @pytest.mark.asyncio
    async def test_full_phoenix_app_startup(self):
        """Test full Phoenix app startup process."""
        app = Phoenix()

        @app.channel("test:*")
        class TestChannel(Channel):
            async def on_join(self, payload, socket):
                return {"status": "ok", "response": {"joined": True}}

        # Start app (this should create and configure transport)
        try:
            await app.start("localhost", 0)  # Port 0 for testing

            # Verify transport is created and connected
            assert app.transport is not None
            assert app.transport.phoenix_app is app
            assert "test:*" in app.channel_handlers

        finally:
            # Clean up
            if app.transport:
                await app.stop()


class TestClientServerIntegration:
    """Test client-server integration scenarios."""

    @pytest.mark.asyncio
    async def test_client_socket_decorator_functionality(self):
        """Test client socket decorator functionality."""
        # Create client socket for testing (no actual connection)
        client = ClientSocket("ws://localhost:4000/socket")

        # Test channel creation
        channel = client.channel("room:test", {"user": "alice"})
        assert channel.topic == "room:test"
        assert channel.params == {"user": "alice"}

        # Test decorator syntax for event handlers
        events_received = []

        @channel.on("test_event")
        async def handle_test(payload, ref):
            events_received.append(("async", payload, ref))

        @channel.on("sync_event")
        def handle_sync(payload, ref):
            events_received.append(("sync", payload, ref))

        # Test triggering events
        await channel.trigger("test_event", {"message": "hello"}, "ref1")
        await channel.trigger("sync_event", {"message": "world"}, "ref2")

        assert len(events_received) == 2
        assert ("async", {"message": "hello"}, "ref1") in events_received
        assert ("sync", {"message": "world"}, "ref2") in events_received

    @pytest.mark.asyncio
    async def test_client_channel_join_leave_flow(self):
        """Test client channel join/leave flow."""
        client = ClientSocket("ws://localhost:4000/socket")
        channel = client.channel("room:test")

        # Initially closed
        from pyphoenix.types import ChannelState

        assert channel.state == ChannelState.CLOSED

        # Mock the socket connection for testing
        messages_sent = []

        async def mock_push(message):
            messages_sent.append(message)

        # Replace the push method for testing
        client.push = mock_push

        # Test join without connection (should raise error)
        with pytest.raises(Exception, match="Channel not joined"):
            await channel.push("test", {})

    @pytest.mark.asyncio
    async def test_message_serialization_format(self):
        """Test Phoenix message format serialization."""
        from pyphoenix.types import Message

        # Test message creation and serialization
        message = Message(
            topic="room:test", event="phx_join", payload={"user": "alice"}, ref="1", join_ref="1"
        )

        # Test to_list format (Phoenix wire format)
        message_list = message.to_list()
        assert message_list == ["1", "1", "room:test", "phx_join", {"user": "alice"}]

        # Test from_list deserialization
        deserialized = Message.from_list(message_list)
        assert deserialized.topic == "room:test"
        assert deserialized.event == "phx_join"
        assert deserialized.payload == {"user": "alice"}
        assert deserialized.ref == "1"
        assert deserialized.join_ref == "1"

        # Test JSON round-trip
        json_data = json.dumps(message_list)
        parsed_list = json.loads(json_data)
        final_message = Message.from_list(parsed_list)
        assert final_message.topic == message.topic
        assert final_message.event == message.event
        assert final_message.payload == message.payload


class TestChannelLifecycleIntegration:
    """Test channel lifecycle in integrated scenarios."""

    @pytest.mark.asyncio
    async def test_channel_join_success_flow(self):
        """Test successful channel join flow."""
        app = Phoenix()

        @app.channel("room:*")
        class RoomChannel(Channel):
            async def on_join(self, payload, socket):
                user_id = payload.get("user_id")
                if not user_id:
                    return {"status": "error", "response": {"reason": "user_id required"}}
                return {"status": "ok", "response": {"user": user_id, "room": self.topic}}

        # Simulate socket and join flow
        from pyphoenix import Socket

        socket = Socket(websocket=None, phoenix_app=app)

        # Test join message
        from pyphoenix.types import Message

        join_message = Message(
            topic="room:lobby",
            event="phx_join",
            payload={"user_id": "alice"},
            ref="1",
            join_ref="1",
        )

        # Track messages sent back to client
        sent_messages = []

        async def mock_push(message):
            sent_messages.append(message)

        socket.push = mock_push

        # Route the join message
        await app.route_message(socket, join_message)

        # Verify response
        assert len(sent_messages) == 1
        reply = sent_messages[0]
        assert reply.event == "phx_reply"
        assert reply.payload["status"] == "ok"
        assert reply.payload["response"]["user"] == "alice"
        assert reply.payload["response"]["room"] == "room:lobby"

    @pytest.mark.asyncio
    async def test_channel_join_error_flow(self):
        """Test channel join error flow."""
        app = Phoenix()

        @app.channel("room:*")
        class RoomChannel(Channel):
            async def on_join(self, payload, socket):
                user_id = payload.get("user_id")
                if not user_id:
                    return {"status": "error", "response": {"reason": "user_id required"}}
                return {"status": "ok", "response": {"user": user_id}}

        from pyphoenix import Socket
        from pyphoenix.types import Message

        socket = Socket(websocket=None, phoenix_app=app)
        sent_messages = []

        async def mock_push(message):
            sent_messages.append(message)

        socket.push = mock_push

        # Join without required user_id
        join_message = Message(
            topic="room:lobby",
            event="phx_join",
            payload={},  # Missing user_id
            ref="1",
            join_ref="1",
        )

        await app.route_message(socket, join_message)

        # Verify error response
        assert len(sent_messages) == 1
        reply = sent_messages[0]
        assert reply.event == "phx_reply"
        assert reply.payload["status"] == "error"
        assert "user_id required" in reply.payload["response"]["reason"]

    @pytest.mark.asyncio
    async def test_custom_event_after_join(self):
        """Test custom events after successful join."""
        app = Phoenix()

        @app.channel("room:*")
        class RoomChannel(Channel):
            async def on_join(self, payload, socket):
                return {"status": "ok", "response": {}}

            async def on_message(self, payload, socket):
                # Echo the message back
                text = payload.get("text", "")
                await self.push("echo", {"echo": f"You said: {text}"})

        from pyphoenix import Socket
        from pyphoenix.types import Message

        socket = Socket(websocket=None, phoenix_app=app)
        sent_messages = []

        async def mock_push(message):
            sent_messages.append(message)

        socket.push = mock_push

        # First join the channel
        join_message = Message(
            topic="room:lobby",
            event="phx_join",
            payload={"user_id": "alice"},
            ref="1",
            join_ref="1",
        )
        await app.route_message(socket, join_message)

        # Clear sent messages
        sent_messages.clear()

        # Send custom message
        message_event = Message(
            topic="room:lobby",
            event="message",
            payload={"text": "Hello world!"},
            ref="2",
            join_ref="1",
        )
        await app.route_message(socket, message_event)

        # Should receive echo message
        assert len(sent_messages) == 1
        echo_message = sent_messages[0]
        assert echo_message.event == "echo"
        assert echo_message.payload["echo"] == "You said: Hello world!"


class TestMultiClientScenarios:
    """Test scenarios with multiple clients."""

    @pytest.mark.asyncio
    async def test_multiple_clients_same_channel(self):
        """Test multiple clients joining the same channel."""
        app = Phoenix()

        @app.channel("room:*")
        class RoomChannel(Channel):
            async def on_join(self, payload, socket):
                return {"status": "ok", "response": {"joined": True}}

        from pyphoenix import Socket
        from pyphoenix.types import Message

        # Create two sockets (representing two clients)
        socket1 = Socket(websocket=None, phoenix_app=app)
        socket2 = Socket(websocket=None, phoenix_app=app)

        # Both join the same room
        join_message1 = Message(
            topic="room:lobby",
            event="phx_join",
            payload={"user_id": "alice"},
            ref="1",
            join_ref="1",
        )

        join_message2 = Message(
            topic="room:lobby", event="phx_join", payload={"user_id": "bob"}, ref="1", join_ref="1"
        )

        await app.route_message(socket1, join_message1)
        await app.route_message(socket2, join_message2)

        # Both should be connected to the same channel instance
        assert "room:lobby" in app.channel_instances
        channel = app.channel_instances["room:lobby"]
        assert socket1 in channel._sockets
        assert socket2 in channel._sockets
        assert len(channel._sockets) == 2

    @pytest.mark.asyncio
    async def test_clients_different_channels(self):
        """Test clients in different channels."""
        app = Phoenix()

        @app.channel("room:*")
        class RoomChannel(Channel):
            async def on_join(self, payload, socket):
                return {"status": "ok", "response": {}}

        @app.channel("user:*")
        class UserChannel(Channel):
            async def on_join(self, payload, socket):
                return {"status": "ok", "response": {}}

        from pyphoenix import Socket
        from pyphoenix.types import Message

        socket1 = Socket(websocket=None, phoenix_app=app)
        socket2 = Socket(websocket=None, phoenix_app=app)

        # Join different channel types
        room_join = Message(
            topic="room:lobby",
            event="phx_join",
            payload={"user_id": "alice"},
            ref="1",
            join_ref="1",
        )

        user_join = Message(
            topic="user:alice",
            event="phx_join",
            payload={"user_id": "alice"},
            ref="1",
            join_ref="1",
        )

        await app.route_message(socket1, room_join)
        await app.route_message(socket2, user_join)

        # Should have two different channel instances
        assert len(app.channel_instances) == 2
        assert "room:lobby" in app.channel_instances
        assert "user:alice" in app.channel_instances

        room_channel = app.channel_instances["room:lobby"]
        user_channel = app.channel_instances["user:alice"]

        assert isinstance(room_channel, RoomChannel)
        assert isinstance(user_channel, UserChannel)
        assert room_channel is not user_channel


class TestPerformanceAndStress:
    """Test performance characteristics and stress scenarios."""

    @pytest.mark.asyncio
    async def test_many_channels_creation(self):
        """Test creating many channels doesn't cause issues."""
        app = Phoenix()

        @app.channel("room:*")
        class RoomChannel(Channel):
            async def on_join(self, payload, socket):
                return {"status": "ok", "response": {}}

        from pyphoenix import Socket

        # Create many channels
        num_channels = 100
        for i in range(num_channels):
            socket = Socket(websocket=None, phoenix_app=app)
            channel = await app.get_or_create_channel(f"room:{i}", socket)
            assert channel is not None
            assert channel.topic == f"room:{i}"

        # All channels should be tracked
        assert len(app.channel_instances) == num_channels

    @pytest.mark.asyncio
    async def test_rapid_message_processing(self):
        """Test rapid message processing."""
        app = Phoenix()

        messages_processed = 0

        @app.channel("test:*")
        class TestChannel(Channel):
            async def on_message(self, payload, socket):
                nonlocal messages_processed
                messages_processed += 1

        from pyphoenix import Socket
        from pyphoenix.types import Message

        socket = Socket(websocket=None, phoenix_app=app)

        # Join channel first
        join_message = Message(
            topic="test:performance", event="phx_join", payload={}, ref="0", join_ref="0"
        )
        await app.route_message(socket, join_message)

        # Send many messages rapidly
        num_messages = 50
        tasks = []
        for i in range(num_messages):
            message = Message(
                topic="test:performance",
                event="message",
                payload={"id": i},
                ref=str(i + 1),
                join_ref="0",
            )
            tasks.append(app.route_message(socket, message))

        # Process all messages concurrently
        await asyncio.gather(*tasks)

        assert messages_processed == num_messages


class TestEdgeCasesIntegration:
    """Test edge cases in integration scenarios."""

    @pytest.mark.asyncio
    async def test_channel_cleanup_on_socket_disconnect(self):
        """Test channel cleanup when socket disconnects."""
        app = Phoenix()

        @app.channel("room:*")
        class RoomChannel(Channel):
            async def on_join(self, payload, socket):
                return {"status": "ok", "response": {}}

        from pyphoenix import Socket

        socket = Socket(websocket=None, phoenix_app=app)
        channel = await app.get_or_create_channel("room:test", socket)

        # Verify socket is tracked
        assert socket in channel._sockets

        # Simulate socket disconnect/cleanup
        await socket.close()

        # In a real implementation, we might want to clean up
        # channels when all sockets disconnect, but for now
        # we just verify the socket close doesn't crash
        assert socket.closed

    @pytest.mark.asyncio
    async def test_invalid_message_formats(self):
        """Test handling of various invalid message formats."""
        app = Phoenix()

        @app.channel("test:*")
        class TestChannel(Channel):
            pass

        from pyphoenix import Socket

        socket = Socket(websocket=None, phoenix_app=app)

        # Test various invalid JSON messages
        invalid_messages = [
            "not json at all",
            "{}",  # Not a list
            '["too", "few"]',  # Too few fields
            '["1", "2", "3", "4", "5", "6"]',  # Too many fields
            "[1, 2, 3, 4, 5]",  # Wrong types
        ]

        for invalid_msg in invalid_messages:
            # Should not crash
            await socket.handle_websocket_message(invalid_msg)

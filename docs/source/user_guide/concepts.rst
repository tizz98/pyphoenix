Core Concepts
=============

PyPhoenix is built around several core concepts that work together to provide
real-time communication capabilities. Understanding these concepts is essential
for building effective PyPhoenix applications.

Phoenix Application
-------------------

The Phoenix application is the main entry point that coordinates all other components.
It manages channel routing, handles connections, and provides the foundation for
real-time communication.

.. code-block:: python

   from pyphoenix import Phoenix
   
   app = Phoenix()
   # Register channels, configure middleware, etc.
   await app.start("localhost", 4000)

Key responsibilities:
- Channel registration and routing
- Connection lifecycle management  
- Integration with transport layers
- Global configuration and middleware

Channels
--------

Channels are the primary abstraction for real-time communication. They represent
a conversation on a specific topic between multiple participants.

**Topic-based Organization**

Channels are organized by topics using a hierarchical naming scheme:

- ``room:lobby`` - A chat room named "lobby"
- ``user:123`` - A private channel for user 123
- ``game:chess:match456`` - A chess game channel

**Stateful Communication**

Channels maintain state throughout their lifecycle:

1. **Joining** - Participants join channels to receive messages
2. **Messaging** - Participants send messages to the channel  
3. **Broadcasting** - Messages are broadcast to all participants
4. **Leaving** - Participants leave when done

.. code-block:: python

   @app.channel("room:*")
   class RoomChannel(Channel):
       async def on_join(self, payload, socket):
           # Handle new participants
           return {"status": "ok"}
           
       async def on_message(self, payload, socket):
           # Handle incoming messages
           await self.broadcast("new_message", payload)

PubSub (Publish/Subscribe)
--------------------------

The PubSub system provides decoupled message routing between components.
It allows publishers to send messages without knowing who will receive them,
and subscribers to receive messages without knowing who sent them.

**Pattern Matching**

PubSub supports pattern-based subscriptions using wildcards:

.. code-block:: python

   from pyphoenix import get_pubsub
   
   pubsub = get_pubsub()
   
   # Subscribe to all room messages
   await pubsub.subscribe("room:*", handle_room_message)
   
   # Publish a message  
   await pubsub.publish("room:lobby", {"type": "announcement", "text": "Welcome!"})

**Use Cases**

- Cross-channel communication
- System notifications
- Event-driven architecture
- Background task coordination

Presence Tracking
-----------------

Presence tracking maintains information about who is currently "present" 
in different topics. It handles distributed state synchronization and 
provides real-time updates about participant changes.

**Tracking Participants**

.. code-block:: python

   from pyphoenix import get_presence
   
   presence = get_presence()
   
   # Track a user's presence
   await presence.track(
       pid="user123",
       topic="room:lobby", 
       meta={
           "username": "Alice",
           "status": "online",
           "joined_at": time.time()
       }
   )
   
   # Get current presence list
   presences = await presence.list("room:lobby")

**Automatic Cleanup**

Presence automatically handles cleanup when connections are lost,
ensuring the presence state remains accurate.

**Callbacks and Events**

Register callbacks to react to presence changes:

.. code-block:: python

   async def on_join(pid, topic, meta):
       print(f"{meta['username']} joined {topic}")
   
   async def on_leave(pid, topic, meta):  
       print(f"{meta['username']} left {topic}")
   
   presence.on_join(on_join)
   presence.on_leave(on_leave)

Transport Layer
---------------

The transport layer handles the low-level communication between clients and servers.
PyPhoenix supports WebSocket transport with Phoenix wire format compatibility.

**WebSocket Protocol**

Messages follow the Phoenix wire format:
``[join_ref, ref, topic, event, payload]``

.. code-block:: python

   # Example message
   ["1", "2", "room:lobby", "new_message", {"text": "Hello!"}]

**Connection Management**

- Automatic heartbeat to keep connections alive
- Graceful reconnection on connection loss  
- Configurable timeouts and retry behavior

Middleware
----------

Middleware provides a way to add cross-cutting concerns to channels
without modifying the core channel logic. Common middleware includes:

**Authentication Middleware**

.. code-block:: python

   async def authenticate_user(payload):
       token = payload.get("token")
       # Validate token and return user info
       return {"user_id": "123", "username": "alice"}
   
   channel.use_middleware(AuthMiddleware(authenticate_user))

**Logging Middleware**

.. code-block:: python

   channel.use_middleware(LoggingMiddleware())

**Rate Limiting Middleware**  

.. code-block:: python

   channel.use_middleware(RateLimitMiddleware(max_messages_per_second=10))

Configuration
-------------

PyPhoenix uses a hierarchical configuration system that supports
environment variables, dictionaries, and programmatic configuration.

.. code-block:: python

   from pyphoenix import PhoenixConfig, set_config
   
   config = PhoenixConfig(
       host="0.0.0.0",
       port=4000,
       debug=False
   )
   
   # Configure components
   config.security.rate_limit_enabled = True
   config.transport.max_connections = 10000
   config.presence.cleanup_interval = 300
   
   set_config(config)

Message Flow
------------

Understanding how messages flow through PyPhoenix helps in designing
effective applications:

1. **Client Connection** - WebSocket connection established
2. **Channel Join** - Client joins specific channel topics
3. **Message Routing** - Incoming messages routed to appropriate channels
4. **Middleware Processing** - Middleware stack processes the message
5. **Event Handling** - Channel event handlers process the message
6. **Broadcasting** - Responses broadcast to relevant participants  
7. **PubSub Integration** - Cross-channel messages via PubSub
8. **Presence Updates** - Presence state updated as needed

This flow ensures messages are processed efficiently while maintaining
the flexibility to customize behavior through middleware and configuration.
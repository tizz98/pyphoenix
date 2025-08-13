Channel
=======

.. currentmodule:: pyphoenix.channel

The Channel class is the core component for real-time communication in PyPhoenix.
It provides Phoenix-compatible channel functionality with support for joining, leaving,
message pushing, broadcasting, and middleware processing.

Channel Class
-------------

.. autoclass:: Channel
   :members:
   :undoc-members:
   :show-inheritance:

   .. automethod:: __init__

Channel Lifecycle
-----------------

Channels follow a strict lifecycle pattern:

1. **CLOSED** - Initial state, not connected
2. **JOINING** - Join request sent, waiting for response  
3. **JOINED** - Successfully joined, can send/receive messages
4. **LEAVING** - Leave request sent, waiting for completion
5. **ERRORED** - Error occurred, channel unusable

State transitions are managed automatically, but you can check the current 
state using the ``state`` attribute.

Event Handling
--------------

Channels support event-based message handling. You can register handlers
for specific events:

.. code-block:: python

   channel.on("user_joined", handle_user_joined)
   channel.on("new_message", handle_new_message)

Built-in events include:

- ``phx_join`` - Channel join event
- ``phx_leave`` - Channel leave event  
- ``phx_reply`` - Reply to a push message
- ``phx_error`` - Channel error event
- ``phx_close`` - Channel close event

Custom Events
~~~~~~~~~~~~~

You can define custom event handlers by implementing methods with the ``on_`` prefix:

.. code-block:: python

   class ChatChannel(Channel):
       async def on_message(self, payload, socket):
           # Handle "message" events
           await self.broadcast("new_message", payload)
           
       async def on_typing(self, payload, socket):
           # Handle "typing" events
           await self.broadcast("user_typing", payload, exclude=socket)

Middleware Support  
------------------

Channels support middleware for cross-cutting concerns:

.. code-block:: python

   from pyphoenix import LoggingMiddleware, AuthMiddleware
   
   channel = Channel("room:lobby")
   channel.use_middleware(LoggingMiddleware())
   channel.use_middleware(AuthMiddleware(auth_function))

Available middleware includes:

- :class:`~pyphoenix.middleware.LoggingMiddleware` - Request/response logging
- :class:`~pyphoenix.middleware.AuthMiddleware` - Authentication  
- :class:`~pyphoenix.middleware.RateLimitMiddleware` - Rate limiting

Broadcasting
------------

Channels can broadcast messages to all joined participants:

.. code-block:: python

   # Broadcast to all participants
   await channel.broadcast("new_message", {"text": "Hello everyone!"})
   
   # Broadcast to all except sender
   await channel.broadcast("typing", {"user": "alice"}, exclude=sender_socket)

Error Handling
--------------

Channels provide comprehensive error handling:

.. code-block:: python

   try:
       response = await channel.join({"token": "invalid"})
   except JoinError as e:
       print(f"Failed to join: {e}")
   except PyPhoenixTimeoutError as e:
       print(f"Join timed out: {e}")

Common error types:

- :exc:`~pyphoenix.exceptions.JoinError` - Join operation failed
- :exc:`~pyphoenix.exceptions.ChannelError` - General channel error
- :exc:`~pyphoenix.exceptions.TimeoutError` - Operation timed out
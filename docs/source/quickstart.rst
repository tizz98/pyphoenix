Quick Start Guide
=================

This guide will help you get started with PyPhoenix quickly.

Installation
------------

PyPhoenix requires Python 3.13 or later. Install it using pip:

.. code-block:: bash

   pip install pyphoenix

For development, install with optional dependencies:

.. code-block:: bash

   # With development dependencies
   pip install pyphoenix[dev]

   # With documentation dependencies
   pip install pyphoenix[docs]

Basic Server
------------

Create a basic Phoenix server with a room channel:

.. code-block:: python

   import asyncio
   from pyphoenix import Phoenix, Channel

   # Create Phoenix application
   app = Phoenix()

   @app.channel("room:*")
   class RoomChannel(Channel):
       async def on_join(self, payload, socket):
           """Handle channel joins."""
           print(f"User joined room: {self.topic}")
           return {"status": "ok", "response": {"message": "Welcome!"}}
       
       async def on_message(self, payload, socket):
           """Handle incoming messages."""
           text = payload.get("text", "")
           username = payload.get("username", "Anonymous")
           
           # Broadcast to all users in the room
           await self.broadcast("new_message", {
               "username": username,
               "text": text,
               "timestamp": asyncio.get_event_loop().time()
           })
       
       async def on_leave(self, reason, socket):
           """Handle channel leaves."""
           print(f"User left room: {self.topic}, reason: {reason}")

   if __name__ == "__main__":
       # Start the server
       asyncio.run(app.start("localhost", 4000))

Basic Client
------------

Create a client to connect to your server:

.. code-block:: python

   import asyncio
   from pyphoenix import ClientSocket

   async def main():
       # Create client socket
       client = ClientSocket("ws://localhost:4000/socket")
       
       # Connect to server
       await client.connect()
       
       # Join a room
       room = client.channel("room:lobby")
       
       # Set up message handler
       @room.on("new_message")
       async def on_message(payload, ref):
           username = payload.get("username", "Unknown")
           text = payload.get("text", "")
           print(f"{username}: {text}")
       
       # Join the room
       response = await room.join()
       print(f"Joined room: {response}")
       
       # Send a message
       await room.push("message", {
           "username": "Alice",
           "text": "Hello, world!"
       })
       
       # Keep connection alive
       await asyncio.sleep(10)
       
       # Leave and disconnect
       await room.leave()
       await client.disconnect()

   asyncio.run(main())

With Middleware
---------------

Add middleware for authentication and logging:

.. code-block:: python

   import asyncio
   from pyphoenix import Phoenix, Channel, LoggingMiddleware, AuthMiddleware

   app = Phoenix()

   # Authentication function
   async def authenticate_user(payload):
       token = payload.get("token")
       if token == "valid_token":
           return {"user_id": "123", "username": "Alice"}
       return None

   @app.channel("room:*")
   class RoomChannel(Channel):
       def __init__(self, topic, params=None, socket=None):
           super().__init__(topic, params, socket)
           
           # Add middleware
           self.use_middleware(LoggingMiddleware())
           self.use_middleware(AuthMiddleware(authenticate_user))
       
       async def on_join(self, payload, socket):
           # User is automatically authenticated by middleware
           user = payload.get("authenticated_user")
           if user:
               print(f"Authenticated user {user['username']} joined {self.topic}")
               return {"status": "ok", "response": {"user": user}}
           
           return {"status": "error", "response": {"reason": "Authentication required"}}

   asyncio.run(app.start("localhost", 4000))

With Configuration
------------------

Use configuration for customizable behavior:

.. code-block:: python

   import asyncio
   from pyphoenix import Phoenix, Channel, PhoenixConfig, set_config

   # Create configuration
   config = PhoenixConfig(
       host="localhost",
       port=4001,
       debug=True
   )
   
   # Customize component settings
   config.channel.default_timeout = 15.0
   config.security.rate_limit_enabled = True
   config.security.max_messages_per_second = 5
   
   # Set global configuration
   set_config(config)

   app = Phoenix()

   @app.channel("room:*")
   class RoomChannel(Channel):
       async def on_join(self, payload, socket):
           return {"status": "ok"}

   asyncio.run(app.start())

Next Steps
----------

* Read the :doc:`user_guide/index` for detailed explanations
* Browse the :doc:`api/index` for complete API reference
* Check out :doc:`examples/index` for more advanced usage patterns
* Learn about :doc:`deployment` for production deployments
Phoenix Application
==================

.. currentmodule:: pyphoenix.phoenix

The Phoenix class is the main application class that manages channels, routing,
and serves as the entry point for PyPhoenix applications.

Phoenix Class
-------------

.. autoclass:: Phoenix
   :members:
   :undoc-members:
   :show-inheritance:

   .. automethod:: __init__

Channel Registration
--------------------

The Phoenix application uses decorators to register channel handlers for
specific topic patterns:

.. code-block:: python

   from pyphoenix import Phoenix, Channel
   
   app = Phoenix()
   
   @app.channel("room:*")
   class RoomChannel(Channel):
       async def on_join(self, payload, socket):
           return {"status": "ok"}
   
   @app.channel("user:*") 
   class UserChannel(Channel):
       async def on_join(self, payload, socket):
           # Only allow users to join their own channel
           user_id = self.topic.split(":")[-1]
           if payload.get("user_id") != user_id:
               return {"status": "error", "response": {"reason": "Unauthorized"}}
           return {"status": "ok"}

Topic Patterns
~~~~~~~~~~~~~~

Topic patterns support wildcards for flexible routing:

- ``room:*`` - Matches ``room:lobby``, ``room:general``, etc.
- ``user:*`` - Matches ``user:123``, ``user:alice``, etc.  
- ``game:*:*`` - Matches ``game:chess:123``, ``game:poker:456``, etc.
- ``exact_topic`` - Matches only the exact topic name

Application Lifecycle
---------------------

Phoenix applications have a simple lifecycle:

1. **Create** - Instantiate the Phoenix class
2. **Configure** - Register channels and set configuration  
3. **Start** - Begin accepting connections
4. **Stop** - Gracefully shutdown

.. code-block:: python

   import asyncio
   from pyphoenix import Phoenix
   
   app = Phoenix()
   
   # Register channels
   @app.channel("room:*")
   class RoomChannel(Channel):
       pass
   
   # Start the application
   async def main():
       try:
           await app.start("localhost", 4000)
       except KeyboardInterrupt:
           await app.stop()
   
   asyncio.run(main())

Configuration
-------------

Phoenix applications can be configured using the configuration system:

.. code-block:: python

   from pyphoenix import Phoenix, PhoenixConfig, set_config
   
   # Create configuration
   config = PhoenixConfig(
       host="0.0.0.0",
       port=4000,
       debug=False
   )
   
   # Customize settings
   config.transport.max_connections = 10000
   config.security.rate_limit_enabled = True
   
   # Apply configuration globally
   set_config(config)
   
   app = Phoenix()

Integration with PubSub and Presence
------------------------------------

Phoenix applications automatically integrate with the PubSub and Presence systems:

.. code-block:: python

   from pyphoenix import get_pubsub, get_presence
   
   @app.channel("room:*")
   class RoomChannel(Channel):
       async def on_join(self, payload, socket):
           # Track presence
           presence = get_presence()
           await presence.track(
               pid=payload["user_id"],
               topic=self.topic,
               meta={"username": payload["username"]}
           )
           
           # Subscribe to updates
           pubsub = get_pubsub()
           await pubsub.subscribe(f"{self.topic}:updates", self._handle_update)
           
           return {"status": "ok"}

Error Handling
--------------

Phoenix applications provide centralized error handling:

.. code-block:: python

   @app.on_error
   async def handle_error(error, context):
       logger.error("Application error", error=str(error), context=context)
       
   @app.on_channel_error  
   async def handle_channel_error(channel, error):
       logger.error("Channel error", topic=channel.topic, error=str(error))
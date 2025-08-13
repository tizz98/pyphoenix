PyPhoenix Documentation
=======================

PyPhoenix is a Python implementation of the Phoenix Framework's real-time communication patterns.
It provides channels, presence tracking, PubSub messaging, and WebSocket transport with a familiar Phoenix-style API.

.. toctree::
   :maxdepth: 2
   :caption: Contents:

   quickstart
   user_guide/index
   api/index
   examples/index
   deployment
   changelog

Features
--------

* **Channels**: Join/leave/push/broadcast operations with Phoenix wire format compatibility
* **WebSocket Transport**: Async WebSocket handling with heartbeat and reconnection
* **PubSub System**: Pattern-based message routing with wildcards (``room:*``)
* **Presence Tracking**: Distributed presence state management
* **Middleware Framework**: Extensible middleware for logging, authentication, rate limiting
* **Metrics & Monitoring**: Comprehensive metrics collection with counters, gauges, histograms
* **Configuration System**: Environment variable and dict-based configuration
* **Client Implementation**: Full client-side Socket and Channel with auto-reconnection
* **Message Serialization**: Support for JSON, MessagePack, and Pickle serialization

Quick Start
-----------

Install PyPhoenix:

.. code-block:: bash

   pip install pyphoenix

Create a basic server:

.. code-block:: python

   import asyncio
   from pyphoenix import Phoenix, Channel

   app = Phoenix()

   @app.channel("room:*")
   class RoomChannel(Channel):
       async def on_join(self, payload, socket):
           return {"status": "ok"}
       
       async def on_message(self, payload, socket):
           await self.broadcast("new_message", payload)

   # Start the server
   asyncio.run(app.start("localhost", 4000))

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
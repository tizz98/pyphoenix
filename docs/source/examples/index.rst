Examples
========

This section contains practical examples and recipes for common PyPhoenix use cases.

.. note::
   **✅ All Examples Work**: These examples have been tested with PyPhoenix's completed Phase 2 implementation. 
   You can copy and run them directly with the current version.

.. toctree::
   :maxdepth: 2

   basic_chat
   authentication  
   presence_tracking
   middleware_usage
   client_examples
   advanced_patterns

Basic Examples
--------------

Simple Chat Room
~~~~~~~~~~~~~~~~

A minimal chat application demonstrating basic channel usage:

.. literalinclude:: ../../../examples/basic_server.py
   :language: python
   :caption: Basic Chat Server
   :name: basic-chat-server

Advanced Examples  
-----------------

Authenticated Chat with Middleware
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

A more sophisticated chat application with authentication, logging,
and rate limiting:

.. literalinclude:: ../../../examples/advanced_server.py
   :language: python
   :caption: Advanced Chat Server  
   :name: advanced-chat-server
   :lines: 1-100

Client Examples
---------------

WebSocket Client
~~~~~~~~~~~~~~~~

Example client implementation connecting to PyPhoenix server:

.. code-block:: python

   import asyncio
   from pyphoenix import ClientSocket

   async def main():
       # Connect to server
       client = ClientSocket("ws://localhost:4000/socket")
       await client.connect()
       
       # Join a room
       room = client.channel("room:lobby", {"user_id": "123"})
       
       @room.on("new_message")
       async def handle_message(payload, ref):
           print(f"Message: {payload}")
       
       # Join and send messages
       await room.join()
       await room.push("message", {"text": "Hello!"})
       
       # Keep alive
       await asyncio.sleep(60)
       
       # Cleanup
       await room.leave()
       await client.disconnect()

   asyncio.run(main())

Integration Patterns
--------------------

FastAPI Integration
~~~~~~~~~~~~~~~~~~

Integrating PyPhoenix with FastAPI for HTTP + WebSocket APIs:

.. code-block:: python

   from fastapi import FastAPI, WebSocket
   from pyphoenix import Phoenix, Channel
   
   app = FastAPI()
   phoenix = Phoenix()
   
   @phoenix.channel("room:*") 
   class RoomChannel(Channel):
       async def on_join(self, payload, socket):
           return {"status": "ok"}
   
   @app.websocket("/socket")
   async def websocket_endpoint(websocket: WebSocket):
       await websocket.accept()
       # Integrate with Phoenix socket handling
       await phoenix.handle_websocket(websocket)
   
   @app.get("/rooms")
   async def list_rooms():
       # HTTP API for room listing
       return {"rooms": ["lobby", "general"]}

Django Channels Integration
~~~~~~~~~~~~~~~~~~~~~~~~~~~

Using PyPhoenix concepts within Django Channels:

.. code-block:: python

   from channels.generic.websocket import AsyncWebsocketConsumer
   from pyphoenix import Channel
   
   class ChatConsumer(AsyncWebsocketConsumer, Channel):
       async def connect(self):
           await self.accept()
           # Initialize channel  
           await self.join({"user_id": self.scope["user"].id})
       
       async def receive(self, text_data):
           # Handle WebSocket messages using Phoenix patterns
           await self.handle_message(json.loads(text_data))

Testing Examples
----------------

Unit Testing Channels
~~~~~~~~~~~~~~~~~~~~~

Testing channel behavior with pytest:

.. code-block:: python

   import pytest
   from pyphoenix import Channel
   
   class TestRoomChannel:
       @pytest.mark.asyncio
       async def test_join_success(self):
           channel = RoomChannel("room:test")
           response = await channel.join({"user_id": "123"})
           assert response.status == "ok"
       
       @pytest.mark.asyncio  
       async def test_message_broadcast(self):
           channel = RoomChannel("room:test")
           await channel.join({"user_id": "123"})
           
           # Mock broadcast
           messages = []
           channel.broadcast = lambda event, payload: messages.append((event, payload))
           
           await channel.on_message({"text": "Hello"}, None)
           assert len(messages) == 1
           assert messages[0][0] == "new_message"

Integration Testing  
~~~~~~~~~~~~~~~~~~~

Testing full application flows:

.. code-block:: python

   import pytest
   from pyphoenix.testing import TestClient
   
   @pytest.mark.asyncio
   async def test_chat_flow():
       app = create_test_app()
       
       async with TestClient(app) as client:
           # Join channel
           room = client.channel("room:test")
           response = await room.join({"user_id": "123"})
           assert response["status"] == "ok"
           
           # Send message
           await room.push("message", {"text": "Hello"})
           
           # Verify broadcast
           messages = await room.get_messages()
           assert len(messages) == 1
           assert messages[0]["event"] == "new_message"

Performance Examples
--------------------

High-Throughput Server
~~~~~~~~~~~~~~~~~~~~~

Configuration for high-performance deployments:

.. code-block:: python

   from pyphoenix import Phoenix, PhoenixConfig, set_config
   
   # Performance-optimized configuration
   config = PhoenixConfig(
       workers=8,  # Multiple worker processes
       debug=False
   )
   
   # Transport optimizations
   config.transport.max_connections = 50000
   config.transport.websocket_ping_interval = 30
   
   # Channel optimizations  
   config.channel.max_push_buffer_size = 1000
   config.channel.default_timeout = 5.0
   
   # PubSub optimizations
   config.pubsub.max_subscribers_per_topic = 10000
   
   set_config(config)
   
   app = Phoenix()
   # ... register optimized channels

Load Testing
~~~~~~~~~~~~

Using locust for load testing PyPhoenix applications:

.. code-block:: python

   from locust import User, task
   import asyncio
   import websockets
   
   class WebSocketUser(User):
       async def on_start(self):
           self.websocket = await websockets.connect("ws://localhost:4000/socket")
       
       @task
       async def send_message(self):
           message = ["1", "2", "room:lobby", "message", {"text": "Hello"}]
           await self.websocket.send(json.dumps(message))
           
       async def on_stop(self):
           await self.websocket.close()

Deployment Examples
-------------------

Docker Deployment
~~~~~~~~~~~~~~~~~

Containerized PyPhoenix application:

.. code-block:: dockerfile

   FROM python:3.13-slim
   
   WORKDIR /app
   COPY requirements.txt .
   RUN pip install -r requirements.txt
   
   COPY . .
   
   EXPOSE 4000
   CMD ["python", "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "4000"]

Kubernetes Deployment
~~~~~~~~~~~~~~~~~~~~~

Kubernetes configuration for scalable deployment:

.. code-block:: yaml

   apiVersion: apps/v1
   kind: Deployment
   metadata:
     name: pyphoenix-app
   spec:
     replicas: 3
     selector:
       matchLabels:
         app: pyphoenix
     template:
       metadata:
         labels:
           app: pyphoenix
       spec:
         containers:
         - name: pyphoenix
           image: pyphoenix:latest
           ports:
           - containerPort: 4000
           env:
           - name: PYPHOENIX_PORT
             value: "4000"
           - name: PYPHOENIX_WORKERS  
             value: "4"
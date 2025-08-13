Changelog
=========

All notable changes to PyPhoenix will be documented in this file.

The format is based on `Keep a Changelog <https://keepachangelog.com/en/1.0.0/>`_,
and this project adheres to `Semantic Versioning <https://semver.org/spec/v2.0.0.html>`_.

[Unreleased]
------------

[0.2.0] - 2025-08-13
--------------------

**🎉 Phase 2 Complete: Integration & Core Features**

Added
~~~~~

**Phoenix App Integration**
* Phoenix app class routes WebSocket connections to registered channels
* Channel pattern matching (``room:*`` → RoomChannel) working  
* WebSocket transport integrated with Phoenix application
* Complete routing from WebSocket → Phoenix → Channels

**End-to-End Functionality**
* Working client-server examples with real communication
* Complete channel join/leave flows between client and server
* Message broadcasting working across multiple connections

**Core Feature Implementation**
* PubSub integration with channel broadcasting (``channel.broadcast()``)
* Presence tracking methods (``track_presence()``, ``list_presence()``, ``broadcast_from()``)
* Comprehensive test suite with **71 passing tests**

**Developer Experience**  
* Working examples: ``target_chat_server.py`` and ``target_chat_client.py``
* Phoenix-style decorator API (``@app.channel("room:*")``)
* Robust error handling and socket cleanup

Fixed
~~~~~

**Socket & Channel Cleanup**
* Resolved double-leave issues and WebSocket close errors
* Fixed socket state management to prevent sending on closed sockets
* Added proper cleanup coordination between Socket and Channel

**Client Compatibility**
* Fixed join response handling and decorator patterns
* Updated client join response format expectations
* Corrected response format in ``_handle_reply()``

**Missing Implementation**
* Implemented ``track_presence()``, ``list_presence()``, ``broadcast_from()`` methods
* Added comprehensive presence method tests
* Fixed websocket library compatibility with modern websockets.asyncio API

[0.1.0] - 2025-08-13
--------------------

Added
~~~~~

**Core Features**

* Channel system with Phoenix-compatible wire format
* WebSocket transport with heartbeat and reconnection
* PubSub messaging with pattern matching (``room:*`` wildcards)  
* Presence tracking with distributed state management
* Phoenix application class for channel registration and routing

**Phase 1+ Enhancements**

* Middleware framework with logging, authentication, and rate limiting
* Configuration system with environment variable support
* Metrics collection with counters, gauges, and histograms
* Message serialization support (JSON, MessagePack, Pickle)
* Client-side Socket and Channel implementations
* Message queue with delivery guarantees
* Comprehensive exception handling
* Background task management

**Developer Experience**

* Comprehensive documentation with Sphinx
* API reference with detailed examples  
* User guides and deployment documentation
* Example applications (basic and advanced servers)
* Full test coverage with pytest
* Code formatting with ruff (100-character line length)

**Architecture**

* AsyncIO-based concurrency model
* Extensible middleware architecture
* Hierarchical configuration system
* Structured logging with contextual information
* Automatic presence cleanup and connection management
* Phoenix wire format: ``[join_ref, ref, topic, event, payload]``

Initial Features
~~~~~~~~~~~~~~~~

* **Channel Operations**: join, leave, push, broadcast with middleware processing
* **Event System**: Event-based message routing with custom handler support
* **Topic Patterns**: Flexible topic matching with wildcard support
* **Transport Layer**: WebSocket communication with connection lifecycle management
* **State Management**: Proper channel state transitions and error handling
* **Integration**: Built-in PubSub and Presence system integration

Dependencies
~~~~~~~~~~~~

* Python 3.13+ support
* websockets for WebSocket transport
* structlog for structured logging  
* aiohttp for HTTP server capabilities
* pytest and pytest-asyncio for testing
* ruff for code formatting and linting

Documentation
~~~~~~~~~~~~~

* Complete API reference documentation
* Quickstart guide and user manual
* Deployment guide with Docker/Kubernetes examples
* Examples and integration patterns
* Performance and security best practices